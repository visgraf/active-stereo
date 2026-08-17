"""Regression: exp003 -- what the two matcher failure modes do to variance.

Failure this guards against
---------------------------
exp003 (issue #4) rendered a material chart spanning dense albedo texture down to
perfectly constant albedo, holding geometry bit-identical across conditions. On
constant-albedo patches both matchers answered ~71-76% of pixels and were wrong
by ~95x the textured error. They were not matching sampler noise: re-rendering at
8x the samples moved nothing, so the structure they locked onto is deterministic
shading.

The result that matters is the *contrast* in reported variance, measured over 12
renders with the block matcher:

    textured, matched        90 px^2      1x
    textureless, matched  57,340 px^2   637x   <- the matcher knows
    half-occluded            426 px^2     5x   <- the matcher does NOT know

Texture loss is reported honestly, so L4's inverse-variance fusion discounts it.
Half-occlusion is not, which corroborates exp001's finding on a different
stimulus class. Half-occlusion is the more dangerous failure precisely because
only one of the two arrives labelled.

An earlier draft of this file asserted the opposite -- that variance was blind to
texture loss -- from reasoning rather than measurement. It was wrong. These tests
exist so the claim stays measured.

These need no Blender: the mechanism reproduces on synthetic arrays.
"""

import itertools

import numpy as np
import pytest

from activestereo.inference import BlockMatcher
from activestereo.scenes.blender import albedo_texture_contrast

pytestmark = pytest.mark.regression


def _smooth_field(shape, amplitude, pad):
    """A smooth irradiance falloff: what a constant-albedo surface looks like
    under a finite area light. Curved rather than a linear ramp, so it carries
    real (if faint) structure instead of being degenerate under shift."""
    rows, cols = np.indices((shape[0], shape[1] + pad))
    r2 = ((cols - 20) / 60.0) ** 2 + ((rows - 10) / 60.0) ** 2
    f = 1.0 / (1.0 + r2)
    f = (f - f.min()) / (f.max() - f.min())
    return 0.5 + amplitude * f


def test_texture_contrast_reports_zero_for_constant_albedo():
    """The measurement that makes the failure diagnosable at all. It must return
    0.0 rather than nan: nan means "no support", a different fact, and it would
    silently drop the textureless condition out of every statistic."""
    contrast = albedo_texture_contrast(np.full((64, 96), 0.5), window=7)
    interior = contrast[4:-4, 4:-4]
    assert np.all(np.isfinite(interior))
    assert float(np.max(interior)) < 1e-9


def test_texture_contrast_separates_textureless_from_textured():
    """The independent variable exp003 bins on. Measured on albedo, never on the
    rendered image: under a raking light a constant-albedo surface carries a
    strong intensity ramp that looks like texture to any statistic computed on
    the beauty pass, but supports matching far more weakly."""
    rng = np.random.default_rng(0)
    textured = albedo_texture_contrast(rng.random((64, 96)), window=7)[4:-4, 4:-4]
    flat = albedo_texture_contrast(_smooth_field((64, 96), 0.003, 0), window=7)[4:-4, 4:-4]
    t, f = float(np.nanmedian(textured)), float(np.nanmedian(flat))
    assert t > 50 * f, f"textured {t:.5f} not separated from textureless {f:.5f}"


def test_variance_grows_as_contrast_falls():
    """The property that makes texture loss survivable downstream.

    L4 fuses by inverse variance, so an estimate that is wrong but *labelled*
    uncertain is discounted automatically. exp003 measured a 637x variance
    inflation on textureless surfaces against ~100x error inflation -- more than
    enough. Here the same relationship is checked synthetically: variance must
    rise steeply and monotonically as image contrast falls.
    """
    matcher = BlockMatcher(max_disparity=16, window=7)
    d0 = 8
    variances = []
    for amplitude in (0.3, 0.05, 0.01, 0.003):
        field = _smooth_field((64, 96), amplitude, d0)
        est = matcher.match(field[:, :96], field[:, d0 : d0 + 96])
        answered = np.isfinite(est.value)
        assert answered.any(), f"no estimate at all at amplitude {amplitude}"
        variances.append(float(np.nanmedian(est.variance[answered])))

    assert all(a < b for a, b in itertools.pairwise(variances)), (
        f"variance did not increase monotonically as contrast fell: {variances}. "
        "If this broke, low-contrast estimates are no longer labelled uncertain "
        "and L4 will fuse them at full weight."
    )
    assert variances[-1] > 100 * variances[0], (
        f"variance rose only {variances[-1] / variances[0]:.1f}x across a 100x "
        "contrast drop. exp003 measured 637x on rendered surfaces; a matcher "
        "that stops flagging low contrast puts wrong depth into fusion at weight."
    )


def test_occlusion_variance_stays_low_the_dangerous_case():
    """Documents the defect, and will fail when it is fixed.

    A half-occluded pixel has no correspondent at all, so any answer is
    fabricated. exp001 found block matching answers 79.6% of them; exp003
    measured the variance it reports there as only ~5x the textured baseline --
    far too confident for a measurement that does not exist. That is the failure
    L4 cannot defend against, unlike texture loss.

    **When L3 grows a left-right consistency check this test should fail.** That
    is the intended outcome: invert it and pin the new behaviour. Do not weaken
    it to keep the suite green.
    """
    rng = np.random.default_rng(3)
    H, W, d0 = 64, 96, 8
    base = rng.random((H, W + d0))
    left, right = base[:, :W].copy(), base[:, d0 : d0 + W].copy()
    # A band present in the left eye only: no correspondent exists anywhere.
    left[:, 30:46] = rng.random((H, 16))

    est = BlockMatcher(max_disparity=16, window=7).match(left, right)
    band = est.variance[:, 34:42]
    good = est.variance[:, 60:90]
    band_var = float(np.nanmedian(band[np.isfinite(band)]))
    good_var = float(np.nanmedian(good[np.isfinite(good)]))
    assert band_var < 50 * good_var, (
        f"occluded-band variance {band_var:.4g} vs matched {good_var:.4g}. If the "
        "gap has widened, L3 now flags fabricated matches and L4 can discount "
        "them -- the exp003 follow-up landed. Invert this assertion."
    )
