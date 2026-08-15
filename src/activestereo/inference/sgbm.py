"""OpenCV SGBM matcher, wrapped to satisfy the L3 contract.

OpenCV is an optional dependency: import this module only where it is installed,
and mark tests with ``@pytest.mark.requires_cv2``.
"""

from __future__ import annotations

import numpy as np

from activestereo.types import Estimate, FloatArray


class SGBMMatcher:
    """Semi-global block matching.

    OpenCV returns fixed-point disparity scaled by 16 and uses a negative sentinel
    for unmatched pixels. Both are translated at this boundary so that nothing
    downstream ever sees an OpenCV convention (CLAUDE.md §3).
    """

    def __init__(
        self,
        max_disparity: int = 32,
        block_size: int = 5,
        uniqueness_ratio: int = 10,
        base_variance: float = 0.25,
    ) -> None:
        if max_disparity % 16 != 0:
            raise ValueError(f"SGBM requires max_disparity divisible by 16, got {max_disparity}")
        self.max_disparity = int(max_disparity)
        self.block_size = int(block_size)
        self.uniqueness_ratio = int(uniqueness_ratio)
        self.base_variance = float(base_variance)

    @property
    def name(self) -> str:
        return f"sgbm_d{self.max_disparity}_b{self.block_size}"

    def match(self, left: FloatArray, right: FloatArray) -> Estimate:
        import cv2  # imported lazily: optional dependency

        lo = _to_uint8(left)
        ro = _to_uint8(right)
        matcher = cv2.StereoSGBM_create(
            minDisparity=0,
            numDisparities=self.max_disparity,
            blockSize=self.block_size,
            P1=8 * self.block_size**2,
            P2=32 * self.block_size**2,
            uniquenessRatio=self.uniqueness_ratio,
            mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY,
        )
        raw = matcher.compute(lo, ro).astype(float) / 16.0
        value = np.where(raw > 0.0, raw, np.nan)
        variance = np.where(np.isfinite(value), self.base_variance, np.nan)
        return Estimate(value=value, variance=variance)


def _to_uint8(a: FloatArray) -> np.ndarray:
    """Normalise to 8-bit for OpenCV, treating nan as zero intensity."""
    a = np.asarray(a, dtype=float)
    finite = np.isfinite(a)
    if not finite.any():
        return np.zeros(a.shape, dtype=np.uint8)
    lo, hi = np.nanmin(a), np.nanmax(a)
    scale = 255.0 / (hi - lo) if hi > lo else 0.0
    out = np.zeros(a.shape, dtype=float)
    out[finite] = (a[finite] - lo) * scale
    return out.astype(np.uint8)
