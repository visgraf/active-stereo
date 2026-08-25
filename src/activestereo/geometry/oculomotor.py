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

from activestereo.types import (
    Estimate,
    Fixation,
    FixationProposal,
    FloatArray,
    RefusalReason,
    StereoRig,
    TargetRefused,
)

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


def rectification_rotation(fixation: Fixation) -> FloatArray:
    """Rotation from the rectified frame into the head frame, shared by both eyes.

    The Helmholtz version rotation (ADR-0015) with **azimuth zeroed** --
    ``helmholtz_rotation(0, fixation.elevation_down)`` in the sense of
    ``tests/unit/test_oculomotor.py``. Dimensionless, ``(3, 3)``.

    **Direction: rect -> head**, the same convention as :class:`EyeRotations`
    (``R @ [0, 0, 1]`` is the frame's optical axis in the head frame), so
    consumers project with ``R.T`` exactly as ``projection._project_one_eye``
    does. Stated with the matrix rather than apart from it: the matrix is
    unambiguous and a direction sentence is the only part that can be wrong.

    **Azimuth-independent by construction**, not by assertion: under Helmholtz
    composition the plane of regard is the elevated plane for *every* azimuth
    (ADR-0015), so zeroing azimuth loses nothing. Independent of vergence and of
    the rig. ``k`` is not an input at all -- that is triviality, not robustness,
    and ADR-0017 says so rather than letting a reader infer a swept invariance.

    Both eyes share it, and their optical centres differ along the head ``+X``
    axis, which this rotation fixes; that is what makes vertical disparity
    identically zero in the pair it induces.

    Determined only up to a rotation about the baseline. This member is chosen
    because it puts the **plane of regard on the principal row** (ADR-0016's
    criterion restated; recorded as ADR-0017). Every other member rectifies
    equally well and differs only in where the fixation point lands.
    """
    el = fixation.elevation_down
    c, s = np.cos(el), np.sin(el)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, s], [0.0, -s, c]])


def is_forward_gaze(fixation: Fixation) -> bool:
    """Whether the cyclopean gaze direction points forward of the interaural plane.

    ``True`` iff ``cos(azimuth) * cos(elevation_down) > 0``, i.e. the ``+Z``
    component of :func:`_cyclopean_direction` is positive.

    **Why this is additive and not a tightening of anything.** ``Fixation``
    validates finiteness and ``vergence >= 0`` only, so
    ``Fixation(0.1, 2.0, 0.064)`` -- elevation past ``pi/2``, a point *behind*
    the head -- is constructible, and ``fixation_distance``, ``fixation_point``
    and ``eye_rotations`` all accept it without raising, returning a well-formed
    orthonormal rotation that points backward. :func:`require_forward_azimuth`
    cannot catch it: it is a statement about azimuth, and elevation is the free
    direction.

    Nor is this a restatement of that guard. ``require_forward_azimuth`` exists
    because the Vieth-Muller chord lands on the minor arc beyond ``|az| = pi/2``,
    where the inscribed angle is ``pi - vergence``; this predicate is about the
    gaze direction being forward at all. The domains coincide; the failures do
    not.

    The boundary itself is not adjudicated and does not need to be: ``np.pi/2``
    is not pi/2, so ``cos`` of it is ``+6.1e-17`` and that state reads as
    degenerately forward. The failure this exists to catch is gaze that is
    unambiguously backward.

    **This is the geometry test, not the angle test, and the difference is not
    cosmetic.** ``abs(el) < pi/2`` agrees with it everywhere except at that
    boundary and on *wrapped* elevations, where the two disagree outright: at
    ``el = 7.0`` -- which wraps to 0.7168, plainly forward -- the angle test says
    backward. Constructed fixations never wrap (``atan2`` returns in
    ``(-pi, pi]``), but ``current`` can be hand-written or loaded from a config.
    Do not "simplify" this to a comparison on the angle.

    A **predicate, not a raiser**, because its first caller
    (:func:`target_to_fixation`) must *refuse* rather than raise -- a bad target
    must not kill the active loop. A raising wrapper belongs with the first
    consumer that wants the loud form, not here as dead code.
    """
    return bool(_cyclopean_direction(fixation)[2] > 0.0)


