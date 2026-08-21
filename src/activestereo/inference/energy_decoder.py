"""L3 decoder for L2 population responses -- the bridge that makes L2 a layer.

Until this module existed, ``GaborEnergyEncoder`` was consumed by nothing in the
pipeline: no matcher read a ``(K, H, W)`` response volume, so the energy model
was validated in isolation (exp002) and never part of the system. This class
satisfies :class:`~activestereo.inference.base.DisparityMatcher` by wrapping any
:class:`~activestereo.encoding.base.DisparityEncoder`, which means every harness
that speaks the matcher Protocol -- the experiment runners, the comparative --
can consume the energy model with no further wiring. See issue #12 (exp005).

The readout is moments of the population profile, not curvature of a cost curve,
and that difference is the scientific point. exp004 showed curvature-derived
variance is *anti-calibrated* in half-occlusions: a sharp cost minimum at the
wrong disparity reads as precision. A profile's second moment can express what
curvature cannot -- "the evidence is spread across many disparities" -- and a
profile with no evidence at all is the natural place to refuse. Whether that
actually escapes the anti-calibration is exp005's H2, a hypothesis and not a
premise of this design.

Per pixel, from the bank response ``E_k`` (non-negative, ``nan`` where the
encoder marked the pixel invalid):

1. **Baseline subtraction** ``Ê_k = E_k - min_k E_k``. A uniform response floor
   (rectified noise, DC leakage through the Gabor) would otherwise drag a
   centroid toward the bank centre. Subtracting the per-pixel minimum commutes
   with positive gain, so it costs none of the encoder's invariance.
2. **Flatness refusal**: refuse where ``sum_k Ê_k <= flatness * sum_k E_k`` --
   the baseline carries essentially all the mass, i.e. no disparity is
   preferred. The rule is a *ratio*, deliberately: an absolute mass floor would
   make the refusal decision gain-dependent (mass scales with interocular gain)
   while the value and variance are not, and exp005's H3 tests exactly that
   end-to-end invariance. ``sum E = 0`` (no positive coherence anywhere)
   refuses automatically.
3. **Endpoint rejection**: the argmax must sit at least ``centroid_halfwidth``
   channels from either end of the bank, so the centroid window always fits.
   This subsumes ``BlockMatcher``'s single-channel endpoint rejection and is
   slightly stricter; a true disparity at the edge of the search range is
   declined, not clamped.
4. **Value**: centroid of ``Ê`` over the ``2*centroid_halfwidth + 1`` channels
   around the argmax. Pixels, left-image convention, positive = crossed
   (CLAUDE.md §3). At 1 px channel spacing no parabolic fit is needed.
5. **Variance**: second moment of the *full* normalised profile about the
   value, plus ``step**2 / 12``. Units px². The full profile -- not just the
   local window -- so that multimodal evidence honestly inflates the variance;
   that is the property exp005 measures. The quantisation floor is not
   cosmetic: ``Estimate.precision`` zeroes any pixel whose variance is not
   strictly positive, so a single-channel delta profile with moment 0 would
   otherwise get *zero* fusion weight -- the most confident answer discarded.
6. Refused or encoder-invalid pixels are ``nan`` in value **and** variance,
   per the L3 contract. Declining is what this readout does when there is no
   evidence, not a bolted-on test.

``flatness`` and ``centroid_halfwidth`` are exp005's pre-registered readout
constants: fixed from unit-test and RDS work only, posted to issue #12 before
the decoder touches any Middlebury scene. The encoder parameters default to
exp002's frozen values and are not tuning knobs here (see that experiment's
escalation note).
"""

from __future__ import annotations

import numpy as np

from activestereo.encoding.base import DisparityEncoder
from activestereo.encoding.energy import GaborEnergyEncoder
from activestereo.types import Estimate, FloatArray


