"""The Vieth-Muller circle: the zero-disparity locus of a *toed-in* rig.

IMPORTANT (ADR-0007): this is **not** the horopter of the rig that
`geometry/projection.py` models. That module implements a shifted-frustum
(off-axis) projection, whose zero-disparity locus is a fronto-parallel plane at
the fixation distance. The two agree near the fixation axis and diverge with
eccentricity.

The circle is kept because it is the correct target for a framework claiming to
model biological stereopsis. Treat it as documentation of where L1 is heading,
not as a description of what L1 currently does.

For a rig with baseline ``b`` fixating at total vergence angle ``mu``, the
theoretical horopter is the circle through both nodal points and the fixation
point. By the inscribed-angle theorem its radius is

    R = b / (2 sin mu)

and its centre lies on the perpendicular bisector of the baseline.
"""

from __future__ import annotations

import numpy as np

from activestereo.types import FloatArray, StereoRig


def vieth_muller_radius(rig: StereoRig) -> float:
    """Radius of the Vieth-Muller circle in metres; ``inf`` at zero vergence."""
    if rig.vergence <= 0.0:
        return float("inf")
    return float(rig.baseline / (2.0 * np.sin(rig.vergence)))


def vieth_muller_circle(rig: StereoRig, n: int = 256) -> tuple[FloatArray, FloatArray]:
    """Sample the horopter in the cyclopean XZ plane.

    Returns
    -------
    (X, Z) : arrays of metres, cyclopean frame, ``+Z`` forward. For zero vergence
    the horopter degenerates to the plane at infinity and ``Z`` is all ``inf``.
    """
    if rig.vergence <= 0.0:
        X = np.linspace(-1.0, 1.0, n)
        return X, np.full(n, np.inf)

    R = vieth_muller_radius(rig)
    # Centre on the +Z perpendicular bisector, at height h above the baseline.
    h = np.sqrt(max(R**2 - (rig.baseline / 2.0) ** 2, 0.0))
    theta = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
    X = R * np.cos(theta)
    Z = h + R * np.sin(theta)
    return X, Z
