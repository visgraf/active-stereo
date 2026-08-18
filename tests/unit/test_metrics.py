"""Shared scoring definitions.

These are the numbers three experiments are stated in, so they are tested against
hand-computable stimuli rather than against each other. A metric that is
self-consistently wrong would still let exp001, exp003 and exp004 agree with one
another and disagree with reality.

The "reproduces the published numbers" check lives in
`scripts/make_comparative_figures.py`, which needs the actual corpora and cannot
run in the suite.
"""

from __future__ import annotations

import numpy as np
import pytest

from activestereo.metrics import (
    bad_pixel_rate,
    coverage,
    hallucination_rate,
    local_contrast,
    pooled_variance_by_region,
    score_all,
    variance_by_contrast,
    variance_ratio,
)
from activestereo.scenes.base import StereoStimulus
from activestereo.types import Estimate, StereoRig

H, W = 10, 20


@pytest.fixture
def rig():
    return StereoRig(baseline=0.064, focal_px=800.0, vergence=0.05)


def make_stim(rig, *, occluded_cols=slice(2, 4), unknown_cols=None, border=2):
    """A stimulus with a known occlusion band, a known border, and optional holes.

    Laid out so every count below is countable by hand:
      - columns [0, border)      -> out of frame
      - `occluded_cols`          -> in frame, not matched  = occluded
      - `unknown_cols`           -> known = False
      - everything else          -> matched
    """
    matched = np.ones((H, W), bool)
    in_frame = np.ones((H, W), bool)
    in_frame[:, :border] = False
    matched[:, :border] = False
    matched[:, occluded_cols] = False

    known = None
    if unknown_cols is not None:
        known = np.ones((H, W), bool)
        known[:, unknown_cols] = False

    return StereoStimulus(
        left=np.zeros((H, W)),
        right=np.zeros((H, W)),
        depth=np.full((H, W), 1.5),
        disparity=np.full((H, W), 10.0),
        matched=matched,
        in_frame=in_frame,
        rig=rig,
        known=known,
    )


def make_est(value=10.0, variance=1.0, unanswered=None):
    v = np.full((H, W), float(value))
    var = np.full((H, W), float(variance))
    if unanswered is not None:
        v[:, unanswered] = np.nan
        var[:, unanswered] = np.nan
    return Estimate(value=v, variance=var)


# --- coverage and hallucination --------------------------------------------


def test_coverage_is_over_scorable_not_the_whole_frame(rig):
    """Border and occluded pixels are not the matcher's to answer, so they do not
    belong in the denominator. Using the frame would make a matcher look worse on
    a stimulus with more occlusion."""
    stim = make_stim(rig)
    assert coverage(stim, make_est()) == 1.0

    # Decline on half the scorable columns: 16 scorable columns, 8 blanked.
    est = make_est(unanswered=slice(4, 12))
    assert coverage(stim, est) == pytest.approx(0.5)


def test_hallucination_is_over_occluded_only(rig):
    stim = make_stim(rig)
    assert stim.occluded.sum() == H * 2
    assert hallucination_rate(stim, make_est()) == 1.0
    assert hallucination_rate(stim, make_est(unanswered=slice(2, 4))) == 0.0


def test_unknown_pixels_leave_both_denominators(rig):
    """ADR-0011. A scanner hole is not a matcher failure and not an occlusion."""
    stim = make_stim(rig, unknown_cols=slice(6, 10))
    # 20 columns - 2 border - 2 occluded - 4 unknown = 12 scorable columns.
    assert stim.scorable.sum() == H * 12
    assert coverage(stim, make_est()) == 1.0

    # Answering everywhere except the holes must not read as declining.
    assert coverage(stim, make_est(unanswered=slice(6, 10))) == 1.0


def test_bad_rate_counts_only_answered_scorable(rig):
    stim = make_stim(rig)
    assert bad_pixel_rate(stim, make_est(value=10.0), threshold=2.0) == 0.0
    assert bad_pixel_rate(stim, make_est(value=13.0), threshold=2.0) == 1.0
    assert bad_pixel_rate(stim, make_est(value=11.5), threshold=2.0) == 0.0


