"""Forward and inverse projection for a converged binocular rig.

Two models live here, deliberately side by side.

``depth_to_disparity`` / ``disparity_to_depth`` are the **off-axis** (shifted
frustum) capture model: two parallel optical axes with a horizontal image-plane
shift, zero-disparity locus a fronto-parallel plane. ADR-0007 chose it for
rendering, and it is what every existing stimulus in the repo was captured
under.

``project_toed_in`` / ``toed_in_disparity`` are the **toed-in** model: the eyes
rotate to converge, per ``geometry.oculomotor.eye_rotations``. Its zero-
horizontal-disparity locus is the Vieth-Muller circle -- exactly, for gaze in the
sagittal or horizontal plane (ADR-0016) -- and it produces vertical disparity,
which the off-axis model cannot. This is ADR-0007 item 4.

The two are not interchangeable and neither supersedes the other: the off-axis
model describes how the stimuli were made, the toed-in model describes how the
framework's eyes look at them.

Sign convention (CLAUDE.md §3): disparity is in pixels, left-image convention,
positive = crossed = nearer than the fixation point.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from activestereo.geometry.oculomotor import eye_rotations
from activestereo.types import Fixation, FloatArray, StereoRig


def depth_to_disparity(Z: FloatArray, rig: StereoRig) -> FloatArray:
    """Map metric depth to retinal disparity (the generative direction, L1).

    For a rig fixating at distance ``Zf``, a point at depth ``Z`` produces

        d = f * b * (1/Z - 1/Zf)

    which is zero on the horopter, positive (crossed) nearer than fixation and
    negative (uncrossed) beyond it. With ``vergence == 0``, ``Zf`` is infinite and
    this reduces to the familiar parallel-camera relation ``d = f b / Z``.

    Parameters
    ----------
    Z : array, metres, cyclopean frame. Non-positive entries yield ``nan``.
    rig : StereoRig

    Returns
    -------
    array of disparity in pixels; ``nan`` where ``Z`` was invalid.
    """
    Z = np.asarray(Z, dtype=float)
    out = np.full(Z.shape, np.nan, dtype=float)
    ok = np.isfinite(Z) & (Z > 0)
    inv_fix = 0.0 if not np.isfinite(rig.fixation_distance) else 1.0 / rig.fixation_distance
    out[ok] = rig.focal_px * rig.baseline * (1.0 / Z[ok] - inv_fix)
    return out


def disparity_to_depth(d: FloatArray, rig: StereoRig) -> FloatArray:
    """Invert :func:`depth_to_disparity`.

    Exact inverse; the *uncertainty* of this inversion is not handled here but in
    L4 (`activestereo.scaling`), per the scaling closure. Entries that invert to a
    non-positive or infinite depth are returned as ``nan``.
    """
    d = np.asarray(d, dtype=float)
    out = np.full(d.shape, np.nan, dtype=float)
    inv_fix = 0.0 if not np.isfinite(rig.fixation_distance) else 1.0 / rig.fixation_distance
    inv_Z = d / (rig.focal_px * rig.baseline) + inv_fix
    ok = np.isfinite(inv_Z) & (inv_Z > 0)
    out[ok] = 1.0 / inv_Z[ok]
    return out


@dataclass(frozen=True)
class BinocularProjection:
    """Image coordinates of one point set, in both eyes.

    Attributes
    ----------
    left, right : FloatArray
        ``(..., 2)`` pixel coordinates as ``(row, col)`` -- row first, origin
        top-left (CLAUDE.md section 3). Entries are ``np.nan`` in **both**
        components wherever the point is not imageable by that eye; never ``0``
        and never a sentinel float.

    A named pair rather than a tuple, for the reason :class:`~activestereo.
    geometry.oculomotor.EyeRotations` is one: a ``right, left = ...`` unpack
    swap is silent at the call site and no test downstream can see it.

    **Validity is eye-indexed, not a property of the 3-D point.** ``left`` and
    ``right`` go ``nan`` independently. The nodal points are a baseline apart
    and the eyes toe in, so the same point can be imageable by one eye and
    behind the other; a point is invalid *in an eye*, never simply invalid.

    This is easy to miss because it is invisible on the fixation axis: at
    sagittal gaze the two eyes are mirror images and their eye-frame depths for
    a given point are identical to machine precision. It appears only off-axis.
    At ``azimuth = 0.35`` rad, ``mu = 0.064``, the cyclopean origin lies
    +1.19e-2 m in front of the left eye and -9.99e-3 m behind the right.

    Consumers therefore carry **two** masks. Collapsing them into a single
    geometric validity mask and applying it to both images is an **ADR-0002
    violation with a plausible-looking cause**: the mask is right for one eye
    and wrong for the other, and every later operation that mixes pixels
    spatially -- blur, filter, downsample, warp -- spreads that error instead of
    excluding it. The collision is not hypothetical; it first bites at migration
    step 10, where synthesis back-warps into each eye's rectified geometry
    separately and the two eyes' valid sets genuinely differ.
    """

    left: FloatArray
    right: FloatArray


def _project_one_eye(
    points: FloatArray, rotation: FloatArray, centre: FloatArray, rig: StereoRig
) -> FloatArray:
    """Pinhole-project head-frame points into one eye.

    ``points`` ``(..., 3)`` metres in the cyclopean head frame; ``rotation`` the
    eye's head-frame orientation (``R``, mapping the reference eye frame into
    the fixated one, so ``R.T`` is the head->eye extrinsic and ``v = (P - C) @ R``
    is that product written for a last-axis point convention); ``centre``
    ``(3,)`` the eye's optical centre in metres. Returns ``(..., 2)`` (row, col)
    pixels, ``nan`` where ``v_z <= 0`` or the input was not finite.
    """
    v = (points - centre) @ rotation
    z = v[..., 2]
    ok = np.isfinite(v).all(axis=-1) & (z > 0.0)
    # Divide against 1.0 on the masked entries: the values are discarded by the
    # `where` below, and this keeps a point exactly on the nodal point from
    # raising a divide warning instead of yielding nan.
    safe_z = np.where(ok, z, 1.0)
    row = np.where(ok, rig.focal_px * v[..., 1] / safe_z + rig.principal_point[0], np.nan)
    col = np.where(ok, rig.focal_px * v[..., 0] / safe_z + rig.principal_point[1], np.nan)
    return np.stack((row, col), axis=-1)


def project_toed_in(
    points: FloatArray, rig: StereoRig, fixation: Fixation, k: float = 0.25
) -> BinocularProjection:
    """Project head-frame points into both eyes under toed-in geometry (L1).

    The generative direction for a rig whose eyes *rotate* to converge, as
    opposed to :func:`depth_to_disparity`'s shifted frustum. Per-eye orientations
    come from :func:`~activestereo.geometry.oculomotor.eye_rotations`, so torsion
    is determined by the binocular Listing law and never passed in (ADR-0013).

    Parameters
    ----------
    points : FloatArray
        ``(..., 3)`` metres, cyclopean head frame (+X right, +Y down, +Z
        forward). The trailing axis is the 3-vector, so an ``(H, W, 3)`` grid
        and an ``(N, 3)`` sample set are both accepted and return ``(H, W, 2)``
        and ``(N, 2)`` respectively.
    rig : StereoRig
        Supplies baseline, focal length and principal point. ``rig.vergence`` is
        **not** read -- the fixation state carries it (ADR-0013), and under that
        ADR a refixable rig has ``rig.vergence == 0``.
    fixation : Fixation
        Oculomotor state, radians, cyclopean head frame.
    k : float
        Listing-plane tilt coefficient, dimensionless (ADR-0014, ADR-0016).

    Returns
    -------
    BinocularProjection
        Per-eye ``(..., 2)`` (row, col) pixels; ``nan`` where a point falls
        behind an eye or the input was not finite.
    """
    points = np.asarray(points, dtype=float)
    if points.shape[-1] != 3:
        raise ValueError(f"points must have a trailing axis of length 3, got {points.shape}")
    rotations = eye_rotations(rig, fixation, k=k)
    half_b = rig.baseline / 2.0
    return BinocularProjection(
        left=_project_one_eye(points, rotations.left, np.array([-half_b, 0.0, 0.0]), rig),
        right=_project_one_eye(points, rotations.right, np.array([half_b, 0.0, 0.0]), rig),
    )


def toed_in_disparity(
    points: FloatArray, rig: StereoRig, fixation: Fixation, k: float = 0.25
) -> tuple[FloatArray, FloatArray]:
    """Horizontal and vertical disparity under toed-in geometry, in pixels.

    Returns
    -------
    (d_h, d_v) : FloatArray, FloatArray
        Both ``points.shape[:-1]``, pixels, ``nan`` wherever either eye's
        projection is invalid.

        ``d_h = col_L - col_R`` follows the existing convention (CLAUDE.md
        section 3): left-image convention, positive = crossed = nearer than the
        fixation point, so it agrees in sign with :func:`depth_to_disparity`.

        ``d_v = row_L - row_R`` is a **new quantity**, and this is the one place
        its convention is defined: positive means the point images *lower* in
        the left eye than in the right, rows growing downward. It is identically
        zero for the off-axis model and is the reason ADR-0007 item 4 existed.

    Zero on the Vieth-Muller circle -- exactly for ``azimuth == 0`` or
    ``elevation_down == 0``, and to within the residual quantified in ADR-0016
    otherwise. ``d_v`` is *not* zero there and is not meant to be.
    """
    projection = project_toed_in(points, rig, fixation, k=k)
    d_h = projection.left[..., 1] - projection.right[..., 1]
    d_v = projection.left[..., 0] - projection.right[..., 0]
    return d_h, d_v
