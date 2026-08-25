"""L1 — toed-in projection, vertical disparity, and the ADR-0007 item-4 closure.

Migration step 4a/4b (`docs/plans/toed-in-projection.md`). Helpers here are
deliberately test-local reimplementations: comparing the module against its own
internals is the vacuity trap (the exp001 exactly-0.0-foveal-MAE failure shape),
and `tests/unit/test_oculomotor.py` keeps the same discipline.

Every sweep runs on a rig with ``vergence == 0`` and an explicit ``Fixation``.
That is the ADR-0013 refixable case, and it is the case in which a guard reading
``rig.vergence`` instead of ``fixation.vergence`` would silently degenerate.
"""

import itertools

import numpy as np
import pytest

from activestereo.geometry import (
    depth_to_disparity,
    fixation_point,
    project_toed_in,
    toed_in_disparity,
    vieth_muller_points,
)
from activestereo.types import Fixation, StereoRig

B, F = 0.064, 800.0
IMAGE_HALF_WIDTH = 160.0  # a 320-px image at f = 800 px

AZIMUTHS = (-0.25, 0.0, 0.13, 0.25)
ELEVATIONS = (-0.2, 0.0, 0.149, 0.2)
VERGENCES = (0.02, 0.064, 0.16)
KS = (0.0, 0.25, 0.5)


@pytest.fixture
def toed_rig() -> StereoRig:
    """A refixable rig: vergence lives in the Fixation, not here (ADR-0013)."""
    return StereoRig(baseline=B, focal_px=F)


def plane_of_regard_points(rig, el, mu, half_width=0.197, n=201, scales=(0.7, 1.0, 1.4)):
    """Points spanning the plane of regard: ``(N, 3)`` metres, cyclopean head frame.

    Sampled at in-plane azimuths within +/- ``half_width`` rad of straight ahead
    and at radial multiples ``scales`` of the fixation distance. The window is
    **angular, not sensor-clipped**: at +/- 0.197 rad it reaches |x| = 160 px at
    1.0 D but 170 px at 0.7 D and up to 184 px at mu = 0.1597, i.e. off the edge
    of a 320-px image. Nothing here depends on the points being imageable.
    """
    from activestereo.geometry import fixation_distance

    D = fixation_distance(rig, Fixation(0.0, el, mu))
    phi = np.linspace(-half_width, half_width, n)
    interaural = np.array([1.0, 0.0, 0.0])
    forward = np.array([0.0, np.sin(el), np.cos(el)])
    dirs = np.sin(phi)[:, None] * interaural + np.cos(phi)[:, None] * forward
    return np.concatenate([s * D * dirs for s in scales])


def offaxis_difference(Z, eta, b, mu, k=0.25):
    """Signed d_h(toed-in) - d_h(off-axis) for a point at depth ``Z``, eccentricity ``eta``.

    ``Z`` is Cartesian depth in metres and ``eta`` the in-plane eccentricity in
    radians, so the point is ``(Z tan eta, 0, Z)``. The off-axis model is
    evaluated on a *capture* rig carrying the same vergence, since
    ``depth_to_disparity`` reads ``rig.fixation_distance``.
    """
    rig = StereoRig(baseline=b, focal_px=F)
    capture = StereoRig(baseline=b, focal_px=F, vergence=mu)
    point = np.array([Z * np.tan(eta), 0.0, Z])
    d_h, _ = toed_in_disparity(point, rig, Fixation.forward(mu), k=k)
    return float(d_h) - float(depth_to_disparity(np.array([Z]), capture)[0])


# --- 4a: per-eye projection -------------------------------------------------


def test_fixation_point_images_on_the_principal_point(toed_rig):
    """The fixation point lies on both optical axes, so it images on both
    principal points.

    **This test is torsion-blind, and that is why it is not sufficient.** The
    fixation point is *on* each optical axis, so any rotation about that axis
    leaves it exactly where it was: substituting ``R_e @ R_z(theta)`` for
    ``R_e`` keeps this passing to 3.6e-14 px even at theta = 1.2 rad, and it
    passes identically at every k. It pins the optical axis and nothing else;
    test_plane_of_regard_images_on_each_eyes_own_meridian_at_k_half is what
    sees roll.
    """
    for az, el, mu, k in itertools.product(AZIMUTHS, ELEVATIONS, VERGENCES, KS):
        fx = Fixation(az, el, mu)
        projection = project_toed_in(fixation_point(toed_rig, fx), toed_rig, fx, k=k)
        for eye in (projection.left, projection.right):
            np.testing.assert_allclose(eye, [0.0, 0.0], atol=1e-9)


