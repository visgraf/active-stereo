"""L5 — vergence estimation and Kalman filtering."""

import numpy as np

from activestereo.control import VergenceKalman, estimate_vergence_disparity
from activestereo.types import Estimate


def test_kalman_converges_to_constant_measurement():
    kf = VergenceKalman(dt=1 / 60, process_var=1e-4)
    for _ in range(200):
        kf.step(0.064, 1e-4)
    assert abs(kf.angle - 0.064) < 1e-3


def test_kalman_coasts_when_measurement_refused():
    """A (nan, inf) measurement means 'no usable data'. The filter must predict
    through it, not diverge or crash."""
    kf = VergenceKalman(dt=1 / 60)
    for _ in range(20):
        kf.step(0.05, 1e-4)
    before = kf.angle
    for _ in range(10):
        kf.step(float("nan"), float("inf"))
    assert np.isfinite(kf.angle)
    assert abs(kf.angle - before) < 0.05
    assert kf.angle_var > 0


def test_uncertainty_grows_while_coasting():
    kf = VergenceKalman(dt=1 / 60, process_var=1e-2)
    kf.step(0.05, 1e-4)
    v0 = kf.angle_var
    for _ in range(30):
        kf.step(float("nan"), float("inf"))
    assert kf.angle_var > v0, "coasting without measurements must increase uncertainty"


def test_vergence_refuses_when_window_is_mostly_invalid():
    value = np.full((40, 40), np.nan)
    value[20, 20] = 3.0
    variance = np.where(np.isfinite(value), 0.1, np.nan)
    d, var = estimate_vergence_disparity(Estimate(value, variance), window=15)
    assert np.isnan(d) and np.isinf(var)
