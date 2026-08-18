"""Stimulus synthesis: correspondence, occlusion, and the absence of monocular cues."""

import numpy as np
import pytest

from activestereo.geometry import disparity_to_depth
from activestereo.scenes import (
    RandomDotStereogram,
    Scene,
    corrugated,
    disk,
    slanted_plane,
    staircase,
)
from activestereo.scenes.rds import dot_texture


@pytest.fixture
def demo_rig():
    from activestereo.types import StereoRig

    # Fixation behind the scene, so no surface sits at disparity 0.
    return StereoRig(baseline=0.064, focal_px=800.0, vergence=2 * np.arctan(0.064 / 2 / 2.5))


def _stim(depth_fn, demo_rig, shape=(96, 128), **kw):
    scene = RandomDotStereogram(depth_fn, shape=shape, **kw)
    return scene.render(demo_rig, np.random.default_rng(7))


def test_rds_satisfies_scene_protocol():
    assert isinstance(RandomDotStereogram(disk), Scene)


def test_matched_pixels_correspond_exactly(demo_rig):
    """The defining property. Every matched left pixel equals its right partner
    bit for bit -- RDS synthesis copies dots, it does not interpolate them."""
    s = _stim(disk, demo_rig, dot_size=2)
    H, W = s.shape
    rows, cols = np.indices((H, W))
    d = np.nan_to_num(s.disparity, nan=0.0).astype(int)
    target = cols - d
    ok = s.matched & (target >= 0) & (target < W)
    assert ok.sum() > 0.5 * H * W
    np.testing.assert_array_equal(s.left[rows[ok], cols[ok]], s.right[rows[ok], target[ok]])


def test_no_monocular_cue(demo_rig):
    """Julesz's point: neither image alone reveals the shape. If the intensity
    statistics inside the disk differ from outside, synthesis has leaked a cue
    and every result obtained with the stimulus is suspect."""
    s = _stim(disk, demo_rig, dot_size=1, shape=(160, 200))
    near = s.disparity > np.nanmedian(s.disparity)
    inside, outside = s.left[near], s.left[~near]
    assert abs(inside.mean() - outside.mean()) < 0.05
    assert abs(inside.std() - outside.std()) < 0.05


def test_depth_and_disparity_are_mutually_consistent(demo_rig):
    """Ground truth must not contradict itself: a matcher that recovers the
    disparity exactly must score zero depth error."""
    s = _stim(staircase, demo_rig)
    expected = disparity_to_depth(s.disparity, demo_rig)
    ok = np.isfinite(expected) & np.isfinite(s.depth)
    np.testing.assert_allclose(s.depth[ok], expected[ok], rtol=1e-12)


def test_depth_step_produces_occlusion(demo_rig):
    s = _stim(disk, demo_rig)
    assert 0.01 < s.occlusion_fraction < 0.4


def test_smooth_surface_produces_almost_none(demo_rig):
    """A monotone disparity gradient warps injectively, so nothing is hidden.
    The contrast with the disk is what makes occlusion an experimental variable
    rather than a confound."""
    s = _stim(slanted_plane, demo_rig)
    assert s.occlusion_fraction < 0.02


def test_larger_depth_step_occludes_more(demo_rig):
    small = _stim(disk, demo_rig, near=1.4, far=1.6)
    large = _stim(disk, demo_rig, near=0.8, far=1.6)
    assert large.occlusion_fraction > small.occlusion_fraction


def test_occlusion_is_adjacent_to_the_depth_step(demo_rig):
    """Half-occlusion is a boundary phenomenon, and the band is exactly as wide as
    the disparity step that produced it. Finding occlusion further from an edge
    than the step size would mean the z-buffer is wrong."""
    s = _stim(disk, demo_rig)
    d = np.nan_to_num(s.disparity, nan=0.0)
    jump = np.abs(np.diff(d, axis=1, prepend=d[:, :1]))
    step = int(np.ceil(jump.max()))
    assert step > 1, "stimulus has no depth step to test"

    # Dilate the edge horizontally by the step size, plus a pixel of slack.
    edge = jump > 1.0
    band = np.zeros_like(edge)
    for shift in range(-step - 1, step + 2):
        band |= np.roll(edge, shift, axis=1)

    occluded = s.occluded
    assert occluded.sum() > 0
    assert (occluded & band).sum() / occluded.sum() > 0.99


def test_determinism(demo_rig):
    scene = RandomDotStereogram(corrugated, shape=(64, 96))
    a = scene.render(demo_rig, np.random.default_rng(3))
    b = scene.render(demo_rig, np.random.default_rng(3))
    np.testing.assert_array_equal(a.left, b.left)
    np.testing.assert_array_equal(a.right, b.right)


def test_different_seeds_give_different_dots_same_geometry(demo_rig):
    scene = RandomDotStereogram(disk, shape=(64, 96))
    a = scene.render(demo_rig, np.random.default_rng(1))
    b = scene.render(demo_rig, np.random.default_rng(2))
    assert not np.array_equal(a.left, b.left)
    np.testing.assert_array_equal(np.nan_to_num(a.disparity), np.nan_to_num(b.disparity))


def test_dot_texture_density_and_size():
    rng = np.random.default_rng(0)
    t = dot_texture((200, 200), rng, density=0.3, dot_size=1)
    assert abs(t.mean() - 0.3) < 0.02
    big = dot_texture((40, 40), rng, density=0.5, dot_size=4)
    np.testing.assert_array_equal(big[0:4, 0:4], np.full((4, 4), big[0, 0]))


