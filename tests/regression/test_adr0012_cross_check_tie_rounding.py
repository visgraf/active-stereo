"""ADR-0012: the cross-check rounds the *target*, half away from zero.

Discovered by running our `matched` against Middlebury's own mask generator
(`MiddEval3-SDK-1.6/code/computemask.cpp`) on real ground truth. They agreed on
99.9995% of pixels -- 6 disagreements in 1.15M -- which is exactly the size of
error that gets called noise and waved through.

Every one of the six was an exact-half disparity, and there were two independent
causes:

1. **Rounding the disparity instead of the target.** ``x - rint(d)`` is not
   ``rint(x - d)``. With ``d = 131.5`` at ``x = 2395`` the first gives 2263 and
   the second 2264. Which one wins depends on the *parity of the column index*,
   which is not a property of the scene.
2. **Tie-break direction.** ``np.rint`` rounds halves to even; C's ``round`` --
   and so Middlebury's generator -- rounds halves away from zero.

Neither is reachable from continuous ground truth: a rendered depth map produces
an exact half essentially never, which is why the Blender path was unaffected and
why this survived until real data arrived. A quantised structured-light scanner
produces them constantly.

These tests are written against the *invariant*, not against a captured output,
so a future rewrite of the cross-check is free to be faster and not free to be
differently wrong.
"""

from __future__ import annotations

import numpy as np
import pytest

from activestereo.scenes.base import cross_check_disparity

pytestmark = pytest.mark.regression


def _probe(x, d, partner_col, width=40):
    """One left pixel at column ``x`` with disparity ``d``; one candidate partner.

    Everything else is unknown or wildly mismatched, so ``matched[0, x]`` is true
    exactly when the implementation looked at ``partner_col``. That makes the
    rounding rule directly observable instead of inferred.
    """
    d0 = np.full((1, width), np.inf)
    d0[0, x] = d
    d1 = np.full((1, width), 999.0)
    d1[0, partner_col] = d
    return bool(cross_check_disparity(d0, d1, 1.0)[0, x])


def test_ties_round_away_from_zero_not_to_even():
    """x = 5, d = 2.5 -> target 2.5. Away from zero gives 3; to even gives 2.

    Rounding the *target* is identical either way here, so this isolates the
    tie-break direction and nothing else.
    """
    assert _probe(5, 2.5, partner_col=3), "half should round away from zero, to column 3"
    assert not _probe(5, 2.5, partner_col=2), "column 2 is where np.rint's to-even lands"


def test_the_target_is_rounded_not_the_disparity():
    """x = 21, d = 11.5 -> target 9.5, which rounds to 10.

    Rounding the disparity first instead gives ``rint(11.5) = 12`` and therefore
    column 9. Both tie-break rules agree on this target, so this isolates *what*
    gets rounded and nothing else.

    Rounding the target is also the defensible operation independently of
    matching Middlebury: it is the coordinate actually used to index the partner
    field, and rounding the disparity makes the answer depend on the parity of
    the column index, which is not a property of the scene.
    """
    assert _probe(21, 11.5, partner_col=10), "the target 9.5 rounds to column 10"
    assert not _probe(21, 11.5, partner_col=9), "column 9 comes from rounding the disparity"


def test_both_faults_together_on_the_case_that_exposed_them():
    """x = 20, d = 11.5 -> target 8.5 -> column 9.

    Here the two faults compound: to-even rounding of the target gives 8, and
    rounding the disparity also gives 8. Only doing both correctly reaches 9.
    """
    assert _probe(20, 11.5, partner_col=9)
    assert not _probe(20, 11.5, partner_col=8)


def test_quantised_ground_truth_is_where_this_bites():
    """The property that made it invisible for three experiments.

    Continuous disparity never lands on a tie, so the Blender and RDS paths could
    not reach either bug. Asserting that keeps the reason on record -- if a future
    stimulus family starts quantising, this is the test that explains why its
    occlusion numbers moved.
    """
    rng = np.random.default_rng(0)
    continuous = rng.uniform(1.0, 30.0, (64, 64))
    assert not np.any(continuous % 1.0 == 0.5), "continuous GT should not produce ties"

    quantised = np.round(continuous * 2.0) / 2.0
    assert np.mean(quantised % 1.0 == 0.5) > 0.4, "half-quantised GT is ~half ties"