def test_plane_of_regard_images_on_each_eyes_own_meridian_at_k_half(toed_rig):
    """At k = 1/2 and sagittal gaze, the plane of regard images on the
    horizontal meridian of **each eye separately** (ADR-0016).

    Asserted per-eye, not differentially: a disparity test passes whenever both
    eyes are wrong in the same way, and the two eyes' errors here are mirror
    images, so a differential test is exactly the one that would miss a shared
    sign error. Per-eye is also not simply half the differential -- ``row_L``
    and ``row_R`` are mirror-antisymmetric in ``col``, so their maxima fall at
    different points (0.2031 px per eye against 0.3813 px differential at
    mu = 0.064).

    Reference magnitudes for the negative control, max |row_e - c_row| over the
    window of :func:`plane_of_regard_points` -- **documentation, not thresholds**,
    since that window is angular and these move with it:

        mu = 0.0640:  0.2031 px at k = 0.25,  0.4061 px at k = 0
        mu = 0.1597:  0.5500 px at k = 0.25,  1.0987 px at k = 0
    """
    for baseline, focal in ((B, F), (0.10, 1200.0), (0.03, 400.0)):
        rig = StereoRig(baseline=baseline, focal_px=focal)
        for mu, el in itertools.product((0.064, 0.1597), (0.149, 0.3)):
            points = plane_of_regard_points(rig, el, mu)
            fx = Fixation(0.0, el, mu)
            aligned = project_toed_in(points, rig, fx, k=0.5)
            assert np.isfinite(aligned.left).all() and np.isfinite(aligned.right).all()
            for eye in (aligned.left, aligned.right):
                assert np.abs(eye[..., 0]).max() < 1e-12
            for k in (0.0, 0.25):
                misaligned = project_toed_in(points, rig, fx, k=k)
                for eye in (misaligned.left, misaligned.right):
                    assert np.abs(eye[..., 0]).max() > 0.05


def test_offaxis_divergence_is_a_depth_offset_plus_a_quadratic_in_eccentricity():
    """The toed-in and off-axis models differ by ``e0(Z/Zf) + c*eta^2`` -- two
    independent terms, which "first-order agreement near the axis" conflates.

    ``e0`` is the eccentricity-independent part. It is *not* small merely
    because eta is small (it is -3.21e-2 px at 0.7 Zf and +1.07e-2 px at 1.4 Zf,
    changing sign across the horopter), and it is independent of baseline. A
    single tolerance on |difference| would absorb it and pin nothing, so both
    assertions here are tolerance-free:

    1. at eta = 0 and Z = Zf the models agree to machine zero -- the one place
       ``e0`` itself vanishes;
    2. the **signed** difference, minus its eta = 0 value, quarters as eta
       halves.

    Signed is load-bearing rather than stylistic. At 1.4 Zf, ``e0 > 0`` while
    ``c*eta^2 < 0``, so the signed difference crosses zero near eta = 0.0143 --
    inside any natural ladder. An |.|-based ladder straddling that crossing
    gives ratios 4.22 / 4.63 / 10.08 and means nothing.
    """
    mu = 0.064
    for b in (0.064, 0.032, 0.016):
        Zf = StereoRig(baseline=b, focal_px=F, vergence=mu).fixation_distance
        assert abs(offaxis_difference(Zf, 0.0, b, mu)) < 1e-12

        for scale in (0.7, 1.0, 1.4):
            Z = scale * Zf
            e0 = offaxis_difference(Z, 0.0, b, mu)
            etas = (0.10, 0.05, 0.025, 0.0125, 0.00625)
            quadratic = [offaxis_difference(Z, eta, b, mu) - e0 for eta in etas]
            ratios = [quadratic[i] / quadratic[i + 1] for i in range(len(etas) - 1)]
            assert all(r > 4.0 for r in ratios), ratios  # approached from above
            assert all(ratios[i] > ratios[i + 1] for i in range(len(ratios) - 1)), ratios
            assert ratios[-1] == pytest.approx(4.0, abs=0.01)