def target_to_fixation(
    target_px: tuple[int, int],
    depth_at_target: Estimate,
    rig: StereoRig,
    current: Fixation,
) -> FixationProposal | TargetRefused:
    """Turn an L6 pixel target into an oculomotor state (ADR-0013's single boundary).

    The **only** place a pixel becomes a rotation. L6 keeps selecting
    ``(row, col)``; this converts it, and nothing else may.

    Parameters
    ----------
    target_px : (row, col)
        Integer pixel in the **rectified left** image, origin top-left
        (CLAUDE.md section 3). Out of bounds raises -- that is a caller error.
    depth_at_target : Estimate
        The belief's depth **field**, ``(H, W)``, metres, indexed here rather
        than by the caller so that an invalid entry becomes a refusal instead of
        being silently dropped upstream. Field-shaped rather than scalar because
        ``StereoRig`` carries no image dimensions, so this is the only thing that
        makes the bounds check above possible at all.

        Never a bare float (ADR-0013): the target is peripheral *by
        construction* -- L6 selects for uncertainty -- and ADR-0003 declares
        peripheral depth untrustworthy, so the returned fixation is explicitly a
        **coarse prior that L5 corrects post-saccade**.
    rig : StereoRig
        Baseline, focal length, principal point. ``rig.vergence`` is not read;
        the fixation state carries it (ADR-0013).
    current : Fixation
        The oculomotor state the target was *observed* under. Supplies the
        rectification rotation, so it is load-bearing, not context.

    Returns
    -------
    FixationProposal | TargetRefused
        Narrow before use. See :class:`~activestereo.types.RefusalReason` for
        why refusal is a set of kinds rather than a bare ``None``.

    Raises
    ------
    ValueError
        Caller errors only: non-integral or out-of-bounds ``target_px``, a
        non-2-D ``depth_at_target``. Data-quality problems -- an unusable depth,
        a point too near, a backward gaze -- are **refused, not raised**: a
        raise kills the active loop on one bad estimate, and exp008 must be able
        to *count* bad targets rather than crash on them.

    Notes
    -----
    **Depth frame -- and a contradiction with CLAUDE.md section 3 that section 3
    loses.** ``depth_at_target`` is ``z`` in the **rectified left-camera frame**,
    which is what L4 actually returns: for a rectified pair ``d = f b / z``, and
    ``scaling`` inverts exactly that. CLAUDE.md section 3 says depth ``Z`` is
    "metres, cyclopean frame". **That invariant is false**, and it is section 3
    that is wrong, not this function. The two coincide only at
    ``elevation_down == 0`` -- every stimulus in the repo today -- which is why
    nothing has caught it. Rectified-camera ``z`` is additionally
    *fixation-dependent*: the same world point has a different bare ``Z`` at
    different fixations, so ground-truth comparison needs a stated frame once
    ``el != 0``. Registered for a section 3 amendment or its own ADR before
    migration step 8; see ``docs/lab-notebook/2026-08-25-step-5-target-to-fixation.md``.

    **Unprojection is about the LEFT optical centre**, ``(-b/2, 0, 0)``, not the
    cyclopean origin -- disparity is left-image convention. At the image centre,
    ``Fixation.forward(0.064)`` and ``Z = 1.5``, the two differ by 0.0213 rad
    (17 px at ``f = 800``), so this is not a rounding-level distinction.

    **The returned variance inherits the exp004/exp006 anti-calibration.** The
    propagation below is a correct first-order derivative; its *input* is a
    miscalibrated variance channel, and downstream the two are indistinguishable.
    A correct derivative of a miscalibrated quantity is still miscalibrated. Step
    8's ``CyclopeanBelief`` compounds it under recursion, which is what exp008
    exists to measure.

    **Depth versus inverse-depth propagation** agree to first order identically.
    They diverge in the second moment, and only under one parameterisation --
    which makes the divergence a property of the assumed distribution, not of the
    geometry. Numbers and harness in the notebook entry above; they are not
    reproduced here because nothing regenerates a docstring table.
    """
    value, variance = depth_at_target.value, depth_at_target.variance
    if value.ndim != 2:
        raise ValueError(f"depth_at_target must be a 2-D field, got shape {value.shape}")
    row, col = target_px
    if row != int(row) or col != int(col):
        raise ValueError(f"target_px must be integral pixel indices, got {target_px}")
    row, col = int(row), int(col)
    height, width = value.shape
    if not (0 <= row < height and 0 <= col < width):
        raise ValueError(f"target_px {target_px} is outside the {height}x{width} field")

    # --- Gate: without a usable depth nothing downstream exists to test. ---
    depth = float(value[row, col])
    if not (np.isfinite(depth) and np.isfinite(variance[row, col])):
        return TargetRefused(frozenset({RefusalReason.DEPTH_UNAVAILABLE}))
    if depth <= 0.0:
        return TargetRefused(frozenset({RefusalReason.DEPTH_NONPOSITIVE}))

    half_b = rig.baseline / 2.0
    centre_left = np.array([-half_b, 0.0, 0.0])
    # Ray direction with unit z in the rectified frame, rotated into the head frame.
    ray = rectification_rotation(current) @ np.array(
        [
            (col - rig.principal_point[1]) / rig.focal_px,
            (row - rig.principal_point[0]) / rig.focal_px,
            1.0,
        ]
    )
    point = centre_left + depth * ray
    distance = float(np.linalg.norm(point))
    sin_az = point[0] / distance
    azimuth = float(np.arcsin(sin_az))
    elevation = float(np.arctan2(point[1], point[2]))

    # --- Independent conditions: neither ranks the other, so both are reported.
    # Elevation needs no depth at all (el = current.el + atan((row - pp_row)/f)),
    # so a backward target is refused even under a perfect depth estimate.
    reasons = set()
    if not is_forward_gaze(Fixation(azimuth, elevation, 0.0)):
        reasons.add(RefusalReason.BACKWARD_GAZE)
    # Must precede Fixation construction: below b/2 the arctan below takes the
    # far branch and returns a negative angle, which Fixation rejects with a
    # ValueError -- a raise escaping where a refusal is required.
    if distance <= half_b:
        reasons.add(RefusalReason.TOO_NEAR)
    if reasons:
        return TargetRefused(frozenset(reasons))

    cos_az = np.cos(azimuth)
    numer = rig.baseline * distance * cos_az
    denom = distance * distance - half_b * half_b
    vergence = float(np.arctan(numer / denom))

    # First-order propagation. Depth enters through both the distance and the
    # azimuth -- the left-centre offset makes azimuth depth-dependent, so the
    # chain rule has two branches and dropping either is a silent factor error.
    #   dD/dZ  = (P . m) / D
    #   daz/dZ = (m_x D - P_x dD/dZ) / (D^2 sqrt(1 - sin_az^2))
    #   dmu/dZ = (M dN/dZ - N dM/dZ) / (M^2 + N^2),  N = b D cos(az), M = D^2 - (b/2)^2
    d_distance = float(point @ ray) / distance
    d_azimuth = (ray[0] * distance - point[0] * d_distance) / (
        distance * distance * np.sqrt(1.0 - sin_az * sin_az)
    )
    d_numer = rig.baseline * (cos_az * d_distance - distance * np.sin(azimuth) * d_azimuth)
    d_denom = 2.0 * distance * d_distance
    jac = (denom * d_numer - numer * d_denom) / (denom * denom + numer * numer)
    vergence_variance = float(jac * jac * variance[row, col])

    return FixationProposal(
        fixation=Fixation(azimuth, elevation, vergence),
        vergence_variance=vergence_variance,
    )
