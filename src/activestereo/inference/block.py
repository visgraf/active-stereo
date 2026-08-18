"""Reference block matcher (SSD) with subpixel refinement and a curvature-based
variance estimate.

This is deliberately simple and slow: it is the *reference* implementation that
faster matchers are validated against, not the production path.
"""

from __future__ import annotations

import numpy as np

from activestereo.types import Estimate, FloatArray
from activestereo.utils import boxsum


class BlockMatcher:
    """Winner-take-all SSD block matching over an integer disparity range.

    Parameters
    ----------
    max_disparity : int
        Search range, pixels, ``[0, max_disparity]``.
    window : int
        Odd window side, pixels.
    uniqueness : float
        Minimum relative margin between best and runner-up cost for a match to be
        accepted. Below it the pixel is marked invalid rather than guessed.
    """

    def __init__(self, max_disparity: int = 32, window: int = 7, uniqueness: float = 0.05) -> None:
        if window % 2 == 0:
            raise ValueError(f"window must be odd, got {window}")
        if max_disparity < 1:
            raise ValueError(f"max_disparity must be >= 1, got {max_disparity}")
        self.max_disparity = int(max_disparity)
        self.window = int(window)
        self.uniqueness = float(uniqueness)

    @property
    def name(self) -> str:
        return f"block_d{self.max_disparity}_w{self.window}"

    def match(self, left: FloatArray, right: FloatArray) -> Estimate:
        left = np.asarray(left, dtype=float)
        right = np.asarray(right, dtype=float)
        if left.shape != right.shape:
            raise ValueError(f"shape mismatch: {left.shape} vs {right.shape}")

        H, W = left.shape
        D = self.max_disparity + 1
        cost = np.full((D, H, W), np.inf)

        r = self.window // 2
        kernel_area = self.window**2
        for d in range(D):
            shifted = np.full_like(right, np.nan)
            if d == 0:
                shifted = right.copy()
            else:
                shifted[:, d:] = right[:, :-d]
            diff = (left - shifted) ** 2
            valid = np.isfinite(diff)
            diff = np.where(valid, diff, 0.0)
            s = boxsum(diff, r)
            n = boxsum(valid.astype(float), r)
            with np.errstate(invalid="ignore", divide="ignore"):
                cost[d] = np.where(n > 0.5 * kernel_area, s / np.maximum(n, 1.0), np.inf)

        best = np.argmin(cost, axis=0)
        rows, cols = np.indices((H, W))
        c_best = cost[best, rows, cols]

        # Runner-up outside a +/-1 neighbourhood of the winner, for uniqueness.
        #
        # Masked in place and restored rather than done on a copy, which saves one
        # cost volume. Measured, because the guess was wrong: on a 200x300 pair
        # with D = 95 this moves the peak from 101.4 MB to 93.7 MB, not the ~46 MB
        # the volume's own size suggests. The binding allocation is
        # `np.argmin(cost, axis=0)` above -- reducing over the *leading* axis of a
        # C-contiguous array is strided, and numpy buffers a full second volume to
        # do it. Removing that needs a streaming two-pass matcher (find the winner
        # without materialising the volume, then re-walk it for the runner-up and
        # the parabola), which trades 2x compute for O(H*W) memory. Worth it only
        # if full-resolution imagery is ever wanted; at downsample 3 the ~1 GB
        # peak is not binding.
        #
        # The clip can make two of the three indices coincide (at best == 0 or
        # best == D-1), so a saved slice may itself already be `inf`. Restoring in
        # reverse order recovers the original value regardless, because the first
        # slice saved is the last one written back.
        saved = np.empty((3, H, W))
        touched = []
        for i, off in enumerate((-1, 0, 1)):
            idx = np.clip(best + off, 0, D - 1)
            touched.append(idx)
            saved[i] = cost[idx, rows, cols]
            cost[idx, rows, cols] = np.inf
        c_second = np.min(cost, axis=0)
        for i in reversed(range(3)):
            cost[touched[i], rows, cols] = saved[i]

        d_sub, var = _subpixel_and_variance(cost, best, rows, cols)

        accept = (
            np.isfinite(c_best)
            & (best > 0)
            & (best < D - 1)
            & (c_second > c_best * (1.0 + self.uniqueness))
        )
        value = np.where(accept, d_sub, np.nan)
        variance = np.where(accept, var, np.nan)
        return Estimate(value=value, variance=variance)


def _subpixel_and_variance(
    cost: FloatArray, best: np.ndarray, rows: np.ndarray, cols: np.ndarray
) -> tuple[FloatArray, FloatArray]:
    """Parabolic subpixel fit; variance from the fitted curvature.

    A sharp cost minimum (large curvature ``a``) means a well-localised match, so
    variance ~ 1/(2a). This is the crude but honest uncertainty that L4 needs; a
    proper posterior width comes from the MRF once L3 grows belief propagation.
    """
    D = cost.shape[0]
    lo = np.clip(best - 1, 0, D - 1)
    hi = np.clip(best + 1, 0, D - 1)
    c0 = cost[lo, rows, cols]
    c1 = cost[best, rows, cols]
    c2 = cost[hi, rows, cols]

    # A non-finite neighbour cost means the parabola is undefined. Fitting it
    # anyway yields variance 0 (infinite curvature) alongside a nan location --
    # a maximally confident non-answer. Reject explicitly instead.
    fittable = np.isfinite(c0) & np.isfinite(c1) & np.isfinite(c2)

    denom = np.where(fittable, c0 - 2.0 * c1 + c2, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        delta = np.where(np.abs(denom) > 1e-12, 0.5 * (c0 - c2) / denom, 0.0)
        delta = np.clip(np.nan_to_num(delta, nan=0.0), -1.0, 1.0)
        curvature = 0.5 * denom
        variance = np.where(
            np.isfinite(curvature) & (curvature > 1e-12), 1.0 / (2.0 * curvature), np.nan
        )

    value = np.where(fittable, best.astype(float) + delta, np.nan)
    return value, variance
