"""Regression: ADR-0003 -- Taylor-remainder term confines confidence to the fovea.

Failure this guards against
---------------------------
Without an explicit linearisation-error term the pipeline reported uniform
confidence across the field. Peripheral estimates were trusted as much as foveal
ones, which broke the expected ordering of matchers: block matching appeared to
match or beat SGBM, contradicting theory.

Adding a variance penalty proportional to eta^2 (eccentricity squared) restored
the expected behaviour. These tests pin the properties the term must have.
"""

import numpy as np
import pytest

from activestereo.policy.foveation import (
    confine_to_fovea,
    eccentricity,
    linearization_penalty,
)
from activestereo.types import Estimate

pytestmark = pytest.mark.regression


def test_penalty_is_quadratic_in_eccentricity():
    """Doubling eccentricity must quadruple the penalty. A linear term would not
    confine confidence tightly enough; a quartic one would erase the periphery."""
    shape = (101, 101)
    p = linearization_penalty(shape, coefficient=1.0, normalize=False)
    eta = eccentricity(shape)
    near = np.isclose(eta, 10.0, atol=0.5)
    far = np.isclose(eta, 20.0, atol=0.5)
    ratio = p[far].mean() / p[near].mean()
    assert ratio == pytest.approx(4.0, rel=0.05), (
        "penalty is not quadratic in eta -- see docs/decisions/0003-foveal-confinement.md"
    )


def test_penalty_is_zero_at_the_fovea():
    p = linearization_penalty((51, 51), coefficient=1.0)
    assert p[25, 25] == pytest.approx(0.0, abs=1e-12)


def test_penalty_increases_monotonically_outward():
    p = linearization_penalty((81, 81), coefficient=1.0)
    row = p[40, 40:]
    assert np.all(np.diff(row) >= -1e-12)


def test_confinement_never_manufactures_confidence():
    """Variance may only increase. If this ever fails, the periphery is being
    reported as more certain than it is -- the original bug."""
    e = Estimate(np.full((40, 40), 1.5), np.full((40, 40), 0.01))
    out = confine_to_fovea(e, coefficient=1e-2)
    assert np.all(out.variance >= e.variance - 1e-15)
    np.testing.assert_array_equal(out.value, e.value)


def test_peripheral_estimates_are_downweighted_in_fusion():
    """The operational consequence: after confinement, MLE fusion should prefer a
    foveal measurement over a peripheral one of equal raw precision."""
    from activestereo.scaling import fuse_mle

    shape = (81, 81)
    foveal = confine_to_fovea(Estimate(np.full(shape, 1.0), np.full(shape, 0.01)), coefficient=1.0)
    assert foveal.precision[40, 40] > foveal.precision[40, 78]
    fused = fuse_mle([foveal])
    assert fused.variance[40, 40] < fused.variance[40, 78]


def test_normalization_makes_coefficient_resolution_independent():
    """Same scene, different resolution, same coefficient -> comparable penalty at
    matched relative eccentricity. Without this, every experiment needs recalibration."""
    small = linearization_penalty((51, 51), coefficient=1.0, normalize=True)
    large = linearization_penalty((201, 201), coefficient=1.0, normalize=True)
    assert small[25, 50] == pytest.approx(large[100, 200], rel=0.02)
