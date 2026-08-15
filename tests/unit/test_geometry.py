"""L1 — projection and horopter."""

import numpy as np
import pytest

from activestereo.geometry import (
    depth_to_disparity,
    disparity_to_depth,
    vieth_muller_radius,
)
from activestereo.types import StereoRig


def test_projection_roundtrip(rig):
    Z = np.array([0.5, 0.8, 1.0, 1.5, 3.0])
    d = depth_to_disparity(Z, rig)
    np.testing.assert_allclose(disparity_to_depth(d, rig), Z, rtol=1e-10)


def test_parallel_rig_reduces_to_fb_over_z(parallel_rig):
    Z = np.array([1.0, 2.0])
    d = depth_to_disparity(Z, parallel_rig)
    expected = parallel_rig.focal_px * parallel_rig.baseline / Z
    np.testing.assert_allclose(d, expected, rtol=1e-12)


def test_zero_disparity_on_the_horopter(rig):
    """Points at the fixation distance have zero disparity, by definition."""
    Z = np.array([rig.fixation_distance])
    np.testing.assert_allclose(depth_to_disparity(Z, rig), [0.0], atol=1e-12)


def test_disparity_sign_convention(rig):
    """Positive = crossed = nearer than fixation (CLAUDE.md section 3)."""
    Zf = rig.fixation_distance
    assert depth_to_disparity(np.array([Zf * 0.5]), rig)[0] > 0
    assert depth_to_disparity(np.array([Zf * 2.0]), rig)[0] < 0


def test_invalid_depth_maps_to_nan(rig):
    d = depth_to_disparity(np.array([-1.0, 0.0, np.nan, np.inf]), rig)
    assert np.isnan(d).all()


def test_vieth_muller_radius_matches_inscribed_angle():
    rig = StereoRig(baseline=0.064, focal_px=800.0, vergence=0.1)
    assert vieth_muller_radius(rig) == pytest.approx(0.064 / (2 * np.sin(0.1)))


def test_horopter_degenerates_at_zero_vergence(parallel_rig):
    assert np.isinf(vieth_muller_radius(parallel_rig))
