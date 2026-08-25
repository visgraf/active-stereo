"""L1 — oculomotor geometry: eye rotations under the binocular Listing law.

The shortest-arc and torsion helpers here are deliberately test-local
reimplementations: comparing the module against its own internals is the
vacuity trap (the exp001 exactly-0.0-foveal-MAE failure shape).
"""

import dataclasses
import itertools
import os
import pathlib
import subprocess
import sys

import numpy as np
import pytest

from activestereo.geometry import (
    EyeRotations,
    eye_rotations,
    fixation_distance,
    fixation_point,
    is_forward_gaze,
    rectification_rotation,
    target_to_fixation,
)
from activestereo.types import (
    Estimate,
    Fixation,
    FixationProposal,
    RefusalReason,
    StereoRig,
    TargetRefused,
)

Z = np.array([0.0, 0.0, 1.0])

# Sweep grid shared by several tests. Radians; spans the project's stimulus
# scales (image edge ~0.2 rad at f=800, vergence 0.16 rad at the 0.4 m near
# limit of configs/default.yaml's depth_range).
AZIMUTHS = (-0.25, 0.0, 0.13, 0.25)
ELEVATIONS = (-0.2, 0.0, 0.11, 0.2)
VERGENCES = (0.0, 0.02, 0.064, 0.16)
KS = (0.0, 0.1, 0.25)


def arc(p, g):
    """Reference shortest-arc rotation p -> g (independent reimplementation)."""
    v = np.cross(p, g)
    V = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]], dtype=float)
    return np.eye(3) + V + V @ V / (1.0 + p @ g)


def torsion(R):
    """Signed twist of R about its own gaze g = R z, relative to strict Listing.

    Decomposes R = twist(tau about g) @ arc(z -> g); tau > 0 is right-handed
    about +g. Sign mapping (head frame +X right, +Y down, +Z forward, gaze
    near +Z): tau > 0 carries the top of the eye (-Y) toward +X.
    """
    g = R @ Z
    T = R @ arc(Z, g).T
    angle = np.arccos(np.clip((np.trace(T) - 1.0) / 2.0, -1.0, 1.0))
    if angle < 1e-14:
        return 0.0
    axis = np.array([T[2, 1] - T[1, 2], T[0, 2] - T[2, 0], T[1, 0] - T[0, 1]])
    return float(angle * np.sign(axis @ g))


def helmholtz(az, el):
    """Cyclopean direction, Helmholtz order (ADR-0015), test-local copy."""
    return np.array([np.sin(az), np.cos(az) * np.sin(el), np.cos(az) * np.cos(el)])


def eye_gazes(rig, fx):
    """Unit gaze directions (left, right) from eye centres to the fixation point."""
    if fx.vergence == 0.0:
        d = helmholtz(fx.azimuth, fx.elevation_down)
        return d, d
    P = fixation_point(rig, fx)
    gl = P - np.array([-rig.baseline / 2.0, 0.0, 0.0])
    gr = P - np.array([rig.baseline / 2.0, 0.0, 0.0])
    return gl / np.linalg.norm(gl), gr / np.linalg.norm(gr)


def test_k0_reduces_to_strict_listing(rig):
    """k = 0: each eye's orientation is the shortest arc from straight ahead."""
    for az, el, mu in itertools.product(AZIMUTHS, ELEVATIONS, VERGENCES):
        fx = Fixation(az, el, mu)
        rot = eye_rotations(rig, fx, k=0.0)
        gl, gr = eye_gazes(rig, fx)
        np.testing.assert_allclose(rot.left, arc(Z, gl), atol=1e-12)
        np.testing.assert_allclose(rot.right, arc(Z, gr), atol=1e-12)


def test_horizontal_plane_fixation_is_pure_yaw(rig):
    """el = 0: everything stays in the plane of regard; zero torsion at ANY k."""
    for az, mu, k in itertools.product((0.0, -0.15, 0.15), (0.0, 0.064, 0.16), (0.0, 0.25)):
        rot = eye_rotations(rig, Fixation(az, 0.0, mu), k=k)
        for R in (rot.left, rot.right):
            np.testing.assert_allclose(R[1, :], [0.0, 1.0, 0.0], atol=1e-15)
            np.testing.assert_allclose(R[:, 1], [0.0, 1.0, 0.0], atol=1e-15)
            assert torsion(R) == 0.0


def test_elevation_dependent_torsion_signs(rig):
    """ADR-0014's observable: intorsion for upward proximal gaze, extorsion
    for downward, opposite in sign between the eyes.

    Sign mapping, spelled out: tau > 0 (right-handed about the gaze, which
    is near +Z) carries the top of the eye (-Y, since +Y is down) toward
    +X. +X is nasal for the left eye (at -X) and temporal for the right,
    so intorsion means tau_L > 0 and tau_R < 0; extorsion is the reverse.
    az = 0 keeps |tau_L| = |tau_R| by mirror symmetry. The magnitude floor
    keeps the test from passing on numerical dust.
    """
    k = 0.25
    for el, expect_up in ((-0.149, True), (0.149, False)):
        rot = eye_rotations(rig, Fixation(0.0, el, 0.0914), k=k)
        tau_left, tau_right = torsion(rot.left), torsion(rot.right)
        assert abs(tau_left) > 1e-4 and abs(tau_right) > 1e-4
        assert tau_left == pytest.approx(-tau_right, rel=1e-9)
        if expect_up:
            assert tau_left > 0 and tau_right < 0  # intorsion
        else:
            assert tau_left < 0 and tau_right > 0  # extorsion
    magnitudes = [
        abs(torsion(eye_rotations(rig, Fixation(0.0, 0.149, mu), k=k).left))
        for mu in (0.064, 0.0914, 0.16)
    ]
    assert magnitudes[0] < magnitudes[1] < magnitudes[2]


