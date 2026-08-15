"""Vergence error estimation from the disparity field.

See ADR-0001. The single-pixel estimate at the fovea is unusable: it is one
sample of a noisy field, and at exactly the point where matching is hardest
(texture-poor fixation targets, occlusion boundaries). The windowed median is
what makes the control loop of L5 stable.
"""

from __future__ import annotations

import numpy as np

from activestereo.types import Estimate


def estimate_vergence_disparity(
    disparity: Estimate,
    centre: tuple[int, int] | None = None,
    window: int = 15,
    min_valid_fraction: float = 0.25,
) -> tuple[float, float]:
    """Estimate the disparity at the fixation point and its uncertainty.

    Uses the **median** over a window rather than the value at a single pixel.
    The median is chosen over the mean because the failure mode being defended
    against is outliers (mismatches, occlusion), not Gaussian noise.

    Parameters
    ----------
    disparity : Estimate, the L3 disparity field.
    centre : (row, col) of the fovea; defaults to the image centre.
    window : odd window side, pixels.
    min_valid_fraction : if fewer than this fraction of window pixels are valid,
        return ``(nan, inf)`` rather than a number. Refusing to answer is correct
        here: a confident wrong vergence error drives the loop into the wall.

    Returns
    -------
    (disparity_estimate, variance) in pixels and pixels squared. ``(nan, inf)``
    signals "no usable measurement", which the Kalman filter handles by
    predicting through with no update.
    """
    if window % 2 == 0:
        raise ValueError(f"window must be odd, got {window}")

    H, W = disparity.value.shape
    r0, c0 = (H // 2, W // 2) if centre is None else centre
    r = window // 2
    rlo, rhi = max(0, r0 - r), min(H, r0 + r + 1)
    clo, chi = max(0, c0 - r), min(W, c0 + r + 1)

    patch = disparity.value[rlo:rhi, clo:chi]
    patch_var = disparity.variance[rlo:rhi, clo:chi]
    valid = np.isfinite(patch) & np.isfinite(patch_var)

    n_valid = int(valid.sum())
    if n_valid == 0 or n_valid < min_valid_fraction * patch.size:
        return float("nan"), float("inf")

    d_hat = float(np.median(patch[valid]))
    # Variance of the median ~ (pi/2) * var / n for large n; the pi/2 factor is
    # the asymptotic efficiency loss of the median relative to the mean.
    mean_var = float(np.mean(patch_var[valid]))
    var_hat = (np.pi / 2.0) * mean_var / n_valid
    return d_hat, var_hat
