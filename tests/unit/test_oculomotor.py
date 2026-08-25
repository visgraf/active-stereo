"""L1 — oculomotor geometry: eye rotations under the binocular Listing law.

The shortest-arc and torsion helpers here are deliberately test-local
reimplementations: comparing the module against its own internals is the
vacuity trap (the exp001 exactly-0.0-foveal-MAE failure shape).
"""

import dataclasses
import itertools

import numpy as np
import pytest

from activestereo.geometry import (
    EyeRotations,
    eye_rotations,
    fixation_distance,
    fixation_point,
)
from activestereo.types import Fixation, StereoRig

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