def test_rotation_matrices_are_special_orthogonal(rig):
    for az, el, mu, k in itertools.product(AZIMUTHS, ELEVATIONS, VERGENCES, KS):
        rot = eye_rotations(rig, Fixation(az, el, mu), k=k)
        for R in (rot.left, rot.right):
            np.testing.assert_allclose(R @ R.T, np.eye(3), atol=1e-12)
            assert np.linalg.det(R) == pytest.approx(1.0, abs=1e-12)


def test_gaze_lines_intersect_the_fixation_point(rig):
    """The geometric definition of fixation, and the strongest test here:
    it is convention-independent, and it fails by 13-32 px of optical-axis
    error if the primary-orientation factor A(z -> p_e) is dropped."""
    for az, el, mu, k in itertools.product(AZIMUTHS, ELEVATIONS, (0.02, 0.064, 0.16), KS):
        fx = Fixation(az, el, mu)
        P = fixation_point(rig, fx)
        rot = eye_rotations(rig, fx, k=k)
        gaze = []
        for R, ex in ((rot.left, -rig.baseline / 2.0), (rot.right, rig.baseline / 2.0)):
            eye = np.array([ex, 0.0, 0.0])
            u = R @ Z
            gaze.append(u)
            perpendicular = (P - eye) - ((P - eye) @ u) * u
            assert np.linalg.norm(perpendicular) < 1e-12  # metres
        recovered = np.arccos(np.clip(gaze[0] @ gaze[1], -1.0, 1.0))
        assert recovered == pytest.approx(mu, rel=1e-9)


def test_sagittal_mirror_symmetry(rig):
    """At az = 0 the two eyes are mirror images through the X -> -X plane;
    catches sign errors asymmetric between the eyes, which symmetric-
    fixation tests cannot see."""
    M = np.diag([-1.0, 1.0, 1.0])
    for el, mu, k in itertools.product(ELEVATIONS, VERGENCES, KS):
        rot = eye_rotations(rig, Fixation(0.0, el, mu), k=k)
        np.testing.assert_allclose(M @ rot.left @ M, rot.right, atol=1e-12)


def test_handedness_anchors(rig):
    """Pin the frame rather than assume it: +X right, +Y DOWN, +Z forward is
    right-handed, and Y-down inverts the intuitive sense of rotations about
    the vertical axis."""
    rot = eye_rotations(rig, Fixation(0.2, 0.0, 0.0914))
    for g in (rot.left @ Z, rot.right @ Z):
        assert g[0] > 0  # positive azimuth -> rightward (+X)
    rot = eye_rotations(rig, Fixation(0.0, 0.15, 0.0914))
    for g in (rot.left @ Z, rot.right @ Z):
        assert g[1] > 0  # positive elevation_down -> downward (+Y)
    rot = eye_rotations(rig, Fixation(0.2, 0.15, 0.0))  # cyclopean direction itself
    g = rot.left @ Z
    assert g[0] > 0 and g[1] > 0


def test_vergence_to_zero_limit_is_continuous(rig):
    """mu -> 0: gaze directions become parallel and equal to the cyclopean
    direction, with no singularity; fixation_distance grows to inf."""
    az, el = 0.1, -0.08
    rot0 = eye_rotations(rig, Fixation(az, el, 0.0))
    g0_left, g0_right = rot0.left @ Z, rot0.right @ Z
    np.testing.assert_array_equal(g0_left, g0_right)
    np.testing.assert_allclose(g0_left, helmholtz(az, el), atol=1e-15)
    for mu in (1e-3, 1e-6, 1e-8):
        rot = eye_rotations(rig, Fixation(az, el, mu))
        for R in (rot.left, rot.right):
            g = R @ Z
            assert np.isfinite(R).all()
            # each eye's gaze deviates from the cyclopean direction by ~mu/2;
            # chord length, not arccos of a dot product: arccos near 1 cannot
            # resolve angles below ~1e-8 and would fail at mu = 1e-8.
            assert np.linalg.norm(g - g0_left) < mu
    distances = [fixation_distance(rig, Fixation(az, el, mu)) for mu in (1e-3, 1e-6, 1e-8)]
    assert distances[0] < distances[1] < distances[2]
    assert np.isinf(fixation_distance(rig, Fixation(az, el, 0.0)))


def test_fixation_distance_forward_matches_rig_convention(rig):
    """At azimuth 0 the chord formula reduces exactly to b / (2 tan(mu/2)),
    the StereoRig.fixation_distance convention."""
    for mu in (0.02, 0.064, 0.0914, 0.16):
        fx = Fixation.forward(mu)
        expected = rig.baseline / (2.0 * np.tan(mu / 2.0))
        assert fixation_distance(rig, fx) == pytest.approx(expected, rel=1e-12)
        capture_rig = StereoRig(rig.baseline, rig.focal_px, vergence=mu)
        assert fixation_distance(rig, fx) == pytest.approx(capture_rig.fixation_distance, rel=1e-12)


def test_fixation_point_norm_is_fixation_distance(rig):
    for az, el, mu in itertools.product((0.0, 0.2), (-0.1, 0.15), (0.064, 0.16)):
        fx = Fixation(az, el, mu)
        assert np.linalg.norm(fixation_point(rig, fx)) == pytest.approx(
            fixation_distance(rig, fx), rel=1e-12
        )


def test_nonfinite_k_raises(rig):
    for bad in (np.nan, np.inf, -np.inf):
        with pytest.raises(ValueError, match="finite"):
            eye_rotations(rig, Fixation.forward(0.064), k=bad)


