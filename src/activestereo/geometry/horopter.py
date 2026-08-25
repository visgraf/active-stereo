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

from activestereo.geometry.oculomotor import _require_forward_azimuth
from activestereo.types import Fixation, FloatArray, StereoRig


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


def vieth_muller_points(rig: StereoRig, fixation: Fixation, azimuths: FloatArray) -> FloatArray:
    """Sample the Vieth-Muller circle of a ``(rig, fixation)`` pair.

    Returns
    -------
    FloatArray
        ``(..., 3)`` **metres, cyclopean head frame** (+X right, +Y down, +Z
        forward), shaped ``azimuths.shape + (3,)``.

    The returned points lie in the **plane of regard**, not the XZ plane. Under
    Helmholtz composition (ADR-0015) the plane of regard at elevation ``el`` is
    the horizontal plane rotated about the interaural +X axis until +Z reaches
    ``(0, sin el, cos el)``, and it contains the baseline at every azimuth. That
    rotation is applied **here**, on purpose: a function that took a ``Fixation``
    and returned XZ samples would silently discard ``elevation_down``, and a
    caller applying the rotation itself would be re-deriving a reference frame
    outside ``geometry.oculomotor``, which ADR-0015's consequences clause
    forbids.

    Parameters
    ----------
    rig : StereoRig
        Supplies the **baseline only**. See the vergence note below.
    fixation : Fixation
        Supplies vergence (which circle) and ``elevation_down`` (which plane).
        Its ``azimuth`` does not affect the locus -- the circle is the same for
        every forward gaze azimuth -- but is domain-checked, because the
        fixation point is required to lie *on* the returned circle.
    azimuths : FloatArray
        In-plane azimuths, radians, measured within the plane of regard from
        straight ahead, each in ``(-pi/2, pi/2)``. Required rather than defaulted:
        a sampling extent is a caller's choice, and a default here would put an
        arbitrary constant in the library.

    **Which vergence field this reads.** ``fixation.vergence``, never
    ``rig.vergence`` -- stated explicitly because :func:`vieth_muller_radius` in
    this same module reads the other one. Under ADR-0013 a refixable rig has
    ``rig.vergence == 0``, so a version of this function reading the rig would
    return a degenerate circle at infinity for exactly the stimuli the toed-in
    model is for, and any zero-disparity test built on it would pass vacuously
    (``docs/plans/fixation-migration.md`` lines 69-85).

    Raises ``ValueError`` at zero vergence rather than returning ``inf``: the
    circle degenerates to the plane at infinity there, and an inf-valued point
    array is a NaN trap under any subsequent arithmetic -- the same rationale as
    :func:`~activestereo.geometry.oculomotor.fixation_point`.

    Equivalent, by construction, to sweeping
    :func:`~activestereo.geometry.oculomotor.fixation_point` over ``azimuths`` at
    fixed vergence and elevation: the chord length at in-plane azimuth ``a`` is
    ``D = h cos a + sqrt(h^2 cos^2 a + (b/2)^2)`` with ``h = (b/2)/tan mu``, which
    is exactly that function's closed form.
    """
    _require_forward_azimuth(fixation)
    mu = fixation.vergence
    if mu <= 0.0:
        raise ValueError(
            "the Vieth-Muller circle is degenerate at zero vergence (fixation at "
            "infinity); pass a fixation with vergence > 0"
        )
    a = np.asarray(azimuths, dtype=float)
    if not np.isfinite(a).all():
        raise ValueError("azimuths must all be finite")
    if not (np.abs(a) < np.pi / 2.0).all():
        raise ValueError(
            "azimuths must lie in (-pi/2, pi/2): beyond it the chord construction "
            "lands on the minor arc, where the inscribed angle is pi - vergence"
        )
    half_b = rig.baseline / 2.0
    h = half_b / np.tan(mu)
    el = fixation.elevation_down
    interaural = np.array([1.0, 0.0, 0.0])
    forward = np.array([0.0, np.sin(el), np.cos(el)])
    cos_a = np.cos(a)
    distance = h * cos_a + np.sqrt(h * h * cos_a * cos_a + half_b * half_b)
    direction = np.sin(a)[..., None] * interaural + cos_a[..., None] * forward
    return distance[..., None] * direction
