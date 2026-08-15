"""Shared types. Every layer speaks these; nothing here imports a layer."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.floating]


@dataclass(frozen=True)
class StereoRig:
    """Binocular rig geometry.

    Attributes
    ----------
    baseline : float
        Interocular distance, metres.
    focal_px : float
        Focal length, pixels.
    principal_point : tuple[float, float]
        (row, col) of the principal point, pixels.
    vergence : float
        Total vergence angle at the fixation point, radians. Zero means parallel
        (fixation at infinity).
    """

    baseline: float
    focal_px: float
    principal_point: tuple[float, float] = (0.0, 0.0)
    vergence: float = 0.0

    def __post_init__(self) -> None:
        if self.baseline <= 0:
            raise ValueError(f"baseline must be positive, got {self.baseline}")
        if self.focal_px <= 0:
            raise ValueError(f"focal_px must be positive, got {self.focal_px}")

    @property
    def fixation_distance(self) -> float:
        """Distance to the fixation point in metres; ``inf`` when vergence is 0."""
        if self.vergence <= 0.0:
            return float("inf")
        return float(self.baseline / (2.0 * np.tan(self.vergence / 2.0)))


@dataclass(frozen=True)
class Estimate:
    """A point estimate paired with its variance.

    The framework requires uncertainty to be first-class (CLAUDE.md §3): no layer
    returns a bare point estimate. ``value`` and ``variance`` share a shape;
    invalid entries are ``np.nan`` in both.
    """

    value: FloatArray
    variance: FloatArray

    def __post_init__(self) -> None:
        if self.value.shape != self.variance.shape:
            raise ValueError(
                f"shape mismatch: value {self.value.shape} vs variance {self.variance.shape}"
            )

    @property
    def valid(self) -> NDArray[np.bool_]:
        """Boolean mask of entries that are finite in both value and variance."""
        return np.isfinite(self.value) & np.isfinite(self.variance)

    @property
    def precision(self) -> FloatArray:
        """Inverse variance, with invalid entries set to zero (contribute nothing)."""
        out = np.zeros_like(self.variance)
        v = self.valid & (self.variance > 0)
        out[v] = 1.0 / self.variance[v]
        return out
