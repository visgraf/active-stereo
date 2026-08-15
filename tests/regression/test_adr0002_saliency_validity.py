"""Regression: ADR-0002 -- mask invalid pixels BEFORE blurring the saliency map.

Failure this guards against
---------------------------
The active-gaze loop hung. An occlusion band is geometrically unresolvable: no
fixation can produce a match there. Because invalid pixels were blurred in as
maximal uncertainty, the band was maximally salient, so the policy fixated it
every iteration, forever.

The fix is normalised convolution (`masked_blur`), which mixes only valid
neighbours, plus inhibition of return in the gaze policy.
"""

import numpy as np
import pytest

from activestereo.policy import masked_blur, next_fixation, uncertainty_saliency

pytestmark = pytest.mark.regression


def test_masked_blur_does_not_leak_invalid_pixels():
    field = np.ones((21, 21))
    valid = np.ones((21, 21), dtype=bool)
    field[10, 10] = 1000.0
    valid[10, 10] = False  # huge value, but invalid -- must not contaminate
    out = masked_blur(field, valid, sigma=2.0)
    finite = np.isfinite(out)
    assert np.allclose(out[finite], 1.0, atol=1e-6), (
        "an invalid pixel's value leaked through the blur -- was masked_blur "
        "replaced by a plain Gaussian? See docs/decisions/0002-saliency-validity-masking.md"
    )


def test_plain_blur_would_have_leaked():
    """Demonstrates the bug being guarded against, so the guard has a referent."""
    from activestereo.policy.saliency import _gaussian_blur

    field = np.ones((21, 21))
    field[10, 10] = 1000.0
    naive = _gaussian_blur(field, sigma=2.0)
    assert naive[10, 10] > 2.0, "counterexample no longer demonstrates the failure"


def test_occlusion_band_is_not_the_saliency_maximum(depth_estimate):
    """The invalid band is unknowable, not uncertain. It must not attract gaze."""
    sal = uncertainty_saliency(depth_estimate, sigma=3.0)
    target = next_fixation(sal)
    assert target is not None
    r, c = target
    invalid = ~depth_estimate.valid
    assert not invalid[r, c], "gaze policy targeted a geometrically invalid pixel"


def test_active_loop_terminates_on_unresolvable_occlusion(depth_estimate):
    """The real symptom: the loop must finish, not spin. Bounded iterations."""
    sal = uncertainty_saliency(depth_estimate, sigma=3.0)
    visited: list[tuple[int, int]] = []
    for _ in range(50):
        target = next_fixation(sal, visited=visited, inhibition_radius=12.0)
        if target is None:
            break
        visited.append(target)
    else:
        pytest.fail("active-sampling loop did not terminate within 50 fixations")
    assert len(visited) < 50


def test_no_fixation_repeats():
    """Inhibition of return actually inhibits."""
    rng = np.random.default_rng(1)
    sal = rng.random((60, 60))
    visited: list[tuple[int, int]] = []
    for _ in range(15):
        t = next_fixation(sal, visited=visited, inhibition_radius=8.0)
        if t is None:
            break
        assert t not in visited
        visited.append(t)