def test_fixation_point_at_zero_vergence_raises(rig):
    with pytest.raises(ValueError, match="infinity"):
        fixation_point(rig, Fixation.forward(0.0))


def test_azimuth_at_or_beyond_interaural_axis_raises(rig):
    """|az| >= pi/2 puts the chord on the minor arc of the Vieth-Muller
    circle (inscribed angle pi - mu): silently wrong vergence, so the
    domain is closed loudly in every public function."""
    for az in (np.pi / 2.0, -np.pi / 2.0, 2.0):
        fx = Fixation(az, 0.0, 0.064)
        for fn in (eye_rotations, fixation_distance, fixation_point):
            with pytest.raises(ValueError, match="azimuth"):
                fn(rig, fx)


def test_backward_gaze_raises_antiparallel(rig):
    """Gaze antiparallel to the primary direction (reachable only through
    extreme elevation) has no defined shortest arc; it raises rather than
    silently picking an axis."""
    with pytest.raises(ValueError, match="antiparallel"):
        eye_rotations(rig, Fixation(0.0, np.pi, 0.0))


def test_eye_rotations_result_is_frozen(rig):
    rot = eye_rotations(rig, Fixation.forward(0.064))
    assert isinstance(rot, EyeRotations)
    with pytest.raises(dataclasses.FrozenInstanceError):
        rot.left = np.eye(3)


# --- ADR-0016: the plane-of-regard alignment optimum -------------------------
# Test-local projection and point sampling. geometry.projection has no toed-in
# projection yet (migration step 4), and even once it does, pinning eye_rotations
# against it would compare the module against its own internals.


def project_px(P, R, C, f):
    """Pinhole-project head-frame points into one eye.

    Parameters: ``P`` ``(..., 3)`` metres in the cyclopean head frame, ``R`` the
    eye's head-frame orientation, ``C`` ``(3,)`` the eye's optical centre in
    metres, ``f`` focal length in pixels. Returns ``(x, y)`` pixel offsets from
    that eye's principal point, ``x`` right and ``y`` down. The principal point
    itself is irrelevant here: every assertion below is on a difference between
    the eyes, and a shared offset cancels.
    """
    v = (P - C) @ R
    return f * v[..., 0] / v[..., 2], f * v[..., 1] / v[..., 2]


def plane_of_regard_points(rig, el, mu, half_width=0.2, n=51, scales=(0.7, 1.0, 1.4)):
    """Points spanning the plane of regard: ``(N, 3)`` metres, cyclopean head frame.

    Under ADR-0015 the plane of regard at elevation ``el`` is the horizontal
    plane rotated about the interaural +X axis until +Z reaches
    ``(0, sin el, cos el)``, and it contains the baseline at every azimuth.
    Sampled at in-plane azimuths within +/- ``half_width`` rad of straight ahead
    and at radial multiples ``scales`` of the fixation distance.

    The *plane* is the alignment criterion, not the Vieth-Muller circle inside
    it: the two disagree off-axis by four orders of magnitude (ADR-0016). The
    depths are arbitrary because the property under test holds for every point
    of the plane, so ``fixation_distance`` here only sets a sensible scale.
    """
    D = fixation_distance(rig, Fixation(0.0, el, mu))
    phi = np.linspace(-half_width, half_width, n)
    in_plane = np.array([1.0, 0.0, 0.0])
    forward = np.array([0.0, np.sin(el), np.cos(el)])
    dirs = np.sin(phi)[:, None] * in_plane + np.cos(phi)[:, None] * forward
    return np.concatenate([s * D * dirs for s in scales], axis=0)


def max_vertical_disparity(rig, fx, k, points):
    """max |row_L - row_R| in pixels over ``points``; the misalignment observable."""
    rot = eye_rotations(rig, fx, k=k)
    half_b = rig.baseline / 2.0
    _, y_left = project_px(points, rot.left, np.array([-half_b, 0.0, 0.0]), rig.focal_px)
    _, y_right = project_px(points, rot.right, np.array([half_b, 0.0, 0.0]), rig.focal_px)
    return float(np.abs(y_left - y_right).max())


def test_plane_of_regard_alignment_optimum_is_k_half():
    """ADR-0016: at sagittal gaze, k = 1/2 zeroes vertical disparity in the
    plane of regard -- exactly, and independently of baseline, focal length,
    vergence and elevation.

    This is the standing pin ADR-0014:116-118 asked for, with the value
    corrected: ADR-0014 predicted the null at k = 0.25 and instructed that a
    minimum elsewhere be read as an eye_rotations sign/axis error. It is not
    one; see ADR-0016 and the 2026-08-25 lab-notebook entry for the independent
    reimplementation that discharges that clause.

    Deliberately an assertion about a stated k, not a minimisation: searching
    for the argmin and asserting it equals 0.5 would bake the search into the
    pin, and the argmin drifts off 0.5 off-axis while the analytic statement
    below does not.
    """
    for baseline, focal in ((0.064, 800.0), (0.10, 1200.0), (0.03, 400.0)):
        rig = StereoRig(baseline=baseline, focal_px=focal)
        for mu, el in itertools.product((0.064, 0.16), (0.149, 0.3)):
            points = plane_of_regard_points(rig, el, mu)
            fx = Fixation(0.0, el, mu)
            assert max_vertical_disparity(rig, fx, 0.5, points) < 1e-12
            # Negative control: the default and strict Listing both miss it by
            # ~0.2-1 px, nine orders above the tolerance above. Without this a
            # projection that returned zeros would pass.
            for k in (0.0, 0.25):
                assert max_vertical_disparity(rig, fx, k, points) > 1e-3


