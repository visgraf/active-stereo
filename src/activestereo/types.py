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
class Fixation:
    """Binocular oculomotor state: where the eyes point, as gaze plus vergence.

    Attributes
    ----------
    azimuth : float
        Gaze azimuth, radians, cyclopean head frame. Positive = toward +X
        (rightward).
    elevation_down : float
        Gaze elevation, radians. Positive = downward (+Y), matching row
        growth in image coordinates. The sign is in the name deliberately:
        "elevation" alone is a sign-error trap, and this field must not be
        shortened.
    vergence : float
        Total vergence angle at the fixation point, radians. Zero is legal
        and means parallel gaze, fixation at infinity — the same convention
        as :attr:`StereoRig.vergence`.

    **Head frame.** Cyclopean origin between the eyes; +X right, +Y down,
    +Z forward. Right-handed, OpenCV-compatible. This is the reference-frame
    definition the fixation migration depends on (ADR-0013); every consumer
    of gaze angles reads them in this frame. Blender uses +Z up, so the
    Blender adapter converts at its own boundary — in
    ``scenes/blender.py`` / the ``rig.json`` loader, migration step 12 —
    never here.

    **Why (azimuth, elevation, vergence) and not two per-eye rotations.**
    This is Hering's decomposition into version (conjugate: both eyes
    together, ``azimuth``/``elevation_down``) and vergence (disjunctive: the
    eyes toward or away from each other). It is the control-regime closure
    expressed in the type: saccades are ballistic and act on version;
    vergence is feedback-controlled and acts on the third component. A pair
    of per-eye rotations — the rejected alternative — would destroy that
    separation and leave L5's two control regimes with no structural home,
    besides admitting states (Listing-violating torsion, non-intersecting
    gaze lines) that the framework holds to be non-physical.

    **Why torsion is not a field.** Per ADR-0013 torsion is *determined*,
    not free: it is computed from gaze and vergence by the binocular Listing
    law in ``geometry.oculomotor.eye_rotations(..., k)`` (ADR-0014). Its
    absence here is a decision, not an omission — do not "fix" it by adding
    a field. The Listing coefficient ``k`` is a property of the oculomotor
    plant, not of a fixation state, and therefore never becomes a field here
    either.

    The distance to the fixation point needs the baseline, so it is a
    property of (rig, fixation) jointly and lives in ``geometry.oculomotor``
    (migration step 3), not on this type.
    """

    azimuth: float
    elevation_down: float
    vergence: float

    def __post_init__(self) -> None:
        # Finiteness is checked explicitly for every field: a comparison
        # like `vergence < 0` is False for NaN, so a sign check alone would
        # silently admit NaN state.
        for name in ("azimuth", "elevation_down", "vergence"):
            value = getattr(self, name)
            if not np.isfinite(value):
                raise ValueError(f"{name} must be finite, got {value}")
        if self.vergence < 0:
            raise ValueError(f"vergence must be >= 0, got {self.vergence}")

    @classmethod
    def forward(cls, vergence: float) -> Fixation:
        """Straight-ahead fixation at the given vergence.

        The static-degradation path of ADR-0013: a non-refixable stimulus
        (photograph, existing render) is treated as viewed at
        ``Fixation.forward(rig.vergence)``. Load-bearing, not a convenience.
        """
        return cls(azimuth=0.0, elevation_down=0.0, vergence=vergence)


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
