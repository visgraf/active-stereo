"""L3 — matcher contract compliance."""

import numpy as np
import pytest

from activestereo.inference import BlockMatcher, DisparityMatcher
from activestereo.types import Estimate


def test_block_matcher_satisfies_protocol():
    assert isinstance(BlockMatcher(), DisparityMatcher)


def test_recovers_known_disparity(synthetic_pair):
    left, right, d_true = synthetic_pair(shape=(48, 80), disparity=6)
    est = BlockMatcher(max_disparity=16, window=7).match(left, right)
    interior = est.value[8:-8, 20:-8]
    valid = np.isfinite(interior)
    assert valid.mean() > 0.5, "matcher rejected most of a well-textured interior"
    assert abs(np.median(interior[valid]) - d_true) < 1.0


def test_output_shape_matches_input(synthetic_pair):
    left, right, _ = synthetic_pair(shape=(32, 48), disparity=4)
    est = BlockMatcher(max_disparity=16).match(left, right)
    assert est.value.shape == left.shape == est.variance.shape


def test_invalid_pixels_are_nan_not_sentinel(synthetic_pair):
    """CLAUDE.md section 3: invalid means nan. A -1 or 0 sentinel would silently
    become a real depth downstream."""
    left, right, _ = synthetic_pair(shape=(32, 48), disparity=4)
    est = BlockMatcher(max_disparity=16).match(left, right)
    invalid = ~est.valid
    if invalid.any():
        assert np.isnan(est.value[invalid]).all()
        assert np.isnan(est.variance[invalid]).all()


def test_matcher_is_deterministic(synthetic_pair):
    left, right, _ = synthetic_pair(shape=(32, 48), disparity=4)
    m = BlockMatcher(max_disparity=16)
    a, b = m.match(left, right), m.match(left, right)
    sentinel = -999.0
    np.testing.assert_array_equal(
        np.nan_to_num(a.value, nan=sentinel), np.nan_to_num(b.value, nan=sentinel)
    )


def test_rejects_even_window():
    with pytest.raises(ValueError, match="odd"):
        BlockMatcher(window=8)


def test_untextured_region_is_rejected_not_guessed():
    """A flat region has no matching evidence. Returning a confident zero there is
    the failure mode; returning nan is correct."""
    flat = np.full((32, 48), 0.5)
    est = BlockMatcher(max_disparity=16, window=7, uniqueness=0.05).match(flat, flat)
    assert isinstance(est, Estimate)
    assert est.valid.mean() < 0.2