class EnergyDecoder:
    """Population readout over an L2 disparity bank, as a ``DisparityMatcher``.

    Parameters
    ----------
    max_disparity : int
        Search range, pixels; the default bank is ``arange(0, max_disparity+1)``
        at 1 px spacing, mirroring ``BlockMatcher``'s ``[0, max_disparity]``.
        Ignored when ``encoder`` is supplied.
    frequency, sigma, window :
        Passed to the default ``GaborEnergyEncoder``. Defaults are exp002's
        frozen values; changing them here would re-open issue #1 through the
        back door.
    flatness : float
        Refusal threshold in (0, 1): refuse where the baseline-subtracted mass
        is at most this fraction of the raw mass. Dimensionless, gain-invariant.
    centroid_halfwidth : int
        Half-width, in channels, of the centroid window around the argmax.
    encoder : DisparityEncoder, optional
        Injected encoder (for tests, or a future multi-scale bank). Its bank
        must be uniformly spaced and sorted ascending.
    """

    def __init__(
        self,
        max_disparity: int = 32,
        frequency: float = 0.2618,
        sigma: float = 6.0,
        window: int = 7,
        flatness: float = 0.05,
        centroid_halfwidth: int = 2,
        encoder: DisparityEncoder | None = None,
    ) -> None:
        if not 0.0 < flatness < 1.0:
            raise ValueError(f"flatness must be in (0, 1), got {flatness}")
        if centroid_halfwidth < 1:
            raise ValueError(f"centroid_halfwidth must be >= 1, got {centroid_halfwidth}")
        if encoder is None:
            if max_disparity < 1:
                raise ValueError(f"max_disparity must be >= 1, got {max_disparity}")
            encoder = GaborEnergyEncoder(
                np.arange(0, max_disparity + 1, dtype=float),
                frequency=frequency,
                sigma=sigma,
                window=window,
            )
        d = np.asarray(encoder.disparities, dtype=float)
        steps = np.diff(d)
        if d.size < 3 or steps.size == 0 or not np.allclose(steps, steps[0]):
            raise ValueError(
                "the encoder's bank must be uniformly spaced, sorted, and have at "
                f"least 3 channels; got {d!r}. The variance floor (step^2/12) and "
                "the centroid window both assume a uniform grid."
            )
        self.encoder = encoder
        self.flatness = float(flatness)
        self.centroid_halfwidth = int(centroid_halfwidth)
        self._step = float(steps[0])

    @property
    def name(self) -> str:
        d = np.asarray(self.encoder.disparities)
        return f"energy_d{round(float(d.max()))}_wc{self.centroid_halfwidth}"

    def match(self, left: FloatArray, right: FloatArray) -> Estimate:
        left = np.asarray(left, dtype=float)
        right = np.asarray(right, dtype=float)
        if left.shape != right.shape:
            raise ValueError(f"shape mismatch: {left.shape} vs {right.shape}")

        E = self.encoder.encode(left, right)  # (K, H, W); nan in every band where invalid
        d = np.asarray(self.encoder.disparities, dtype=float)
        K = d.size
        wc = self.centroid_halfwidth

        valid = np.all(np.isfinite(E), axis=0)
        raw_mass = E.sum(axis=0)
        floor = E.min(axis=0)
        # In-place baseline subtraction: E is a fresh array from encode(), and at
        # Middlebury scale it is ~1.3 GB -- a second copy would double the peak
        # for no benefit. From here on, E *is* the baseline-subtracted profile.
        E -= floor[None, :, :]
        mass = E.sum(axis=0)

        # Flatness refusal. nan comparisons are False, so invalid pixels fall
        # through to the `valid` mask rather than deciding anything here.
        with np.errstate(invalid="ignore"):
            flat = mass <= self.flatness * raw_mass

        # Plain argmax, deliberately: masking nans first
        # (np.where(isfinite(E), E, -inf)) materialises a second full volume --
        # ~1.3 GB on the widest Middlebury bank, and a measured contributor to
        # exp005's 8.7 GB peak. At invalid pixels argmax over nans returns a
        # garbage index, and every path that consumes it is already gated by
        # `valid`/`accept`; at valid pixels E is finite and the result is
        # identical. Byte-identity across this change is pinned in the unit
        # suite.
        kstar = np.argmax(E, axis=0)
        interior = (kstar >= wc) & (kstar <= K - 1 - wc)

        # Local centroid around the argmax. Indices are clipped only so the
        # gather is legal for pixels that `interior` already rejects.
        offsets = np.arange(-wc, wc + 1)
        idx = np.clip(kstar[None, :, :] + offsets[:, None, None], 0, K - 1)
        local = np.take_along_axis(E, idx, axis=0)
        local_d = d[idx]
        with np.errstate(invalid="ignore", divide="ignore"):
            den = local.sum(axis=0)
            value = np.where(den > 0, (local_d * local).sum(axis=0) / den, np.nan)

        # Second moment of the FULL normalised profile about the value, summed
        # channel by channel: materialising (d - value) as (K, H, W) would cost
        # another full volume, and K iterations of (H, W) arithmetic are cheap.
        m2 = np.zeros_like(value)
        for k in range(K):
            m2 += (d[k] - value) ** 2 * E[k]
        with np.errstate(invalid="ignore", divide="ignore"):
            m2 = np.where(mass > 0, m2 / mass, np.nan)
        variance = m2 + self._step**2 / 12.0

        accept = valid & ~flat & interior & np.isfinite(value) & np.isfinite(variance)
        return Estimate(
            value=np.where(accept, value, np.nan),
            variance=np.where(accept, variance, np.nan),
        )