def helmholtz_rotation(az, el):
    """Rx(el) @ Ry(az): the Helmholtz composition of ADR-0015, test-local.

    Elevation about the fixed interaural +X axis first, then azimuth within the
    elevated plane. Head frame: +X right, +Y down, +Z forward, right-handed.
    """
    ce, se, ca, sa = np.cos(el), np.sin(el), np.cos(az), np.sin(az)
    Rx = np.array([[1.0, 0.0, 0.0], [0.0, ce, se], [0.0, -se, ce]])
    Ry = np.array([[ca, 0.0, sa], [0.0, 1.0, 0.0], [-sa, 0.0, ca]])
    return Rx @ Ry


def test_tilted_listing_at_k_half_is_helmholtz(rig):
    """ADR-0016, the reason the k = 1/2 null is exact rather than first-order:
    at sagittal gaze the tilted-Listing composition A(p->g) @ A(z->p) *is* the
    Helmholtz rotation of the eye's own gaze, identically.

    Helmholtz composition carries no torsion about the plane of regard
    (ADR-0015), so the plane images on the horizontal meridian of both retinas
    and vertical disparity vanishes there for every point at once. The
    spherical-excess cancellation that predicts k = 1/2 to first order is this
    identity linearised. Needs no projection, so it fails independently of
    test_plane_of_regard_alignment_optimum_is_k_half.
    """
    for el, mu in itertools.product((0.05, 0.149, 0.3), (0.02, 0.064, 0.16, 0.35)):
        fx = Fixation(0.0, el, mu)
        rot = eye_rotations(rig, fx, k=0.5)
        for R, g in zip((rot.left, rot.right), eye_gazes(rig, fx), strict=True):
            # The eye's own Helmholtz coordinates, read off its gaze direction.
            az_e = np.arcsin(np.clip(g[0], -1.0, 1.0))
            el_e = np.arctan2(g[1], g[2])
            np.testing.assert_allclose(R, helmholtz_rotation(az_e, el_e), atol=1e-12)
        # Negative control: the identity is a property of k = 1/2 alone.
        rot_default = eye_rotations(rig, fx, k=0.25)
        for R, g in zip((rot_default.left, rot_default.right), eye_gazes(rig, fx), strict=True):
            az_e = np.arcsin(np.clip(g[0], -1.0, 1.0))
            el_e = np.arctan2(g[1], g[2])
            assert np.abs(R - helmholtz_rotation(az_e, el_e)).max() > 1e-5


# ---------------------------------------------------------------------------
# Migration step 5: rectification_rotation, is_forward_gaze, target_to_fixation.
#
# Every geometric test below uses elevation != 0 AND azimuth != 0. At el = 0 the
# rectifier is the identity, so applying it, omitting it, or transposing it are
# bit-identical -- the sagittal-gaze hole of docs/method/003. A test that fixates
# straight ahead pins nothing here.
# ---------------------------------------------------------------------------

WIDE_RIG = StereoRig(baseline=0.064, focal_px=800.0, principal_point=(512.0, 640.0))
FIELD_SHAPE = (1024, 1280)


@pytest.fixture
def wide_rig() -> StereoRig:
    """A rig with a real principal point, so off-axis fixations land in-image.

    The shared ``rig`` fixture puts the principal point at (0, 0), which is fine
    for pure-geometry tests but makes every pixel index negative.
    """
    return WIDE_RIG


def rect_rotation(el):
    """Reference rectifier: the Helmholtz version rotation with azimuth zeroed.

    Test-local and independent of the module -- it reuses ``helmholtz_rotation``
    above, which is itself an independent reimplementation. This is also what
    pins the naming decision: if ``rectification_rotation`` ever stops being
    ``helmholtz_rotation(0, el)`` this equality fails.
    """
    return helmholtz_rotation(0.0, el)


def project_rect(rig, el, points, centre):
    """Project head-frame points into a rectified eye. Returns (row, col, z).

    Written from the geometric definition rather than by calling
    ``rectification_rotation`` / ``_project_one_eye``: a round trip through the
    implementation's own helper is self-consistent and discriminates nothing.
    """
    v = (np.asarray(points, dtype=float) - np.asarray(centre)) @ rect_rotation(el)
    return (
        rig.focal_px * v[..., 1] / v[..., 2] + rig.principal_point[0],
        rig.focal_px * v[..., 0] / v[..., 2] + rig.principal_point[1],
        v[..., 2],
    )


def left_centre(rig):
    return np.array([-rig.baseline / 2.0, 0.0, 0.0])


def azimuth_landing_on_column(rig, target_col, el, mu):
    """Azimuth whose fixation point projects onto exactly ``target_col``.

    ``target_px`` is integral (ADR-0013: ``next_fixation`` returns a pixel), so
    an exact round trip needs a fixation whose projection is exactly a pixel.
    Bisection, not the module's inverse -- constructing the input with the
    function under test is the vacuity trap.
    """
    lo, hi = -1.2, 1.2
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        _, col, _ = project_rect(
            rig, el, fixation_point(rig, Fixation(mid, el, mu)), left_centre(rig)
        )
        if col < target_col:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def depth_field_at(pixel, depth, variance=1e-4, shape=FIELD_SHAPE):
    """An all-invalid depth field carrying one valid measurement at ``pixel``."""
    value = np.full(shape, np.nan)
    var = np.full(shape, np.nan)
    value[pixel] = depth
    var[pixel] = variance
    return Estimate(value=value, variance=var)


# Fixations whose fixation point lands on an exact pixel column. Azimuth is
# solved per case; elevation and vergence are chosen to span the sweep.
ROUNDTRIP_CASES = ((900, 0.4, 0.064), (400, -0.35, 0.02), (1100, 0.25, 0.3), (300, 0.6, 0.15))