def test_stimulus_rejects_mismatched_shapes(demo_rig):
    from activestereo.scenes.base import StereoStimulus

    with pytest.raises(ValueError, match="disagree in shape"):
        StereoStimulus(
            left=np.zeros((4, 4)),
            right=np.zeros((4, 4)),
            depth=np.zeros((4, 4)),
            disparity=np.zeros((5, 5)),
            matched=np.ones((4, 4), bool),
            in_frame=np.ones((4, 4), bool),
            rig=demo_rig,
        )


def test_noise_degrades_correlation_without_moving_geometry(demo_rig):
    clean = _stim(disk, demo_rig, noise=0.0)
    noisy = _stim(disk, demo_rig, noise=0.2)
    np.testing.assert_array_equal(np.nan_to_num(clean.disparity), np.nan_to_num(noisy.disparity))
    assert noisy.left.std() > clean.left.std()


def test_out_of_range_disparity_is_marked_unmatched(demo_rig):
    """A surface so near that its correspondent falls off the image edge has no
    partner. Silently wrapping or clamping would fabricate one."""
    s = _stim(disk, demo_rig, near=0.35, far=1.6, radius=0.9)
    assert s.out_of_frame.any()
    assert not (s.out_of_frame & s.matched).any()


def test_out_of_frame_is_not_counted_as_occlusion(demo_rig):
    """A border pixel whose partner fell off the sensor is a field-of-view limit,
    not a fact about the scene. Counting it as occlusion would make every smooth
    surface look occluded and would pollute every occlusion statistic."""
    s = _stim(slanted_plane, demo_rig)
    assert s.out_of_frame.sum() > 0
    assert not (s.occluded & s.out_of_frame).any()
    assert s.occlusion_fraction < float(1.0 - s.matched.mean())


# --- ADR-0011: ground truth we do not have -----------------------------------


def _with_known(stim, known):
    """Copy a stimulus, supplying a ``known`` mask. The dataclass is frozen."""
    from dataclasses import replace

    return replace(stim, known=known)


def test_synthetic_stimulus_leaves_known_unset(demo_rig):
    """An RDS knows the disparity of every pixel because it placed the dots.
    ``None`` is the honest answer, and it is what keeps exp001-exp003 comparable."""
    s = _stim(disk, demo_rig)
    assert s.known is None
    assert s.unknown_fraction == 0.0


def test_known_none_reproduces_pre_adr_behaviour(demo_rig):
    """ADR-0011 must be invisible to every existing caller. These three properties
    are what exp001, exp002 and exp003 are scored through; if any of them moved,
    three sets of published run-ids would silently stop meaning what they say."""
    s = _stim(disk, demo_rig)
    np.testing.assert_array_equal(s.scorable, s.matched)
    np.testing.assert_array_equal(s.occluded, s.in_frame & ~s.matched)
    np.testing.assert_array_equal(s.out_of_frame, ~s.in_frame)


def test_known_narrows_scorable_occluded_and_out_of_frame(demo_rig):
    s = _stim(disk, demo_rig)
    known = np.ones(s.shape, bool)
    known[10:20, 30:40] = False
    holed = _with_known(s, known)

    assert holed.unknown_fraction == pytest.approx(100 / (s.shape[0] * s.shape[1]))
    for full, narrowed in (
        (s.scorable, holed.scorable),
        (s.occluded, holed.occluded),
        (s.out_of_frame, holed.out_of_frame),
    ):
        assert not (narrowed & ~known).any()
        np.testing.assert_array_equal(narrowed, full & known)


def test_unknown_pixels_land_in_no_scene_category(demo_rig):
    """The regression ADR-0011 exists to prevent.

    A scanner hole is a gap in our knowledge, not a fact about the scene. Charged
    to ``occluded`` it inflates exp001's headline metric; charged to
    ``out_of_frame`` it inflates a field-of-view statistic with a sensor failure.
    It must appear in neither -- so the three categories stop partitioning the
    frame, and ``unknown_fraction`` accounts for the remainder.
    """
    s = _stim(staircase, demo_rig)
    known = np.ones(s.shape, bool)
    known[::7, ::5] = False  # scattered, so it crosses occluded and border alike
    holed = _with_known(s, known)

    unknown = ~known
    assert unknown.sum() > 0
    assert not (holed.occluded & unknown).any()
    assert not (holed.out_of_frame & unknown).any()
    assert not (holed.scorable & unknown).any()

    # Where truth *does* exist, the three scene categories still partition. Union
    # alone would be vacuous -- it holds by construction whatever the masks say --
    # so the load-bearing half is that they stay mutually exclusive, in particular
    # that nothing is both matched and off-sensor.
    classes = (holed.scorable, holed.occluded, holed.out_of_frame)
    for i, a in enumerate(classes):
        for b in classes[i + 1 :]:
            assert not (a & b).any()
    assert (classes[0] | classes[1] | classes[2])[known].all()


def test_stimulus_rejects_mismatched_known_shape(demo_rig):
    from activestereo.scenes.base import StereoStimulus

    with pytest.raises(ValueError, match="disagree in shape"):
        StereoStimulus(
            left=np.zeros((4, 4)),
            right=np.zeros((4, 4)),
            depth=np.zeros((4, 4)),
            disparity=np.zeros((4, 4)),
            matched=np.ones((4, 4), bool),
            in_frame=np.ones((4, 4), bool),
            rig=demo_rig,
            known=np.ones((5, 5), bool),
        )