def test_unimageable_points_are_nan_in_both_channels(toed_rig):
    """CLAUDE.md section 3: invalid means ``nan``, never 0 and never a sentinel.

    Three near-misses worth stating, because all look invalid and are not.

    "Behind" means behind the **eye**, not behind the cyclopean origin. The
    nodal points sit 32 mm lateral and the eyes toe inward, so a point at
    ``[0, 0, -0.001]`` is still in *front* of both: the eye-frame depth is
    ``(b/2) sin(yaw) + z cos(yaw)``, which stays positive until z is roughly
    -1.0e-3 m at mu = 0.064. ``[0, 0, 0]`` itself images legitimately, at
    ~2.5e4 px. And one eye's nodal point is 64 mm in front of the other's, so it
    is invalid in that eye alone -- validity is **per-eye**, and asserting it on
    both would be asserting something false.

    Being far off the sensor is not the same as being invalid; clipping to the
    image is the caller's business, not this module's.
    """
    fx = Fixation.forward(0.064)
    behind = np.array([[0.0, 0.0, -1.0], [0.0, 0.0, -0.1], [0.0, 0.0, -0.01]])
    nonfinite = np.array([[np.nan, 0.0, 1.0], [0.0, np.inf, 1.0], [0.0, 0.0, np.nan]])
    for points in (behind, nonfinite):
        projection = project_toed_in(points, toed_rig, fx)
        assert np.isnan(projection.left).all()
        assert np.isnan(projection.right).all()

    # Each eye's own nodal point: v = 0, so v_z = 0 and the projection is
    # undefined -- in that eye only, and the other eye must still be finite.
    at_left_nodal = project_toed_in(np.array([-B / 2, 0.0, 0.0]), toed_rig, fx)
    assert np.isnan(at_left_nodal.left).all() and np.isfinite(at_left_nodal.right).all()
    at_right_nodal = project_toed_in(np.array([B / 2, 0.0, 0.0]), toed_rig, fx)
    assert np.isnan(at_right_nodal.right).all() and np.isfinite(at_right_nodal.left).all()

    # Disparity needs both eyes, so it is nan wherever either eye is.
    d_h, d_v = toed_in_disparity(nonfinite, toed_rig, fx)
    assert np.isnan(d_h).all() and np.isnan(d_v).all()


def test_validity_is_eye_indexed_not_a_property_of_the_point(toed_rig):
    """The same 3-D point can be imageable by one eye and behind the other.

    Sagittal gaze cannot show this: the eyes are mirror images there, so their
    eye-frame depths for a given point are identical to machine precision (the
    cyclopean origin sits at +1.023825e-3 m in *both* eyes at az = 0, and the
    sign flips for both together at z = -(b/2) tan(mu/2) = -1.024350e-3 m). A
    test written only on-axis would pass against a consumer that built one
    geometric validity mask and applied it to both images -- the ADR-0002
    failure mode described on :class:`BinocularProjection`.

    Off-axis the two eyes disagree outright. At az = 0.35 the cyclopean origin
    is +1.19e-2 m in front of the left eye and -9.99e-3 m behind the right, so
    exactly one eye's projection is ``nan``.
    """
    eccentric = Fixation(0.35, 0.0, 0.064)
    origin = np.zeros(3)
    projection = project_toed_in(origin, toed_rig, eccentric)
    assert np.isfinite(projection.left).all()
    assert np.isnan(projection.right).all()

    # Disparity needs both eyes, so it is nan wherever either eye is.
    d_h, d_v = toed_in_disparity(origin, toed_rig, eccentric)
    assert np.isnan(d_h).all() and np.isnan(d_v).all()

    # ...and the mirrored gaze flips which eye it is, so neither eye is simply
    # the more permissive one.
    mirrored = project_toed_in(origin, toed_rig, Fixation(-0.35, 0.0, 0.064))
    assert np.isnan(mirrored.left).all()
    assert np.isfinite(mirrored.right).all()


