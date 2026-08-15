"""Foveal confinement via the linearisation-remainder term.

See ADR-0003. The disparity-to-depth inversion is linearised about the current
fixation; that linearisation is only locally valid. Without an explicit
remainder term the pipeline reports confident depth across the whole field,
peripheral estimates are trusted as much as foveal ones, and the theoretically
expected ordering of matchers inverts.

Adding a Taylor-remainder variance term proportional to eta^2 -- where eta is
eccentricity from the fovea -- restores the expected behaviour and makes SGBM
outperform block matching as the theory predicts.
"""

from __future__ import annotations

import numpy as np

from activestereo.types import Estimate, FloatArray


def eccentricity(shape: tuple[int, int], centre: tuple[int, int] | None = None) -> FloatArray:
    """Radial distance from the fovea in pixels, shape ``shape``."""
    H, W = shape
    r0, c0 = (H // 2, W // 2) if centre is None else centre
    rows, cols = np.indices((H, W))
    return np.hypot(rows - r0, cols - c0).astype(float)


def linearization_penalty(
    shape: tuple[int, int],
    centre: tuple[int, int] | None = None,
    coefficient: float = 1e-4,
    normalize: bool = True,
) -> FloatArray:
    """Second-order Taylor-remainder variance, quadratic in eccentricity.

    ``penalty = coefficient * eta^2``

    Parameters
    ----------
    coefficient : scales the remainder. Physically it absorbs the curvature of the
        depth map and the rig geometry; in practice it is calibrated per scene.
    normalize : express ``eta`` in units of the image half-diagonal, so that
        ``coefficient`` is comparable across resolutions. Keep ``True`` unless you
        have a specific reason -- ADR-0003 records why.
    """
    eta = eccentricity(shape, centre)
    if normalize:
        H, W = shape
        # Distance from centre to the corner *pixel* -- not 0.5*hypot(H, W),
        # which is off by half a pixel and makes resolutions disagree.
        eta = eta / np.hypot((H - 1) / 2.0, (W - 1) / 2.0)
    return coefficient * eta**2


def confine_to_fovea(
    depth: Estimate,
    centre: tuple[int, int] | None = None,
    coefficient: float = 1e-4,
) -> Estimate:
    """Add the eccentricity-dependent remainder to a depth estimate's variance.

    Variance only ever increases, so this can never manufacture confidence. That
    monotonicity is asserted in ``tests/regression/test_adr0003_foveal_confinement.py``.
    """
    penalty = linearization_penalty(depth.value.shape, centre, coefficient)
    return Estimate(value=depth.value, variance=depth.variance + penalty)
