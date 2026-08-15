"""Shared fixtures. Deterministic by construction: no global RNG anywhere."""

from __future__ import annotations

import numpy as np
import pytest

from activestereo.types import Estimate, StereoRig


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(20260815)


@pytest.fixture
def rig() -> StereoRig:
    """A plausible desktop-XR rig: 64 mm baseline, 800 px focal, fixating ~1 m."""
    return StereoRig(baseline=0.064, focal_px=800.0, vergence=2 * np.arctan(0.064 / 2 / 1.0))


@pytest.fixture
def parallel_rig() -> StereoRig:
    return StereoRig(baseline=0.064, focal_px=800.0, vergence=0.0)


@pytest.fixture
def synthetic_pair(rng: np.random.Generator):
    """Textured left/right pair with a known constant ground-truth disparity."""

    def _make(shape=(64, 96), disparity=8, noise=0.01):
        H, W = shape
        # Matcher convention: left[x] matches right[x - d].
        base = rng.random((H, W + disparity))
        left = base[:, :W]
        right = base[:, disparity : disparity + W]
        left = left + rng.normal(0, noise, left.shape)
        right = right + rng.normal(0, noise, right.shape)
        return left, right, float(disparity)

    return _make


@pytest.fixture
def depth_estimate() -> Estimate:
    """A depth field with a rectangular invalid (occluded) band."""
    value = np.full((40, 60), 1.5)
    variance = np.full((40, 60), 0.01)
    value[10:20, 25:35] = np.nan
    variance[10:20, 25:35] = np.nan
    return Estimate(value=value, variance=variance)