def roundtrip_inputs(rig, target_col, el, mu):
    """(current, pixel, depth) for the acceptance round trip."""
    az = azimuth_landing_on_column(rig, target_col, el, mu)
    current = Fixation(az, el, mu)
    row, col, z = project_rect(rig, el, fixation_point(rig, current), left_centre(rig))
    return current, (round(float(row)), round(float(col))), float(z)


@pytest.mark.parametrize(("target_col", "el", "mu"), ROUNDTRIP_CASES)
def test_target_to_fixation_round_trips_the_current_fixation(wide_rig, target_col, el, mu):
    """Oracle-free acceptance test: refixating on the current fixation is a no-op.

    Project the fixation point into the rectified left frame, feed that pixel
    back with its true depth, and the returned Fixation must be the one we
    started from. No ground-truth table, no tolerance chosen to fit -- the
    identity is forced by the geometry, and the negative controls below show
    each way of getting it wrong is visible.
    """
    current, pixel, depth = roundtrip_inputs(wide_rig, target_col, el, mu)
    result = target_to_fixation(pixel, depth_field_at(pixel, depth), wide_rig, current)

    assert isinstance(result, FixationProposal)
    assert result.fixation.azimuth == pytest.approx(current.azimuth, abs=1e-12)
    assert result.fixation.elevation_down == pytest.approx(current.elevation_down, abs=1e-12)
    assert result.fixation.vergence == pytest.approx(current.vergence, abs=1e-12)


def reference_inverse(rig, pixel, depth, current, fault=None):
    """Test-local unprojection, with an optional injected fault.

    Used only by the negative-control test: it establishes that each fault is
    *visible*, which an assertion about the correct implementation cannot.
    """
    row, col = pixel
    rot = rect_rotation(current.elevation_down)
    if fault == "transposed_rect":
        rot = rot.T
    centre = np.zeros(3) if fault == "cyclopean_origin" else left_centre(rig)
    ray = rot @ np.array(
        [
            (col - rig.principal_point[1]) / rig.focal_px,
            (row - rig.principal_point[0]) / rig.focal_px,
            1.0,
        ]
    )
    point = centre + depth * ray
    dist = float(np.linalg.norm(point))
    az = float(np.arcsin(point[0] / dist))
    el = float(np.arctan2(point[1], point[2]))
    if fault == "swapped_az_el":
        az, el = el, az
    half_b = rig.baseline / 2.0
    mu = float(np.arctan(rig.baseline * dist * np.cos(az) / (dist * dist - half_b * half_b)))
    return Fixation(az, el, mu)


@pytest.mark.parametrize(
    ("fault", "floor"),
    [("transposed_rect", 1e-2), ("cyclopean_origin", 1e-3), ("swapped_az_el", 1e-2)],
)
def test_round_trip_negative_controls_are_visible(wide_rig, fault, floor):
    """Each way of getting the unprojection wrong breaks the round trip.

    Without this the acceptance test could be passing vacuously: a round trip is
    exact whenever the inverse uses whatever convention the forward map used, so
    it discriminates only against faults it can actually see.
    """
    current, pixel, depth = roundtrip_inputs(wide_rig, *ROUNDTRIP_CASES[0])
    clean = reference_inverse(wide_rig, pixel, depth, current)
    assert (
        max(
            abs(clean.azimuth - current.azimuth),
            abs(clean.elevation_down - current.elevation_down),
            abs(clean.vergence - current.vergence),
        )
        < 1e-12
    ), "the fault-free reference must reproduce the fixation, or the controls prove nothing"

    broken = reference_inverse(wide_rig, pixel, depth, current, fault=fault)
    assert (
        max(
            abs(broken.azimuth - current.azimuth),
            abs(broken.elevation_down - current.elevation_down),
            abs(broken.vergence - current.vergence),
        )
        > floor
    )


def test_transposing_the_rectifier_breaks_the_round_trip(wide_rig, monkeypatch):
    """The strongest form of the transpose control: fault the module itself."""
    from activestereo.geometry import oculomotor

    current, pixel, depth = roundtrip_inputs(wide_rig, *ROUNDTRIP_CASES[0])
    original = oculomotor.rectification_rotation
    monkeypatch.setattr(oculomotor, "rectification_rotation", lambda fx: original(fx).T)

    result = oculomotor.target_to_fixation(pixel, depth_field_at(pixel, depth), wide_rig, current)
    assert isinstance(result, FixationProposal)
    assert abs(result.fixation.elevation_down - current.elevation_down) > 1e-2


@pytest.mark.parametrize(
    ("az", "el", "mu"), list(itertools.product((-0.3, 0.2), (-0.25, 0.35), (0.02, 0.3)))
)
def test_rectification_puts_the_plane_of_regard_on_the_principal_row(wide_rig, az, el, mu):
    """The criterion that selects THIS member of the R_rect family (ADR-0017).

    R_rect is fixed only up to a rotation about the baseline; every member gives
    d_v == 0. What distinguishes this one is that the fixation point images on
    the principal row. Independent of the round trip, which is transpose-blind
    when both sides share a convention.
    """
    point = fixation_point(wide_rig, Fixation(az, el, mu))
    row, _, _ = project_rect(wide_rig, el, point, left_centre(wide_rig))
    assert row == pytest.approx(wide_rig.principal_point[0], abs=1e-9)