def test_principal_point_offset_is_honoured_in_row_col_order(toed_rig):
    """``principal_point`` is ``(row, col)``; a transposed read would swap a
    120-px row shift with a 160-px column shift and still look plausible."""
    offset = StereoRig(baseline=B, focal_px=F, principal_point=(120.0, 160.0))
    fx = Fixation(0.1, -0.05, 0.064)
    point = fixation_point(toed_rig, fx)
    centred = project_toed_in(point, toed_rig, fx).left
    shifted = project_toed_in(point, offset, fx).left
    np.testing.assert_allclose(shifted - centred, [120.0, 160.0], atol=1e-9)


# --- 4b: vertical disparity and the horopter closure ------------------------


def independent_circle(rig, fixation, azimuths):
    """Vieth-Muller circle from centre and radius, rotated into the plane of regard.

    Built from the inscribed-angle construction rather than the chord formula
    the library uses, and it reads ``fixation.vergence`` -- never
    ``rig.vergence``, which is 0 for every rig in this file.
    """
    mu, el = fixation.vergence, fixation.elevation_down
    radius = rig.baseline / (2.0 * np.sin(mu))
    height = (rig.baseline / 2.0) / np.tan(mu)
    # In-plane (u, w): centre at (0, height), so u = R sin t, w = height + R cos t
    # for the point seen at in-plane azimuth `azimuths` from the origin.
    u, w = [], []
    for a in np.atleast_1d(azimuths):
        # Intersect the ray (sin a, cos a) with the circle; take the far root.
        t = height * np.cos(a) + np.sqrt(radius**2 - height**2 * np.sin(a) ** 2) * np.sign(
            np.cos(a)
        )
        u.append(t * np.sin(a))
        w.append(t * np.cos(a))
    u, w = np.array(u), np.array(w)
    interaural = np.array([1.0, 0.0, 0.0])
    forward = np.array([0.0, np.sin(el), np.cos(el)])
    return u[:, None] * interaural + w[:, None] * forward


def test_vieth_muller_points_matches_an_independent_circle_construction(toed_rig):
    """The library applies R_x(elevation_down) itself; this is the control that
    keeps that from being unfalsifiable.

    The reimplementation intersects a ray with the circle of radius
    ``b / (2 sin mu)`` centred at height ``(b/2) / tan mu`` -- the inscribed-angle
    construction -- where the library evaluates the chord closed form.
    """
    azimuths = np.linspace(-0.4, 0.4, 41)
    for az, el, mu in itertools.product((0.0, 0.2), (-0.15, 0.0, 0.149), (0.02, 0.064, 0.16)):
        fx = Fixation(az, el, mu)
        np.testing.assert_allclose(
            vieth_muller_points(toed_rig, fx, azimuths),
            independent_circle(toed_rig, fx, azimuths),
            atol=1e-15,
        )


def test_vieth_muller_points_passes_through_the_fixation_point(toed_rig):
    """Sampled at the gaze azimuth, the circle *is* the fixation point."""
    for az, el, mu in itertools.product((0.0, 0.2), (-0.15, 0.149), (0.02, 0.064, 0.16)):
        fx = Fixation(az, el, mu)
        np.testing.assert_allclose(
            vieth_muller_points(toed_rig, fx, np.array(az)),
            fixation_point(toed_rig, fx),
            atol=1e-15,
        )


def test_vieth_muller_points_rejects_degenerate_and_out_of_domain_input(toed_rig):
    """Zero vergence degenerates to the plane at infinity; returning ``inf``
    would make every downstream zero-disparity test pass vacuously."""
    with pytest.raises(ValueError, match="degenerate"):
        vieth_muller_points(toed_rig, Fixation.forward(0.0), np.array([0.0]))
    with pytest.raises(ValueError, match="azimuth"):
        vieth_muller_points(toed_rig, Fixation(np.pi / 2, 0.0, 0.064), np.array([0.0]))
    for bad in (np.pi / 2, -np.pi / 2, 2.0):
        with pytest.raises(ValueError, match="minor arc"):
            vieth_muller_points(toed_rig, Fixation.forward(0.064), np.array([bad]))
    with pytest.raises(ValueError, match="finite"):
        vieth_muller_points(toed_rig, Fixation.forward(0.064), np.array([np.nan]))


