"""L4 — metric scaling and MLE fusion."""

import numpy as np

from activestereo.geometry import depth_to_disparity
from activestereo.scaling import fuse_mle, scale_to_depth
from activestereo.types import Estimate


def test_scale_to_depth_recovers_ground_truth(rig):
    Z_true = np.array([[0.6, 1.0, 2.0]])
    d = depth_to_disparity(Z_true, rig)
    est = scale_to_depth(Estimate(value=d, variance=np.full(d.shape, 0.25)), rig)
    np.testing.assert_allclose(est.value, Z_true, rtol=1e-10)


def test_depth_variance_grows_with_distance(rig):
    """var(Z) ~ Z^4: the quadratic Jacobian squared. This is why far depth needs
    cue fusion rather than more stereo."""
    Z_true = np.array([[1.0, 2.0]])
    d = depth_to_disparity(Z_true, rig)
    est = scale_to_depth(Estimate(value=d, variance=np.full(d.shape, 1.0)), rig)
    ratio = est.variance[0, 1] / est.variance[0, 0]
    np.testing.assert_allclose(ratio, 2.0**4, rtol=1e-9)


def test_fusion_never_increases_variance():
    a = Estimate(np.full((4, 4), 1.0), np.full((4, 4), 0.5))
    b = Estimate(np.full((4, 4), 1.2), np.full((4, 4), 0.5))
    fused = fuse_mle([a, b])
    assert np.all(fused.variance <= a.variance + 1e-12)
    np.testing.assert_allclose(fused.variance, 0.25)


def test_fusion_weights_by_precision():
    precise = Estimate(np.array([1.0]), np.array([0.01]))
    vague = Estimate(np.array([5.0]), np.array([100.0]))
    fused = fuse_mle([precise, vague])
    assert abs(fused.value[0] - 1.0) < 0.01


def test_invalid_cue_contributes_nothing():
    good = Estimate(np.array([2.0, 2.0]), np.array([1.0, 1.0]))
    partly_bad = Estimate(np.array([9.0, np.nan]), np.array([1.0, np.nan]))
    fused = fuse_mle([good, partly_bad])
    assert fused.value[1] == 2.0  # untouched by the invalid entry
    assert fused.variance[1] == 1.0
    assert fused.value[0] == 5.5  # genuinely fused where both are valid


def test_fusion_of_all_invalid_is_nan():
    bad = Estimate(np.array([np.nan]), np.array([np.nan]))
    assert np.isnan(fuse_mle([bad, bad]).value[0])
