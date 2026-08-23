"""Scoring definitions shared by every experiment.

Three experiments have now measured overlapping things in non-overlapping ways.
exp001 published an occlusion hallucination rate but no variance ratio; exp003
published variance ratios but never measured hallucination; exp004 published both
plus a contrast stratification neither of the others attempted. Each computed its
own statistics inline, which was fine while the questions were separate and stops
being fine the moment anyone puts the three in one table.

Everything here takes a :class:`StereoStimulus` and an :class:`Estimate`, so the
``known`` mask (ADR-0011) is honoured for free and the same code runs on random
dots, renders and photographs. That is the point: a cross-family comparison is
only worth making if the definitions are identical, and the cheapest way to
guarantee that is to have one implementation.

**What is comparable across stimulus families and what is not.** Rates and ratios
are dimensionless and travel. Absolute errors do not: the families differ in rig,
depth range, image size and disparity range, so a millimetre is not a millimetre.
Disparity range in particular is a live confound -- a matcher searching 247
candidates has more chances to find a spurious minimum than one searching 48 --
so report it alongside anything that involves the word "hallucination".
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from activestereo.types import Estimate, FloatArray
from activestereo.utils import boxsum

if TYPE_CHECKING:
    from activestereo.scenes.base import StereoStimulus


def _median(a: FloatArray) -> float:
    """Median of the finite entries; ``nan`` when there are none."""
    finite = np.asarray(a)[np.isfinite(a)]
    return float(np.median(finite)) if finite.size else float("nan")


def answered(est: Estimate) -> NDArray[np.bool_]:
    """Where the matcher committed to a value."""
    return np.asarray(np.isfinite(est.value))


def coverage(stim: StereoStimulus, est: Estimate) -> float:
    """Fraction of *scorable* pixels the matcher answered.

    Scorable is ``matched & known``: a correspondent exists and we know where it
    is. Declining on a pixel that has no correspondent is correct behaviour and
    does not belong in this denominator -- that is :func:`hallucination_rate`.
    """
    scorable = stim.scorable
    return float(answered(est)[scorable].mean()) if scorable.any() else float("nan")


def hallucination_rate(stim: StereoStimulus, est: Estimate) -> float:
    """Fraction of ground-truth half-occlusions filled with a confident answer.

    The operationally decisive number in this project. A matcher returning ``nan``
    in a half-occlusion is telling the truth; one returning a value is injecting a
    fabricated measurement into inverse-variance fusion at L4.
    """
    occ = stim.occluded
    return float(answered(est)[occ].mean()) if occ.any() else float("nan")


def bad_pixel_rate(stim: StereoStimulus, est: Estimate, threshold: float = 2.0) -> float:
    """Fraction of answered scorable pixels wrong by more than ``threshold`` px.

    Middlebury's leaderboard metric at ``threshold=2.0``. Comparable across
    families only in the weak sense that the threshold is in pixels; the families
    differ in how hard they are.
    """
    err = np.abs(est.value - stim.disparity)
    graded = stim.scorable & answered(est) & np.isfinite(err)
    return float((err[graded] > threshold).mean()) if graded.any() else float("nan")


def variance_ratio(stim: StereoStimulus, est: Estimate) -> float:
    """Median reported variance in half-occlusions, over that in matched regions.

    The calibration number. Above 1 the matcher is at least *less* sure where it
    is fabricating; below 1 it is **more** sure, which is the anti-calibration
    exp004 measured on photographs.

    Both medians pool pixels within the frame. When aggregating across several
    frames, take the median of this ratio per frame rather than a ratio of pooled
    medians -- see :func:`pooled_variance_by_region` for the case where the
    aggregation order is itself load-bearing.
    """
    ok = answered(est) & np.isfinite(est.variance)
    matched = _median(est.variance[stim.scorable & ok])
    occluded = _median(est.variance[stim.occluded & ok])
    if not np.isfinite(matched) or matched <= 0:
        return float("nan")
    return occluded / matched


def pooled_variance_by_region(
    stim: StereoStimulus, est: Estimate, regions: dict[str, NDArray[np.bool_]]
) -> dict[str, float]:
    """Median reported variance within each named region of one frame.

    Exists so the *aggregation order* is a caller's decision rather than a hidden
    one. exp003's headline 637x and 5x come from pooling pixels within a render
    and then taking the median across renders; pooling the other way round --
    per-patch medians, then a median of those -- is equally defensible and gives
    730x. A synthesis that quietly picks the other order disagrees with the record
    of record for no stated reason.

    Returns a per-frame value per region. Aggregate across frames yourself.
    """
    ok = answered(est) & np.isfinite(est.variance)
    return {name: _median(est.variance[mask & ok]) for name, mask in regions.items()}


def local_contrast(image: FloatArray, window: int = 7) -> FloatArray:
    """Local standard deviation over a ``window x window`` box.

    Masked before mixing, per ADR-0002.

    Computed on the *image*, not on an albedo pass. A photograph has no albedo
    pass, and exp003 showed that image contrast conflates albedo texture with
    shading gradient -- a uniform wall under a raking light reads as textured
    here. That limitation is inherited by anything using this as a stratifier and
    should be stated rather than papered over.

    Related, deliberately not shared: ``scenes.blender.albedo_texture_contrast``
    is the same operator applied to an albedo pass, with a support threshold this
    one does not have. It is left alone because exp003's published texture
    contrasts were produced by it, and the shift below changes results in the last
    few digits. Two copies is where ``boxsum`` was before issue #5; a third would
    be the point to unify them.
    """
    r = window // 2
    valid = np.isfinite(image)

    # Shift by the global mean before accumulating. `E[x^2] - E[x]^2` on a
    # near-constant patch subtracts two nearly equal large numbers, and the
    # summed-area table has already accumulated rounding across the whole frame:
    # on a constant image this returns ~5e-8 rather than 0. Variance is invariant
    # to a constant offset, so subtracting one costs nothing and buys about eight
    # orders of magnitude here. It matters because "no texture" is a region this
    # project cares about specifically, and a threshold near zero should not be
    # comparing against numerical dust.
    finite = image[valid]
    shift = float(finite.mean()) if finite.size else 0.0
    filled = np.where(valid, image - shift, 0.0)

    n = boxsum(valid.astype(float), r)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(n > 0, boxsum(filled, r) / np.maximum(n, 1.0), np.nan)
        sq = np.where(n > 0, boxsum(filled**2, r) / np.maximum(n, 1.0), np.nan)
        return np.asarray(np.sqrt(np.maximum(sq - mean**2, 0.0)), dtype=float)


def variance_by_contrast(
    stim: StereoStimulus,
    est: Estimate,
    image: FloatArray | None = None,
    window: int = 7,
    contrast: FloatArray | None = None,
) -> dict[str, float]:
    """Split occluded pixels by local contrast and report variance in each cell.

    The control that turned exp004's finding from "under-confident" to
    "anti-calibrated". The split point is the **median contrast of scorable
    pixels**, so "high contrast" means high relative to what this matcher usually
    succeeds on in this frame, rather than relative to a constant that would mean
    different things on a random-dot pattern and a photograph.

    Pass either ``image`` or a precomputed ``contrast``; the latter matters when
    several right-image variants share one left image and the stratifier must not
    move between them.

    Returns ``matched``, ``occluded_hi``, ``occluded_lo``, the pixel counts, and
    the threshold used.
    """
    if contrast is None:
        if image is None:
            raise ValueError("variance_by_contrast needs either `image` or `contrast`")
        contrast = local_contrast(image, window)

    ok = answered(est) & np.isfinite(est.variance)
    threshold = _median(contrast[stim.scorable])
    hi = stim.occluded & ok & (contrast > threshold)
    lo = stim.occluded & ok & (contrast <= threshold)
    return {
        "matched": _median(est.variance[stim.scorable & ok]),
        "occluded_hi": _median(est.variance[hi]),
        "occluded_lo": _median(est.variance[lo]),
        "n_hi": int(hi.sum()),
        "n_lo": int(lo.sum()),
        "contrast_threshold": threshold,
    }


def score_all(
    stim: StereoStimulus,
    est: Estimate,
    image: FloatArray | None = None,
    bad_threshold: float = 2.0,
    window: int = 7,
    contrast: FloatArray | None = None,
) -> dict[str, float]:
    """Every metric above for one (stimulus, estimate) pair.

    The convenience the synthesis uses, so all three stimulus families are scored
    by one call and cannot drift apart.
    """
    out: dict[str, float] = {
        "coverage": coverage(stim, est),
        "hallucination": hallucination_rate(stim, est),
        "bad_rate": bad_pixel_rate(stim, est, bad_threshold),
        "variance_ratio": variance_ratio(stim, est),
        "n_scorable": int(stim.scorable.sum()),
        "n_occluded": int(stim.occluded.sum()),
        "unknown_fraction": stim.unknown_fraction,
    }
    if image is not None or contrast is not None:
        out.update(variance_by_contrast(stim, est, image=image, window=window, contrast=contrast))
    return out