@pytest.mark.parametrize(
    ("az", "el", "mu"), list(itertools.product((-0.3, 0.2), (-0.25, 0.35), (0.02, 0.3)))
)
def test_rectification_rotation_is_sufficient_for_rectification(wide_rig, rng, az, el, mu):
    """Vertical disparity vanishes in the pair R_rect induces.

    Named for the property it pins rather than for geometry/rectify.py, which
    does not exist yet: this belongs to rectification_rotation, and step 6
    extends it instead of writing a second copy against the module it owns.

    Both eyes share an orientation and their centres differ along the head +X
    axis, which R_rect fixes -- so rows agree exactly, not approximately.
    """
    points = rng.normal(size=(300, 3)) * np.array([0.4, 0.4, 0.2]) + np.array([0.0, 0.0, 1.8])
    row_l, _, z_l = project_rect(wide_rig, el, points, left_centre(wide_rig))
    row_r, _, z_r = project_rect(wide_rig, el, points, -left_centre(wide_rig))

    # ADR-0002: validity is eye-indexed. A point behind either eye is not
    # "zero vertical disparity", it is not imageable, and mixing the two is the
    # masking violation the ADR exists to prevent.
    imageable = (z_l > 0) & (z_r > 0)
    assert imageable.sum() > 100, (
        "degenerate sample: nothing imageable, the assertion below is vacuous"
    )
    assert np.abs(row_l[imageable] - row_r[imageable]).max() == 0.0


def test_rectification_rotation_matches_helmholtz_with_azimuth_zeroed(wide_rig):
    """The naming decision, pinned: R_rect IS the Helmholtz version rotation at az = 0."""
    for el in (-0.6, -0.2, 0.0, 0.35, 0.9):
        assert rectification_rotation(Fixation(0.4, el, 0.064)) == pytest.approx(
            helmholtz_rotation(0.0, el), abs=1e-15
        )


def test_rectification_rotation_ignores_azimuth_and_vergence(wide_rig):
    """Azimuth-independence is structural (ADR-0015), not approximate."""
    reference = rectification_rotation(Fixation(0.0, 0.37, 0.0))
    for az, mu in itertools.product((-0.9, -0.2, 0.5, 1.4), (0.0, 0.064, 0.5)):
        assert rectification_rotation(Fixation(az, 0.37, mu)) == pytest.approx(reference, abs=1e-15)


# --- the elevation domain hole -------------------------------------------------


def test_is_forward_gaze_rejects_the_elevation_domain_hole():
    """Fixation(0.1, 2.0, 0.064) is constructible and points BEHIND the head.

    types.py validates finiteness and vergence >= 0 only, and every existing L1
    function accepts this state without raising -- eye_rotations returns a
    well-formed orthonormal matrix whose optical axis has negative z.
    require_forward_azimuth cannot catch it: elevation is the free direction.
    """
    backward = Fixation(0.1, 2.0, 0.064)
    assert not is_forward_gaze(backward)
    # The state really is admitted everywhere else -- this is the hole, not a guess.
    assert np.isfinite(fixation_distance(WIDE_RIG, backward))
    assert fixation_point(WIDE_RIG, backward)[2] < 0.0
    assert eye_rotations(WIDE_RIG, backward).left @ Z @ Z < 0.0


def test_is_forward_gaze_changes_sign_at_pi_over_two():
    """The sign change sits at pi/2, and the predicate is not fooled either side.

    Deliberately not asserted *at* ``np.pi / 2``: that float is not pi/2, so
    ``cos`` of it is +6.1e-17 and the point is degenerately in front. The
    boundary is measure-zero and unreachable; what the guard has to catch is
    gaze that is unambiguously backward, and that is what is pinned here.
    """
    assert is_forward_gaze(Fixation(0.0, np.pi / 2.0 - 1e-9, 0.064))
    assert not is_forward_gaze(Fixation(0.0, np.pi / 2.0 + 1e-9, 0.064))
    assert not is_forward_gaze(Fixation(0.0, -np.pi / 2.0 - 1e-9, 0.064))
    assert is_forward_gaze(Fixation(0.3, -0.4, 0.064))


# --- the error contract -------------------------------------------------------
#
# Bad input DATA is refused so the active loop can pick another target and exp008
# can count what went wrong; a bad CALLER argument raises. Every refusal branch
# below has a test that produces it -- a guard no test can trigger is a guard
# nobody knows is dead (docs/method/003).

BACKWARD_CURRENT = Fixation(0.2, 1.5, 0.064)
NEAR_CURRENT = Fixation(0.2, 0.2, 0.064)


def test_refuses_a_target_with_no_usable_depth(wide_rig):
    """Absence of evidence: the half-occlusion signal exp008 is about."""
    field = Estimate(np.full(FIELD_SHAPE, np.nan), np.full(FIELD_SHAPE, np.nan))
    result = target_to_fixation((600, 700), field, wide_rig, NEAR_CURRENT)
    assert isinstance(result, TargetRefused)
    assert result.reasons == frozenset({RefusalReason.DEPTH_UNAVAILABLE})


def test_refuses_the_inf_variance_refusal_sentinel(wide_rig):
    """(nan, inf) is L5's established 'no usable measurement' pair; honour it here too."""
    field = depth_field_at((600, 700), np.nan, variance=np.inf)
    result = target_to_fixation((600, 700), field, wide_rig, NEAR_CURRENT)
    assert isinstance(result, TargetRefused)
    assert result.reasons == frozenset({RefusalReason.DEPTH_UNAVAILABLE})


def test_refuses_non_positive_depth(wide_rig):
    result = target_to_fixation(
        (600, 700), depth_field_at((600, 700), -1.0), wide_rig, NEAR_CURRENT
    )
    assert isinstance(result, TargetRefused)
    assert result.reasons == frozenset({RefusalReason.DEPTH_NONPOSITIVE})


