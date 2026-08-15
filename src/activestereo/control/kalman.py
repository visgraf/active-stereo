"""Scalar Kalman filter for the vergence state.

State is the vergence angle (radians) and its rate. Constant-velocity model:
adequate because the plant's own dynamics dominate at the timescales of interest,
and because a richer model cannot be identified from the measurements available.
"""

from __future__ import annotations

import numpy as np

from activestereo.types import FloatArray


class VergenceKalman:
    """Constant-velocity Kalman filter on (vergence, vergence_rate).

    Parameters
    ----------
    dt : timestep, seconds.
    process_var : acceleration noise density, rad^2/s^3.
    initial_state : (angle, rate), radians and rad/s.
    initial_var : diagonal of the initial covariance.
    """

    def __init__(
        self,
        dt: float = 1.0 / 60.0,
        process_var: float = 1e-3,
        initial_state: tuple[float, float] = (0.0, 0.0),
        initial_var: tuple[float, float] = (1e-2, 1e-2),
    ) -> None:
        self.dt = float(dt)
        self.process_var = float(process_var)
        self.x = np.array(initial_state, dtype=float)
        self.P = np.diag(np.asarray(initial_var, dtype=float))
        self.F = np.array([[1.0, self.dt], [0.0, 1.0]])
        self.H = np.array([[1.0, 0.0]])
        q = self.process_var
        d = self.dt
        self.Q = q * np.array([[d**3 / 3.0, d**2 / 2.0], [d**2 / 2.0, d]])

    @property
    def angle(self) -> float:
        """Current vergence angle estimate, radians."""
        return float(self.x[0])

    @property
    def angle_var(self) -> float:
        """Current variance of the vergence angle estimate, rad^2."""
        return float(self.P[0, 0])

    def predict(self) -> None:
        """Advance the state one timestep."""
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q

    def update(self, measurement: float, measurement_var: float) -> None:
        """Fold in a vergence measurement.

        A measurement of ``nan`` or infinite variance is a *refusal to measure*
        (see :func:`activestereo.control.vergence.estimate_vergence_disparity`)
        and is skipped: the filter coasts on its prediction. This is what stops a
        texture-poor frame from yanking the eyes.
        """
        if not np.isfinite(measurement) or not np.isfinite(measurement_var):
            return
        z = np.array([measurement], dtype=float)
        R = np.array([[float(measurement_var)]])
        y = z - self.H @ self.x
        S = self.H @ self.P @ self.H.T + R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.x = self.x + (K @ y).ravel()
        self.P = (np.eye(2) - K @ self.H) @ self.P

    def step(self, measurement: float, measurement_var: float) -> FloatArray:
        """Predict then update; returns a copy of the state."""
        self.predict()
        self.update(measurement, measurement_var)
        return self.x.copy()
