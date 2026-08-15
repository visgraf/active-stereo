"""Regression: ADR-0001 -- windowed-median vergence, not single-pixel.

Failure this guards against
---------------------------
Reading vergence disparity from the single foveal pixel made the control loop
oscillate: one bad match at the fovea produced a large spurious vergence error,
the loop responded, and the response moved the fovea onto different bad data.

The windowed median is robust to exactly this: a minority of outliers cannot move
it. These tests fail if anyone reverts to a point sample or swaps the median for
a mean.
"""

import numpy as np
import pytest

from activestereo.control import estimate_vergence_disparity
from activestereo.types import Estimate

pytestmark = pytest.mark.regression


def _field_with_foveal_outlier(true_d=4.0, outlier=40.0, shape=(41, 41)):
    value = np.full(shape, true_d)
    variance = np.full(shape, 0.1)
    value[shape[0] // 2, shape[1] // 2] = outlier  # the fovea is the bad pixel
    return Estimate(value, variance)


def test_single_outlier_at_fovea_does_not_move_the_estimate():
    est = _field_with_foveal_outlier(true_d=4.0, outlier=40.0)
    d, _ = estimate_vergence_disparity(est, window=15)
    assert abs(d - 4.0) < 0.01, (
        "vergence followed a single foveal outlier -- did someone revert to a "
        "point sample? See docs/decisions/0001-windowed-median-vergence.md"
    )


def test_robust_to_a_large_minority_of_outliers():
    rng = np.random.default_rng(0)
    shape = (41, 41)
    value = np.full(shape, 4.0)
    idx = rng.choice(value.size, size=int(0.3 * value.size), replace=False)
    value.flat[idx] = rng.uniform(-30, 30, idx.size)
    est = Estimate(value, np.full(shape, 0.1))
    d, _ = estimate_vergence_disparity(est, window=21)
    assert abs(d - 4.0) < 0.5, "30% outliers moved the estimate: mean, not median?"


def test_estimator_variance_shrinks_with_window_size():
    """More samples, less uncertainty. Guards the 1/n in the median's variance."""
    est = Estimate(np.full((61, 61), 4.0), np.full((61, 61), 0.1))
    _, var_small = estimate_vergence_disparity(est, window=5)
    _, var_large = estimate_vergence_disparity(est, window=31)
    assert var_large < var_small


def test_refuses_rather_than_guesses_on_sparse_data():
    """Returning (nan, inf) lets the Kalman filter coast. Returning a number from
    two valid pixels would be a confident lie."""
    value = np.full((41, 41), np.nan)
    value[20, 20:22] = 4.0
    variance = np.where(np.isfinite(value), 0.1, np.nan)
    d, var = estimate_vergence_disparity(Estimate(value, variance), window=15)
    assert np.isnan(d) and np.isinf(var)
