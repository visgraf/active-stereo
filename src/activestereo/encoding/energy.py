"""L2 -- binocular energy-model encoder.

Implements a position-shift quadrature energy model (Ohzawa-DeAngelis-Freeman
1990; Fleet-Wagner-Heeger 1996): each eye's image is filtered with a complex
Gabor kernel (Gaussian envelope x carrier at ``frequency``) to get complex
responses ``Z_L``, ``Z_R``. For each candidate disparity ``d_k`` in the bank,
the response is the rectified coherence between the left response and the
*spatially re-indexed* right response:

    E_k(x) = relu( Re( Z_L(x) . conj(Z_R(x - d_k)) ) )

This is exact, not an approximation: because Gabor filtering is linear and
shift-equivariant, if the true disparity at ``x`` is ``d0`` then
``Z_R(x - d0) == Z_L(x)`` exactly (up to noise and edge truncation), so
``E_{d0}(x) == |Z_L(x)|**2``, generically the largest value across ``k`` since
uncorrelated channels average to a smaller value. An earlier version of this
module tried a pure phase-rotation combination (no spatial re-indexing,
``Z_L(x) + Z_R(x)*exp(-i*frequency*d_k)``) reasoning that phase should advance
linearly with position for a locally narrowband signal -- that assumption
degrades once the disparity being tested exceeds roughly one envelope width
(``sigma``), and it measurably failed the unit tests at ``d0=8, sigma=6``. The
position-shift form used here relies on the exact shift-equivariance property
instead and needs no such approximation.

Gain invariance is correspondingly exact and simple: scaling the right image
by a positive real gain ``g`` scales ``Z_R`` by ``g`` (linear filter), which
scales ``E_k(x)`` by ``g`` *uniformly across every k* (``relu`` commutes with
positive scaling). So ``argmax_k E_k(x)`` is unchanged for any ``g > 0`` --
this is what exp002 (issue #1) validates quantitatively.

That invariance distinguishes this construction from a differencing (SSD)
encoder such as ``inference.block.BlockMatcher``, whose cost has cross-terms
at different powers of gain and is therefore not gain-invariant. It does
*not*, on its own, distinguish it from a squared-cross-correlation-of-raw-
pixels fake, since ``argmax`` of any purely multiplicative ``gain**n *
f_k(x)`` profile is gain-invariant regardless of mechanism -- see
exp002/findings.md for the full discussion of what this test does and
doesn't rule out.
"""

from __future__ import annotations

import numpy as np

from activestereo.types import FloatArray


class GaborEnergyEncoder:
    """Quadrature binocular energy encoder satisfying ``DisparityEncoder``.

    Parameters
    ----------
    disparities : array-like, shape (K,)
        Disparity bank, pixels, signed, left-image convention (CLAUDE.md §3).
    frequency : float
        Carrier frequency of the Gabor front-end filter, radians per pixel.
        Shapes the encoder's frequency tuning; does not affect which channel
        wins (decoding is via spatial re-indexing, not phase arithmetic).
    sigma : float
        Gaussian envelope half-width of the Gabor front-end filter, pixels.
    window : int
        Odd side length, pixels, of the local pooling window applied to the
        per-pixel coherence before rectification. A single pixel's complex
        product is too noisy a coherence estimate on its own (the encoder's
        two Gabor responses are still just one sample each); pooling over a
        neighbourhood is the same fix ``inference.block.BlockMatcher`` uses
        for its own per-pixel cost, box-summed over the same kind of window.
        Pooling is linear and happens *before* rectification, so it changes
        nothing about the gain-invariance argument above.

    Notes
    -----
    ``encode`` returns a response volume, not an :class:`Estimate` -- encoders
    produce evidence, never a decision (see ``encoding/base.py``), so
    ADR-0005's estimate-and-variance contract does not apply here.
    """

    def __init__(
        self,
        disparities: FloatArray,
        frequency: float = 0.2618,
        sigma: float = 6.0,
        window: int = 7,
    ) -> None:
        d = np.asarray(disparities, dtype=float)
        if d.ndim != 1 or d.size == 0:
            raise ValueError(f"disparities must be a non-empty 1-D array, got shape {d.shape}")
        if frequency <= 0:
            raise ValueError(f"frequency must be positive, got {frequency}")
        if sigma <= 0:
            raise ValueError(f"sigma must be positive, got {sigma}")
        if window % 2 == 0:
            raise ValueError(f"window must be odd, got {window}")
        self._disparities = d
        self.frequency = float(frequency)
        self.sigma = float(sigma)
        self.window = int(window)

    @property
    def disparities(self) -> FloatArray:
        return self._disparities

    def encode(self, left: FloatArray, right: FloatArray) -> FloatArray:
        left = np.asarray(left, dtype=float)
        right = np.asarray(right, dtype=float)
        if left.shape != right.shape:
            raise ValueError(f"shape mismatch: {left.shape} vs {right.shape}")

        zl = _complex_response(left, self.frequency, self.sigma)
        zr = _complex_response(right, self.frequency, self.sigma)

        H, W = left.shape
        K = self._disparities.size
        max_shift = int(np.ceil(np.max(np.abs(self._disparities)))) if K else 0
        zr_pad = np.pad(
            zr, ((0, 0), (max_shift, max_shift)), mode="constant", constant_values=np.nan
        )

        r = self.window // 2
        out = np.empty((K, H, W), dtype=float)
        for k, dk in enumerate(self._disparities):
            shift = round(dk)
            start = max_shift - shift
            zr_shifted = zr_pad[:, start : start + W]
            coherence = np.real(zl * np.conj(zr_shifted))
            out[k] = np.maximum(0.0, _pooled_mean(coherence, r))

        # Protocol contract: invalid pixels are nan in every band, not just the
        # specific channels whose shift ran off the edge (encoding/base.py).
        invalid = ~np.all(np.isfinite(out), axis=0)
        return np.where(invalid[None, :, :], np.nan, out)