def on_circle(rig, fx, k, span=0.25, n=801):
    """Sample the Vieth-Muller circle of ``(rig, fx)``.

    Returns ``(d_h, d_v, col_left, mask)`` -- disparities in px, the left eye's
    column coordinate in px, and the mask of samples inside the image.
    ``col_left`` is returned rather than reduced here so that
    :func:`assert_preconditions` can measure peripheral reach itself.
    """
    azimuths = np.linspace(fx.azimuth - span, fx.azimuth + span, n)
    points = vieth_muller_points(rig, fx, azimuths)
    d_h, d_v = toed_in_disparity(points, rig, fx, k=k)
    col = project_toed_in(points, rig, fx, k=k).left[..., 1]
    return d_h, d_v, col, np.abs(col) <= IMAGE_HALF_WIDTH


def assert_preconditions(rig, fx, col, mask):
    """Guard against the vacuous pass (`docs/plans/fixation-migration.md` 69-85).

    Reads ``fixation.vergence``. The radius via ``vieth_muller_radius(rig)``
    would be ``inf`` for every rig in this file, and the assertion would then
    hold on a horopter that had degenerated to the plane at infinity.

    Takes ``col`` and ``mask`` and derives the peripheral reach **here**, rather
    than accepting a reach argument. An earlier version took the number, and two
    of its three call sites passed a constant -- a guard that cannot fail, which
    is the exact defect this file exists to rule out. Deriving it from the same
    arrays the assertions run on makes that unexpressible.
    """
    assert fx.vergence > 0.0
    radius = rig.baseline / (2.0 * np.sin(fx.vergence))
    assert np.isfinite(radius) and radius > 0.0
    assert mask.sum() > 100, "no imageable samples: nothing was actually compared"
    reach = np.abs(col[mask]).max()
    assert reach > 100.0, f"samples reach only {reach:.1f} px; the residual lives at the edge"


def test_zero_horizontal_disparity_on_the_vieth_muller_circle(toed_rig):
    """ADR-0007 item 4, closed. The Vieth-Muller circle is the zero-horizontal-
    disparity locus of the toed-in model -- **exactly** where ``azimuth == 0`` or
    ``elevation_down == 0``, and to a residual ADR-0016 quantifies otherwise.

    Three regimes, because one tolerance across all of them would be either
    vacuous or wrong:

    * sagittal or horizontal gaze -- exact, ``< 1e-12`` px (measured <= 2e-13);
    * oblique gaze at k in {0, 0.25} -- the residual follows
      ``x * mu * az * el**2 * (k - 1/2) / 2``, pinned to 10% (measured 2.2% and
      5.6%);
    * oblique gaze at k = 1/2 -- the law vanishes and the measurement does not,
      so this corner takes an **absolute** bound. 2.0e-3 px is a residual the
      law does not capture, not a failure of it, and pinning it by relative
      error against a vanishing prediction is meaningless.
    """
    for el, mu, k in itertools.product((0.0, 0.149, 0.2), VERGENCES, KS):
        fx = Fixation(0.0, el, mu)  # sagittal
        d_h, _, col, mask = on_circle(toed_rig, fx, k)
        assert_preconditions(toed_rig, fx, col, mask)
        assert np.abs(d_h[mask]).max() < 1e-12

    for az, mu, k in itertools.product((-0.25, 0.13, 0.25), VERGENCES, KS):
        fx = Fixation(az, 0.0, mu)  # horizontal
        d_h, _, col, mask = on_circle(toed_rig, fx, k)
        assert_preconditions(toed_rig, fx, col, mask)
        assert np.abs(d_h[mask]).max() < 1e-12

    for az, el, mu in itertools.product((0.13, 0.25), (0.149, 0.2), (0.064, 0.16)):
        for k in (0.0, 0.25):
            fx = Fixation(az, el, mu)
            d_h, _, col, mask = on_circle(toed_rig, fx, k)
            assert_preconditions(toed_rig, fx, col, mask)
            # Pointwise, not max against max: the two maxima need not fall at
            # the same sample, so comparing them would agree for a reason the
            # law does not supply -- the same objection that replaced the
            # differential form of the A2 meridian test with a per-eye one.
            predicted = col[mask] * mu * az * el**2 * (k - 0.5) / 2.0
            measured = d_h[mask]
            # Scale-free residual bound, valid through the sign change at
            # col = 0 where both sides vanish and a ratio means nothing.
            assert np.abs(measured - predicted).max() < 0.10 * np.abs(predicted).max()
            # ...and a genuine pointwise relative agreement over the bulk.
            significant = np.abs(predicted) > 1e-3
            assert significant.sum() > 100
            np.testing.assert_allclose(measured[significant], predicted[significant], rtol=0.10)
        fx = Fixation(az, el, mu)
        d_h, _, col, mask = on_circle(toed_rig, fx, 0.5)
        assert_preconditions(toed_rig, fx, col, mask)
        assert np.abs(d_h[mask]).max() < 5e-3


