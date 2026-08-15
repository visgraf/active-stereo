"""Shared types and the uncertainty-first-class invariant."""

import numpy as np
import pytest

from activestereo.types import Estimate, StereoRig


def test_rig_rejects_nonphysical_parameters():
    with pytest.raises(ValueError, match="baseline"):
        StereoRig(baseline=0.0, focal_px=800.0)
    with pytest.raises(ValueError, match="focal_px"):
        StereoRig(baseline=0.064, focal_px=-1.0)


def test_estimate_rejects_shape_mismatch():
    with pytest.raises(ValueError, match="shape mismatch"):
        Estimate(value=np.zeros((2, 2)), variance=np.zeros((3, 3)))


def test_precision_is_zero_on_invalid_entries():
    e = Estimate(
        value=np.array([1.0, np.nan, 3.0]),
        variance=np.array([0.25, np.nan, 0.0]),
    )
    np.testing.assert_allclose(e.precision, [4.0, 0.0, 0.0])
    np.testing.assert_array_equal(e.valid, [True, False, True])