def _pooled_mean(a: FloatArray, r: int) -> FloatArray:
    """Mean over a (2r+1)x(2r+1) window, masking non-finite entries before
    mixing (ADR-0002) rather than letting a single noisy pixel's coherence
    stand for its neighbourhood. Same cumulative-sum box-sum technique as
    ``inference.block.BlockMatcher._boxsum``, duplicated locally rather than
    imported since it's a small private helper each module owns.
    """
    if r == 0:
        return a
    valid = np.isfinite(a)
    filled = np.where(valid, a, 0.0)
    s = _boxsum(filled, r)
    n = _boxsum(valid.astype(float), r)
    kernel_area = (2 * r + 1) ** 2
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(n > 0.5 * kernel_area, s / np.maximum(n, 1.0), np.nan)


def _boxsum(a: FloatArray, r: int) -> FloatArray:
    """Sum over a (2r+1)x(2r+1) window, edge-padded, same shape out."""
    pad = np.pad(a, r, mode="edge")
    c = np.cumsum(np.cumsum(pad, axis=0), axis=1)
    c = np.pad(c, ((1, 0), (1, 0)))
    k = 2 * r + 1
    H, W = a.shape
    return c[k : k + H, k : k + W] - c[0:H, k : k + W] - c[k : k + H, 0:W] + c[0:H, 0:W]


def _complex_response(image: FloatArray, frequency: float, sigma: float) -> np.ndarray:
    """Normalised-convolution complex Gabor response, row-wise, along columns.

    Generalises ``policy.saliency.masked_blur``'s normalised-convolution
    technique (ADR-0002: mask invalid pixels before any spatial mixing) to a
    signed, complex kernel. The numerator uses the signed cos/sin kernel, but
    the *normalisation* weight is the non-negative Gaussian envelope alone --
    dividing by a convolved signed kernel would give a denominator that
    crosses zero even under full support, which a plain reuse of
    ``masked_blur`` would silently do.
    """
    valid = np.isfinite(image)
    filled = np.where(valid, image, 0.0)

    radius = max(1, int(np.ceil(3.0 * sigma)))
    x = np.arange(-radius, radius + 1, dtype=float)
    env = np.exp(-0.5 * (x / sigma) ** 2)
    k_cos = env * np.cos(frequency * x)
    k_sin = env * np.sin(frequency * x)

    def _row_convolve(a: np.ndarray, kernel: np.ndarray) -> np.ndarray:
        pad = np.pad(a, ((0, 0), (radius, radius)), mode="edge")
        return np.apply_along_axis(lambda m: np.convolve(m, kernel, mode="valid"), 1, pad)

    num_real = _row_convolve(filled, k_cos)
    num_imag = _row_convolve(filled, k_sin)
    den = _row_convolve(valid.astype(float), env)

    with np.errstate(invalid="ignore", divide="ignore"):
        real = np.where(den > 1e-6, num_real / den, np.nan)
        imag = np.where(den > 1e-6, num_imag / den, np.nan)
    return real + 1j * imag