def test_refuses_a_target_nearer_than_half_the_baseline(wide_rig):
    """D <= b/2 has no forward vergence solution; the arctan would take the far branch.

    Reachable only on the nasal side: D < b/2 needs the ray to run toward +x,
    i.e. col > principal column for the left eye.
    """
    pixel = (512, 1200)
    result = target_to_fixation(pixel, depth_field_at(pixel, 0.010), wide_rig, NEAR_CURRENT)
    assert isinstance(result, TargetRefused)
    assert result.reasons == frozenset({RefusalReason.TOO_NEAR})


def test_refuses_a_target_that_would_point_the_eyes_backward(wide_rig):
    """el_new = el_current + atan((row - pp_row)/f), so the image cone can cross pi/2.

    Reachable in one step once |el_current| > pi/2 - atan(half_height/f). Not a
    hypothetical branch: this is the elevation hole types.py leaves open, now
    closed for constructed fixations.
    """
    pixel = (1023, 640)
    result = target_to_fixation(pixel, depth_field_at(pixel, 1.5), wide_rig, BACKWARD_CURRENT)
    assert isinstance(result, TargetRefused)
    assert result.reasons == frozenset({RefusalReason.BACKWARD_GAZE})


def test_co_occurring_refusals_are_all_reported(wide_rig):
    """A target can be wrong in more than one way, and the set keeps both.

    BACKWARD_GAZE and TOO_NEAR are independent: elevation needs no depth, so a
    backward target is refused even under perfect depth. Returning a single
    'first' reason would count this target once and make the co-occurrence
    unrecoverable -- the same reduction as collapsing distinct kinds into None.
    """
    pixel = (1023, 1200)
    result = target_to_fixation(pixel, depth_field_at(pixel, 0.010), wide_rig, BACKWARD_CURRENT)
    assert isinstance(result, TargetRefused)
    assert result.reasons == frozenset({RefusalReason.BACKWARD_GAZE, RefusalReason.TOO_NEAR})

    # Same current fixation, same depth, column moved back to the principal
    # column: only the elevation condition survives. If the two were evaluated
    # as a chain rather than independently, this pair could not both hold.
    only_backward = target_to_fixation(
        (1023, 640), depth_field_at((1023, 640), 0.010), wide_rig, BACKWARD_CURRENT
    )
    assert isinstance(only_backward, TargetRefused)
    assert only_backward.reasons == frozenset({RefusalReason.BACKWARD_GAZE})


@pytest.mark.parametrize(
    ("pixel", "match"),
    [
        ((-1, 10), "outside"),
        ((10, -1), "outside"),
        ((1024, 10), "outside"),
        ((10, 1280), "outside"),
    ],
)
def test_out_of_bounds_target_raises(wide_rig, pixel, match):
    """A caller error, not a data-quality problem: refusing it would hide a bug."""
    field = Estimate(np.full(FIELD_SHAPE, 1.5), np.full(FIELD_SHAPE, 1e-4))
    with pytest.raises(ValueError, match=match):
        target_to_fixation(pixel, field, wide_rig, NEAR_CURRENT)


def test_non_integral_target_raises(wide_rig):
    field = Estimate(np.full(FIELD_SHAPE, 1.5), np.full(FIELD_SHAPE, 1e-4))
    with pytest.raises(ValueError, match="integral"):
        target_to_fixation((10.5, 10), field, wide_rig, NEAR_CURRENT)


def test_non_field_shaped_depth_raises(wide_rig):
    """Field-shaped is what makes the bounds check above possible at all."""
    scalar = Estimate(np.array(1.5), np.array(1e-4))
    with pytest.raises(ValueError, match="2-D"):
        target_to_fixation((10, 10), scalar, wide_rig, NEAR_CURRENT)


# --- variance propagation -----------------------------------------------------


def test_vergence_variance_is_linear_in_the_input_variance(wide_rig):
    """Pins LINEAR PASS-THROUGH, which a docstring cannot.

    First-order propagation is var_mu = J^2 var_Z, exactly proportional. Any
    clip, floor, or quiet re-scaling of the anti-calibrated variance channel
    breaks proportionality, and this fails across decades where a spot check
    would not. The propagated variance is still the exp004/exp006
    anti-calibrated one -- a correct derivative of a miscalibrated quantity.
    """
    pixel, depth = (600, 700), 1.5
    base = target_to_fixation(
        pixel, depth_field_at(pixel, depth, variance=1e-8), wide_rig, NEAR_CURRENT
    )
    assert isinstance(base, FixationProposal)

    for decade in range(9):
        scale = 10.0**decade
        scaled = target_to_fixation(
            pixel, depth_field_at(pixel, depth, variance=1e-8 * scale), wide_rig, NEAR_CURRENT
        )
        assert isinstance(scaled, FixationProposal)
        assert scaled.vergence_variance == pytest.approx(base.vergence_variance * scale, rel=1e-12)
        # The estimate itself must not move when only its uncertainty does.
        assert scaled.fixation.vergence == pytest.approx(base.fixation.vergence, rel=1e-15)


@pytest.mark.parametrize(
    ("pixel", "depth"), [((600, 700), 1.5), ((300, 900), 0.8), ((800, 400), 3.0)]
)
def test_vergence_variance_jacobian_matches_finite_differences(wide_rig, pixel, depth):
    """The analytic dmu/dZ, checked against the function's own output.

    Depth enters mu through both the distance and the azimuth -- the left-centre
    offset makes azimuth depth-dependent -- so dropping either chain-rule branch
    is a silent factor error that a sign or magnitude check would miss.
    """

    def vergence_at(z):
        result = target_to_fixation(pixel, depth_field_at(pixel, z), wide_rig, NEAR_CURRENT)
        assert isinstance(result, FixationProposal)
        return result.fixation.vergence

    unit = target_to_fixation(
        pixel, depth_field_at(pixel, depth, variance=1.0), wide_rig, NEAR_CURRENT
    )
    assert isinstance(unit, FixationProposal)

    step = 1e-6 * depth
    finite_difference = (vergence_at(depth + step) - vergence_at(depth - step)) / (2.0 * step)
    assert np.sqrt(unit.vergence_variance) == pytest.approx(abs(finite_difference), rel=1e-6)


