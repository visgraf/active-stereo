"""End-to-end: RDS stimulus through all six layers.

These tests are the closest thing the repo has to "does the framework work". They
are slower than unit tests and deliberately assert *relationships* (SGBM beats
block matching in occlusions; the loop terminates) rather than absolute numbers,
which would be brittle without buying anything.
"""

import numpy as np
import pytest

from activestereo.inference import BlockMatcher
from activestereo.policy import next_fixation, uncertainty_saliency
from activestereo.policy.foveation import confine_to_fovea
from activestereo.scaling import scale_to_depth
from activestereo.scenes import RandomDotStereogram, disk, slanted_plane
from activestereo.types import StereoRig

pytestmark = pytest.mark.integration


@pytest.fixture
def rig():
    return StereoRig(baseline=0.064, focal_px=800.0, vergence=2 * np.arctan(0.064 / 2 / 2.5))


@pytest.fixture
def stim(rig):
    return RandomDotStereogram(disk, shape=(120, 160), dot_size=2).render(
        rig, np.random.default_rng(11)
    )


def _pipeline(stim, matcher, coefficient=1e-4):
    d = matcher.match(stim.left, stim.right)
    return d, confine_to_fovea(scale_to_depth(d, stim.rig), coefficient=coefficient)


def test_recovers_depth_where_a_match_exists(stim):
    """The stimulus carries depth in disparity alone, so a correct depth estimate
    is proof that L3 matched rather than that L1 leaked."""
    _, depth = _pipeline(stim, BlockMatcher(max_disparity=48, window=7))
    ok = stim.matched & np.isfinite(depth.value)
    assert ok.mean() > 0.5
    assert float(np.median(np.abs(depth.value[ok] - stim.depth[ok]))) < 0.02


def test_frontoparallel_bias_on_a_depth_gradient(rig):
    """A square correlation window assumes constant disparity across itself, so a
    slanted surface is systematically harder than a fronto-parallel one even with
    identical dot statistics and no occlusion at all.

    This is the frontoparallel bias, and it is the standing argument for the
    slanted-plane stimulus: it separates "the matcher cannot find a match" from
    "the matcher's model of the surface is wrong". Only the second is fixed by a
    better prior at L3.
    """
    m = BlockMatcher(max_disparity=48, window=7)
    err = {}
    for name, fn in (("slant", slanted_plane), ("disk", disk)):
        s = RandomDotStereogram(fn, shape=(120, 160), dot_size=2).render(
            rig, np.random.default_rng(5)
        )
        d = m.match(s.left, s.right)
        ok = s.matched & np.isfinite(d.value)
        err[name] = float(np.percentile(np.abs(d.value[ok] - s.disparity[ok]), 90))

    assert err["slant"] > 1.5 * err["disk"], err


def test_gradient_stimulus_has_no_occlusion(rig):
    """The control condition. A monotone disparity gradient warps injectively, so
    any coverage loss on the slanted plane is attributable to matching alone."""
    s = RandomDotStereogram(slanted_plane, shape=(120, 160), dot_size=2).render(
        rig, np.random.default_rng(5)
    )
    assert s.occlusion_fraction == 0.0


@pytest.mark.regression
def test_active_loop_terminates_on_a_real_occlusion_band(stim):
    """ADR-0002 against a stimulus with genuine geometric occlusion, rather than
    the synthetic invalid rectangle in the unit-level regression test."""
    _, depth = _pipeline(stim, BlockMatcher(max_disparity=48, window=7))
    saliency = uncertainty_saliency(depth, sigma=3.0)

    visited: list[tuple[int, int]] = []
    for _ in range(200):
        t = next_fixation(saliency, visited=visited, inhibition_radius=10.0)
        if t is None:
            break
        assert t not in visited, "inhibition of return failed; ADR-0002"
        visited.append(t)
    else:
        pytest.fail("active-sampling loop did not terminate within 200 fixations")


@pytest.mark.regression
def test_gaze_avoids_the_occlusion_band(stim):
    """The band is unknowable, so it must not be where the policy looks first."""
    _, depth = _pipeline(stim, BlockMatcher(max_disparity=48, window=7))
    saliency = uncertainty_saliency(depth, sigma=3.0)
    targets = []
    for _ in range(10):
        t = next_fixation(saliency, visited=targets, inhibition_radius=8.0)
        if t is None:
            break
        targets.append(t)
    hits = sum(1 for r, c in targets if stim.occluded[r, c])
    assert hits <= 1, f"{hits}/{len(targets)} fixations landed in the occlusion band"


@pytest.mark.requires_cv2
def test_sgbm_hallucinates_less_in_occlusions_than_block_matching(stim):
    """The operational reason SGBM is preferred: not that it covers more, but that
    it declines where there is nothing to find. A matcher that confidently reports
    depth in a half-occlusion is worse than one that returns nan."""
    cv2 = pytest.importorskip("cv2")
    assert cv2 is not None
    from activestereo.inference.sgbm import SGBMMatcher

    rates = {}
    for name, m in (
        ("block", BlockMatcher(max_disparity=48, window=7)),
        ("sgbm", SGBMMatcher(max_disparity=48, block_size=7)),
    ):
        _, depth = _pipeline(stim, m)
        occ = stim.occluded
        rates[name] = float((occ & np.isfinite(depth.value)).sum() / max(occ.sum(), 1))
    assert rates["sgbm"] < rates["block"], rates