# --- variance ---------------------------------------------------------------


def test_variance_ratio_is_occluded_over_matched(rig):
    stim = make_stim(rig)
    var = np.full((H, W), 4.0)
    var[:, 2:4] = 1.0  # occluded band reports LOWER variance
    est = Estimate(value=np.full((H, W), 10.0), variance=var)
    assert variance_ratio(stim, est) == pytest.approx(0.25)

    var[:, 2:4] = 40.0
    assert variance_ratio(stim, Estimate(np.full((H, W), 10.0), var)) == pytest.approx(10.0)


def test_variance_ratio_below_one_is_the_anti_calibrated_case(rig):
    """The distinction the whole exp004 finding rests on: under-confident is
    ratio > 1 but small; anti-calibrated is ratio < 1. They are different signs of
    the same quantity and must not be conflated by an abs() anywhere."""
    stim = make_stim(rig)
    var = np.full((H, W), 10.0)
    var[:, 2:4] = 3.0
    ratio = variance_ratio(stim, Estimate(np.full((H, W), 10.0), var))
    assert ratio < 1.0


def test_pooled_variance_leaves_aggregation_to_the_caller(rig):
    """Returns one number per region per frame, deliberately. exp003's 637x
    depends on pooling within a frame then medianing across frames; doing it the
    other way gives 730x, and the module must not pick silently."""
    stim = make_stim(rig)
    var = np.full((H, W), 2.0)
    var[:, 2:4] = 8.0
    est = Estimate(value=np.full((H, W), 10.0), variance=var)
    out = pooled_variance_by_region(
        stim, est, {"matched": stim.scorable, "occluded": stim.occluded}
    )
    assert out["matched"] == pytest.approx(2.0)
    assert out["occluded"] == pytest.approx(8.0)


# --- contrast ---------------------------------------------------------------


def test_local_contrast_is_zero_on_a_constant_image():
    assert np.allclose(local_contrast(np.full((H, W), 0.4), window=3), 0.0)


def test_local_contrast_rises_with_structure():
    rng = np.random.default_rng(0)
    flat = np.full((H, W), 0.5)
    noisy = rng.random((H, W))
    assert np.median(local_contrast(noisy, 3)) > np.median(local_contrast(flat, 3))


def test_variance_by_contrast_splits_at_the_scorable_median(rig):
    """The split point is a property of *this frame's matched pixels*, so "high
    contrast" means high relative to what the matcher usually succeeds on. A fixed
    constant would mean different things on random dots and a photograph."""
    stim = make_stim(rig)

    contrast = np.zeros((H, W))
    contrast[: H // 2] = 1.0  # top half high contrast
    var = np.full((H, W), 5.0)
    var[: H // 2, 2:4] = 0.5  # high-contrast occlusions: confidently wrong
    var[H // 2 :, 2:4] = 50.0  # low-contrast occlusions: honestly unsure
    est = Estimate(value=np.full((H, W), 10.0), variance=var)

    out = variance_by_contrast(stim, est, contrast=contrast)
    assert out["occluded_hi"] == pytest.approx(0.5)
    assert out["occluded_lo"] == pytest.approx(50.0)
    assert out["n_hi"] == (H // 2) * 2
    assert out["n_lo"] == (H // 2) * 2
    # The overall ratio hides the split entirely -- which is the point of the control.
    assert 0.5 < variance_ratio(stim, est) < 50.0


def test_variance_by_contrast_requires_an_image_or_a_contrast_map(rig):
    with pytest.raises(ValueError, match="either"):
        variance_by_contrast(make_stim(rig), make_est())


def test_score_all_covers_every_metric(rig):
    out = score_all(make_stim(rig), make_est(), image=np.zeros((H, W)))
    for key in (
        "coverage",
        "hallucination",
        "bad_rate",
        "variance_ratio",
        "occluded_hi",
        "occluded_lo",
        "unknown_fraction",
    ):
        assert key in out
