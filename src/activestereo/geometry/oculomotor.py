"""L1 — oculomotor geometry: gaze becomes SO(3) here and nowhere else.

Per ADR-0013 the third rotational DOF of each eye (torsion) is determined,
not stored: :func:`eye_rotations` computes it from gaze and vergence by the
binocular extension of Listing's law, with the Listing-plane tilt
coefficient ``k`` as a parameter (ADR-0014; ``k = 0`` is strict Listing,
``k = 0.25`` the default).

Frames and units (CLAUDE.md section 3): cyclopean head frame, +X right,
+Y down, +Z forward, right-handed; angles in radians, distances in metres.
Gaze angles compose in **Helmholtz order** (ADR-0015): elevation about the
interaural X axis first, azimuth within the elevated plane. Consequence:
the plane of regard (through both eyes and the fixation point) is exactly
the elevated plane for every azimuth, which is what makes the fixation
geometry below closed-form.

Domain: ``fixation.azimuth`` must lie in (-pi/2, pi/2) — the fixation
point must be forward of the interaural axis. Beyond it, the chord
construction in :func:`fixation_distance` lands on the minor arc of the
Vieth-Muller circle, where the inscribed angle is ``pi - vergence``, and
the returned geometry would be silently wrong; the functions raise
``ValueError`` instead.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from activestereo.types import Fixation, FloatArray, StereoRig

_Z = np.array([0.0, 0.0, 1.0])


@dataclass(frozen=True)
class EyeRotations:
    """Head-frame orientations of the two eyes under a fixation.

    Attributes
    ----------
    left, right : FloatArray
        ``(3, 3)`` rotation matrices, dimensionless, cyclopean head frame
        (+X right, +Y down, +Z forward). ``R`` maps the reference
        (straight-ahead) eye frame into the fixated one; the eye's optical
        axis in the head frame is ``R @ [0, 0, 1]``. Camera extrinsics
        (head -> eye) for the toed-in projection and rectification
        (migration steps 4 and 6) use ``R.T``.

    A named pair rather than a tuple: an ``R_right, R_left = ...`` unpack
    swap is silent at the call site, and the sagittal-mirror test cannot
    see a swap that happens outside this module.
    """

    left: FloatArray
    right: FloatArray


def require_forward_azimuth(fixation: Fixation) -> None:
    """Raise unless ``fixation.azimuth`` lies in (-pi/2, pi/2).

    Public because ``geometry/horopter.py`` needs the same domain, and the
    alternative -- each module re-validating locally -- would put a second
    copy of this rule and its error message in L1. The domain is a property
    of the Vieth-Muller chord construction, not of any one function that
    uses it.
    """
    if not abs(fixation.azimuth) < np.pi / 2.0:
        raise ValueError(
            f"azimuth must lie in (-pi/2, pi/2), got {fixation.azimuth}: the fixation "
            "point must be forward of the interaural axis (beyond it the Vieth-Muller "
            "chord subtends pi - vergence instead of vergence)"
        )


def _cyclopean_direction(fixation: Fixation) -> FloatArray:
    """Unit gaze direction of the cyclopean eye, head frame, Helmholtz order (ADR-0015)."""
    az, el = fixation.azimuth, fixation.elevation_down
    return np.array([np.sin(az), np.cos(az) * np.sin(el), np.cos(az) * np.cos(el)])


def _shortest_arc(p: FloatArray, g: FloatArray) -> FloatArray:
    """Rotation taking unit vector ``p`` to unit vector ``g`` about the axis ``p x g``.

    Trig-free exact Rodrigues form ``R = I + [v]x + [v]x^2 / (1 + c)`` with
    ``v = p x g``, ``c = p . g``: no ``acos``-near-1 precision loss, and
    ``g == p`` yields exactly the identity with no branch. The axis is
    undefined at ``c = -1``, so that neighbourhood raises.
    """
    v = np.cross(p, g)
    c = float(p @ g)
    if 1.0 + c < 1e-9:
        raise ValueError("gaze direction is antiparallel to the primary direction")
    V = np.array([[0.0, -v[2], v[1]], [v[2], 0.0, -v[0]], [-v[1], v[0], 0.0]])
    return np.eye(3) + V + (V @ V) / (1.0 + c)


def fixation_distance(rig: StereoRig, fixation: Fixation) -> float:
    """Distance from the cyclopean origin to the fixation point, metres.

    Exact, via the Vieth-Muller chord in the plane of regard (which, under
    Helmholtz composition, contains the baseline for every azimuth — so
    elevation does not enter): with ``h = (b/2) / tan(mu)`` the circle
    centre's height and ``az`` the azimuth,

        D = h cos(az) + sqrt(h^2 cos^2(az) + (b/2)^2)

    Returns ``inf`` at zero vergence (parallel gaze, fixation at infinity).
    At azimuth 0 this reduces exactly to ``b / (2 tan(mu/2))``, the same
    formula as :attr:`StereoRig.fixation_distance` — the two conventions
    agree on the forward axis by construction.
    """
    require_forward_azimuth(fixation)
    mu = fixation.vergence
    if mu <= 0.0:
        return float("inf")
    half_b = rig.baseline / 2.0
    h = half_b / np.tan(mu)
    ca = np.cos(fixation.azimuth)
    return float(h * ca + np.sqrt(h * h * ca * ca + half_b * half_b))


def fixation_point(rig: StereoRig, fixation: Fixation) -> FloatArray:
    """Fixation point, ``(3,)`` metres, cyclopean head frame (+Z forward).

    Raises ``ValueError`` at zero vergence: the point is at infinity, and
    an inf-valued vector is a NaN trap under any subsequent arithmetic.
    Callers needing the parallel-gaze limit should work with the gaze
    direction instead, which is what :func:`eye_rotations` does internally.
    """
    require_forward_azimuth(fixation)
    if fixation.vergence <= 0.0:
        raise ValueError("fixation point is at infinity at zero vergence")
    return fixation_distance(rig, fixation) * _cyclopean_direction(fixation)


def eye_rotations(rig: StereoRig, fixation: Fixation, k: float = 0.25) -> EyeRotations:
    """Per-eye orientations under the binocular Listing law (L2) with tilt ``k``.

    Torsion is determined, not free (ADR-0013). Each eye's primary
    direction ``p_e`` is straight ahead tilted *temporally* (away from the
    nose: -X for the left eye, +X for the right) by ``k * vergence`` — the
    only place ``k`` enters (ADR-0014). The orientation is the shortest-arc
    displacement from the primary orientation:

        R_e = A(p_e -> g_e) @ A(z -> p_e)        # maps z -> p_e -> g_e

    where ``g_e`` is the unit vector from the eye's optical centre to the
    fixation point (both eyes' gaze at zero vergence is the cyclopean
    direction — the parallel-gaze limit, no singularity). The displacement
    axis ``p_e x g_e`` is perpendicular to ``p_e`` by construction, i.e.
    lies in the tilted Listing plane; for an axis n perpendicular to p
    taking p to g, ``g . n = 0`` forces ``n || p x g``, so the shortest arc
    is the *unique* Listing-compatible displacement. ``k = 0`` gives
    ``p_e = z``, the second factor collapses to the identity, and strict
    Listing holds with no branch. The second factor is the primary
    orientation — a pure temporal yaw with no torsional component, since
    ``p_e`` lies in the horizontal plane; omitting it mis-points the
    optical axis by ~ ``k * vergence`` (13-32 px at project scales), which
    the gaze-lines-intersect test pins.

    Parameters
    ----------
    rig : StereoRig
        Supplies the baseline (metres) only. ``rig.vergence`` — the capture
        convergence of static stimuli — is never read here; the static path
        passes ``Fixation.forward(rig.vergence)`` explicitly (ADR-0013).
    fixation : Fixation
        Oculomotor state, radians, cyclopean head frame.
    k : float
        Temporal tilt of each eye's Listing plane per radian of vergence,
        dimensionless. Default 0.25 (ADR-0014). Deliberately not
        range-restricted: the ADR-0014 sweep must be free to explore.

    Returns
    -------
    EyeRotations
        Head-frame rotation matrices; see the class docstring for the
        mapping convention.
    """
    if not np.isfinite(k):
        raise ValueError(f"k must be finite, got {k}")
    require_forward_azimuth(fixation)
    mu = fixation.vergence
    s, c = np.sin(k * mu), np.cos(k * mu)
    p_left = np.array([-s, 0.0, c])
    p_right = np.array([s, 0.0, c])
    if mu <= 0.0:
        g_left = g_right = _cyclopean_direction(fixation)
    else:
        point = fixation_point(rig, fixation)
        half_b = rig.baseline / 2.0
        g_left = point - np.array([-half_b, 0.0, 0.0])
        g_left = g_left / np.linalg.norm(g_left)
        g_right = point - np.array([half_b, 0.0, 0.0])
        g_right = g_right / np.linalg.norm(g_right)
    return EyeRotations(
        left=_shortest_arc(p_left, g_left) @ _shortest_arc(_Z, p_left),
        right=_shortest_arc(p_right, g_right) @ _shortest_arc(_Z, p_right),
    )
