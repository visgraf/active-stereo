"""Saliency for the active-sampling loop.

See ADR-0002. Blurring a saliency map that still contains invalid pixels is the
bug that made the gaze policy loop forever on an occlusion band: the invalid
region reads as maximally uncertain, so it is maximally attractive, so the policy
fixates it, and no fixation can resolve it because the occlusion is geometric.

Validity must be handled *before* any spatial mixing. `masked_blur` is the only
sanctioned way to smooth a field with invalid entries in this codebase.
"""

from __future__ import annotations

import numpy as np

from activestereo.types import Estimate, FloatArray


def masked_blur(field: FloatArray, valid: np.ndarray, sigma: float) -> FloatArray:
    """Normalised-convolution blur that never lets invalid pixels leak in.

    Blurs ``field * valid`` and ``valid`` with the same kernel and divides. Each
    output pixel is therefore the weighted mean of the *valid* neighbours only.
    Pixels with no valid support in range stay ``nan``.

    This is the operation people reach for a plain Gaussian blur for, and it is
    not the same thing: a plain blur silently treats missing data as zero.
    """
    f = np.where(valid, np.nan_to_num(field, nan=0.0), 0.0)
    w = valid.astype(float)
    num = _gaussian_blur(f, sigma)
    den = _gaussian_blur(w, sigma)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(den > 1e-6, num / den, np.nan)
    return out


def uncertainty_saliency(
    depth: Estimate,
    sigma: float = 3.0,
    exclude_invalid: bool = True,
) -> FloatArray:
    """Saliency proportional to posterior depth variance.

    Parameters
    ----------
    depth : Estimate from L4.
    sigma : blur scale, pixels.
    exclude_invalid : keep ``True``. The parameter exists only so the regression
        test in ``tests/regression/`` can demonstrate the failure it guards
        against; production code must never set it ``False``. See ADR-0002.

    Returns
    -------
    Saliency map, ``nan`` where no valid support exists. Invalid pixels are *not*
    salient -- they are unknowable, which is a different thing from uncertain.
    """
    valid = depth.valid
    raw = np.where(valid, depth.variance, np.nan)

    if not exclude_invalid:
        # The historical bug, retained solely as a documented counterexample:
        # invalid pixels become +inf saliency and dominate the argmax forever.
        raw = np.where(valid, depth.variance, np.inf)
        return _gaussian_blur(np.nan_to_num(raw, posinf=np.nanmax(raw[valid]) * 10), sigma)

    return masked_blur(raw, valid, sigma)


def _gaussian_blur(a: FloatArray, sigma: float) -> FloatArray:
    """Separable Gaussian blur with edge padding. NumPy-only, no SciPy needed."""
    if sigma <= 0:
        return a.copy()
    radius = max(1, int(np.ceil(3.0 * sigma)))
    x = np.arange(-radius, radius + 1, dtype=float)
    k = np.exp(-0.5 * (x / sigma) ** 2)
    k /= k.sum()

    pad = np.pad(a, ((radius, radius), (0, 0)), mode="edge")
    out = np.apply_along_axis(lambda m: np.convolve(m, k, mode="valid"), 0, pad)
    pad = np.pad(out, ((0, 0), (radius, radius)), mode="edge")
    out = np.apply_along_axis(lambda m: np.convolve(m, k, mode="valid"), 1, pad)
    return out