def test_vertical_disparity_on_the_vieth_muller_circle_is_nonzero_at_elevated_gaze(toed_rig):
    """Vertical disparity does not vanish on the horopter, and is not meant to.

    **Point set: the Vieth-Muller circle.** ADR-0016 leaves plane-vs-circle open
    and explicitly declined to headline the off-axis floor, so this asserts
    **non-vanishing only, never a magnitude**: 0.05 px sits far below both
    candidate criteria (circle 0.38-0.95 px, plane 0.41-1.11 px at k = 0.25) and
    is therefore insensitive to which one the framework eventually adopts.

    It doubles as the guard that keeps
    test_zero_horizontal_disparity_on_the_vieth_muller_circle honest: a
    projection returning zeros, or one that dropped the row channel, would pass
    that test and fail this one.
    """
    for az, el, mu in itertools.product((0.0, 0.13), (0.149, 0.2), (0.064, 0.16)):
        fx = Fixation(az, el, mu)
        _, d_v, col, mask = on_circle(toed_rig, fx, 0.25)
        assert_preconditions(toed_rig, fx, col, mask)
        assert np.abs(d_v[mask]).max() > 0.05
    for az, mu in itertools.product((0.0, 0.13, 0.25), VERGENCES):
        fx = Fixation(az, 0.0, mu)  # elevation 0: the plane of regard is the XZ plane
        _, d_v, col, mask = on_circle(toed_rig, fx, 0.25)
        # The exact-zero half needs the guard as much as the payoff test does:
        # an empty mask would satisfy `< 1e-12` without comparing anything.
        assert_preconditions(toed_rig, fx, col, mask)
        assert np.abs(d_v[mask]).max() < 1e-12


def test_perturbed_vergence_breaks_the_horopter_zero(toed_rig):
    """Negative control for the payoff test: the zero is a property of *this*
    fixation, not of any fixation.

    Perturbing ``fixation.vergence`` by 1% and re-projecting the **unperturbed**
    circle must move the horizontal disparity far above tolerance. The predicted
    scale is ``f * delta_mu`` -- 0.512 px at mu = 0.064 -- and the measured value
    is 0.5325 px.

    The margin is regime-dependent and both are recorded: in the exact-zero
    regime it is ~13 orders (5.7e-14 -> 0.53), at oblique gaze only ~40x
    (3.4e-2 -> 1.36), because the unperturbed value there is already the
    ADR-0016 residual rather than machine zero.
    """
    for az, el, mu in itertools.product((0.0, 0.13, 0.25), (0.0, 0.149, 0.2), (0.064, 0.16)):
        fx = Fixation(az, el, mu)
        perturbed = Fixation(az, el, mu * 1.01)
        azimuths = np.linspace(az - 0.25, az + 0.25, 801)
        points = vieth_muller_points(toed_rig, fx, azimuths)  # unperturbed circle
        base, _ = toed_in_disparity(points, toed_rig, fx, k=0.25)
        moved, _ = toed_in_disparity(points, toed_rig, perturbed, k=0.25)
        col = project_toed_in(points, toed_rig, fx, k=0.25).left[..., 1]
        mask = np.abs(col) <= IMAGE_HALF_WIDTH
        assert_preconditions(toed_rig, fx, col, mask)
        assert np.abs(moved[mask]).max() > 0.1
        assert np.abs(moved[mask]).max() > 10.0 * max(np.abs(base[mask]).max(), 1e-12)