UNNARROWED_SNIPPET = """
import numpy as np

from activestereo.geometry import target_to_fixation
from activestereo.types import Estimate, Fixation, StereoRig

result = target_to_fixation(
    (1, 1),
    Estimate(np.zeros((4, 4)), np.zeros((4, 4))),
    StereoRig(baseline=0.064, focal_px=800.0),
    Fixation(0.0, 0.0, 0.0),
)
print(result.fixation)
"""

NARROWED_SNIPPET = """
import numpy as np

from activestereo.geometry import target_to_fixation
from activestereo.types import Estimate, Fixation, FixationProposal, StereoRig

result = target_to_fixation(
    (1, 1),
    Estimate(np.zeros((4, 4)), np.zeros((4, 4))),
    StereoRig(baseline=0.064, focal_px=800.0),
    Fixation(0.0, 0.0, 0.0),
)
if isinstance(result, FixationProposal):
    print(result.fixation)
"""


@pytest.mark.slow
def test_the_refusal_union_forces_callers_to_narrow(tmp_path):
    """The union's whole point is that a caller cannot skip the refusal branch.

    Nothing in src/ consumes target_to_fixation until migration step 9, so no
    ordinary test pins this and a one-off manual check decays silently. Marked
    slow because it shells out to a type checker; skipped where mypy is absent
    rather than failing on an environment difference.

    Hermetic subprocess, following tests/unit/test_adr_hook.py: what is pinned is
    the deployed checker's behaviour, not a reimplementation of it.
    """
    pytest.importorskip("mypy")
    repo = pathlib.Path(__file__).resolve().parents[2]
    env = {**os.environ, "MYPYPATH": str(repo / "src")}

    def run(source, name):
        path = tmp_path / name
        path.write_text(source)
        return subprocess.run(
            [sys.executable, "-m", "mypy", "--no-error-summary", str(path)],
            capture_output=True,
            text=True,
            cwd=repo,
            env=env,
        )

    unnarrowed = run(UNNARROWED_SNIPPET, "unnarrowed.py")
    assert unnarrowed.returncode != 0, "reading .fixation without narrowing must not type-check"
    assert "union-attr" in unnarrowed.stdout

    # The other half: narrowing must actually be *sufficient*. Without this the
    # test would still pass if the union were unusable for a different reason.
    narrowed = run(NARROWED_SNIPPET, "narrowed.py")
    assert narrowed.returncode == 0, narrowed.stdout


def test_is_forward_gaze_is_the_geometry_test_not_the_angle_test():
    """Wrapped elevations separate the two, and only the geometry test is right.

    abs(el) < pi/2 and cos(az)cos(el) > 0 agree except at the boundary and on
    wrapped input. el = 7.0 wraps to 0.7168 and is plainly forward; the angle
    test calls it backward. Pinned so nobody "simplifies" the predicate into the
    comparison the prose around it uses.
    """
    for el in (0.3, 1.5, 1.6, 2.0, 3.0, 6.5, 7.0, -7.0):
        wrapped = (el + np.pi) % (2.0 * np.pi) - np.pi
        assert is_forward_gaze(Fixation(0.2, el, 0.064)) == (abs(wrapped) < np.pi / 2.0)
    # The three cases where a naive angle test would have been wrong.
    for el in (6.5, 7.0, -7.0):
        assert is_forward_gaze(Fixation(0.2, el, 0.064)) is True
        assert abs(el) > np.pi / 2.0


def test_target_to_fixation_is_2pi_invariant_in_the_current_elevation(wide_rig):
    """current.elevation_down enters only through cos/sin, so wrapping is invisible.

    A partial answer to step 2's declared wrapping question, in the one place
    step 5 touches it.

    Invariant to floating-point precision, NOT bitwise: cos(7.0) and
    cos(0.71681...) are not the same float, so the results differ in the last
    ulp (~3e-16). Asserted with a tolerance because the exact-equality version of
    this test fails, which is worth knowing before someone writes it.

    Note also that the reachability closed form
    el_new = el_current + atan((row - pp_row)/f) is an identity only modulo 2pi:
    here it reads 7.109560, and the returned value is that minus 2pi.
    """
    pixel = (600, 700)
    field = depth_field_at(pixel, 1.5)
    principal = target_to_fixation(pixel, field, wide_rig, Fixation(0.2, 0.7168146928204138, 0.064))
    wrapped = target_to_fixation(pixel, field, wide_rig, Fixation(0.2, 7.0, 0.064))
    assert isinstance(principal, FixationProposal) and isinstance(wrapped, FixationProposal)
    assert wrapped.fixation.elevation_down == pytest.approx(
        principal.fixation.elevation_down, abs=1e-15
    )
    assert wrapped.fixation.azimuth == pytest.approx(principal.fixation.azimuth, abs=1e-15)
    assert wrapped.fixation.vergence == pytest.approx(principal.fixation.vergence, abs=1e-15)
    assert wrapped.vergence_variance == pytest.approx(principal.vergence_variance, rel=1e-12)

    closed_form = 7.0 + np.arctan((pixel[0] - wide_rig.principal_point[0]) / wide_rig.focal_px)
    assert wrapped.fixation.elevation_down == pytest.approx(closed_form - 2.0 * np.pi, abs=1e-12)
