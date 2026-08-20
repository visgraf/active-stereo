"""L2 -- multi-scale binocular energy bank.

exp005 localised the single-scale encoder's failure precisely: the readout above
it is unbiased wherever the true peak wins, but one 1-D Gabor at a 24 px period
carries almost no matchable structure on photographs -- Middlebury errors landed
at 91-96% of the uniform-guess floor, and on random dots the answered population
was contaminated by pixels where broadband noise, not the stimulus, chose the
channel (issue #12, exp005 findings).

A population over spatial scales attacks both pathologies at once, and the two
mechanisms are different:

- **Contamination**: a coarse scale's coherence profile has no false peaks
  within its long quasi-period, so a spurious fine-scale candidate far from the
  true disparity finds no support and the combined profile suppresses it.
- **Precision**: a fine scale localises the surviving peak to sub-pixel where
  the coarse scale alone cannot.

This is the coarse-to-fine construction of phase-based stereo (Fleet-Wagner-
Heeger lineage), and it is also the V1-faithful choice: populations across
spatial frequency with bandwidth roughly constant in octaves (sigma scaling
with period).

The class composes existing :class:`~activestereo.encoding.energy.
GaborEnergyEncoder` instances over one shared disparity bank -- reuse, not
reimplementation: the per-scale nan handling, edge bands and ADR-0002 pooling
are all inherited, and the per-scale invalid masks coincide because the edge
band is set by the shared bank, not by sigma.

**Gain invariance is exact per scale, before combination.** Each scale's
profile is normalised to ``P_s = E_s / sum_k E_s`` -- a ratio, so a positive
right-image gain cancels within every scale independently (bit-exactly for
power-of-two gains, since only floating-point exponents move). Any combination
of invariant profiles is invariant; nothing is delegated to a homogeneity
argument about the combination rule.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from activestereo.encoding.energy import GaborEnergyEncoder
from activestereo.types import FloatArray

#: (period px, sigma px) per scale; sigma = period/2 keeps bandwidth roughly
#: constant in octaves. The exp006 dev stage selects a subset from a declared
#: grid (issue #13); this default is the full four-octave ladder.
DEFAULT_SCALES: tuple[tuple[float, float], ...] = ((4, 2), (8, 4), (16, 8), (32, 16))


class MultiScaleEnergyEncoder:
    """A ``DisparityEncoder`` combining energy profiles across spatial scales.

    Parameters
    ----------
    disparities : array-like, shape (K,)
        Shared disparity bank, pixels, left-image convention (CLAUDE.md §3).
    scales : sequence of (period, sigma)
        Gabor carrier period and envelope half-width per scale, pixels.
        ``frequency = 2*pi/period``.
    combine : {"product", "sum"}
        ``product``: naive-Bayes fusion of per-scale profiles,
        ``prod_s (P_s + floor)`` -- sharpest suppression of unsupported peaks;
        the ``floor`` keeps one weak scale from vetoing everything.
        ``sum``: ``sum_s w_s P_s`` -- robust, weaker suppression.
    weights : sequence of float, optional
        Per-scale weights for ``combine="sum"``; uniform when omitted. Must be
        positive (a zero weight is a deleted scale -- delete it instead).
    floor : float
        Regulariser for the product rule, in profile-probability units
        (a uniform profile has mass ``1/K`` per channel).
    window : int
        Pooling window passed to every scale, as in exp002/exp005.

    Notes
    -----
    A **dead scale** -- zero coherence mass at a pixel -- contributes a
    *uniform* profile under ``product`` (no evidence must not veto the other
    scales) and zero under ``sum``. A pixel invalid at **any** scale is ``nan``
    in every band, per the ``encoding/base.py`` contract.
    """

    def __init__(
        self,
        disparities: FloatArray,
        scales: Sequence[tuple[float, float]] = DEFAULT_SCALES,
        combine: str = "product",
        weights: Sequence[float] | None = None,
        floor: float = 1e-3,
        window: int = 7,
    ) -> None:
        if combine not in ("product", "sum"):
            raise ValueError(f"combine must be 'product' or 'sum', got {combine!r}")
        if not scales:
            raise ValueError("at least one (period, sigma) scale is required")
        if floor <= 0:
            raise ValueError(f"floor must be positive, got {floor}")
        if weights is None:
            weights = [1.0] * len(scales)
        if len(weights) != len(scales) or any(w <= 0 for w in weights):
            raise ValueError(
                f"weights must be positive and match scales: {weights!r} vs {len(scales)} scales"
            )
        self._encoders = [
            GaborEnergyEncoder(
                disparities, frequency=2.0 * np.pi / period, sigma=sigma, window=window
            )
            for period, sigma in scales
        ]
        self.scales = tuple((float(p), float(s)) for p, s in scales)
        self.combine = combine
        self.weights = tuple(float(w) for w in weights)
        self.floor = float(floor)

    @property
    def disparities(self) -> FloatArray:
        return self._encoders[0].disparities

    def encode(self, left: FloatArray, right: FloatArray) -> FloatArray:
        left = np.asarray(left, dtype=float)
        right = np.asarray(right, dtype=float)
        if left.shape != right.shape:
            raise ValueError(f"shape mismatch: {left.shape} vs {right.shape}")

        K = self.disparities.size
        out: FloatArray | None = None
        valid_all: np.ndarray | None = None

        # One scale volume in memory at a time, plus the accumulator: ~2 volumes
        # peak instead of S. At Middlebury's widest bank a volume is ~1.3 GB.
        for encoder, weight in zip(self._encoders, self.weights, strict=True):
            E = encoder.encode(left, right)  # (K, H, W)
            valid = np.all(np.isfinite(E), axis=0)
            valid_all = valid if valid_all is None else (valid_all & valid)

            mass = E.sum(axis=0)
            with np.errstate(invalid="ignore", divide="ignore"):
                # In place: E becomes this scale's normalised profile P_s. A
                # dead scale (mass 0) becomes uniform under `product` -- no
                # evidence must not veto -- and zero under `sum`.
                dead_value = 1.0 / K if self.combine == "product" else 0.0
                E = np.where(mass[None, :, :] > 0, E / mass[None, :, :], dead_value)

            if self.combine == "product":
                E += self.floor
                out = E if out is None else out * E
            else:
                E *= weight
                out = E if out is None else out + E

        assert out is not None and valid_all is not None  # scales is non-empty
        return np.where(valid_all[None, :, :], out, np.nan)
