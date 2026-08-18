"""exp004 -- does the uncertainty-calibration finding survive real photographs?

Hypotheses, falsifiers, the declared peek and threats to validity live in
``config.yaml`` and in issue #6. This runner is deliberately thin: all reusable
logic belongs in ``src``.

Fetch the corpus first (~1 GB, outside the repository)::

    python scripts/fetch_middlebury.py

then::

    python -m experiments.exp004_real_data_transfer.run \
        --config experiments/exp004_real_data_transfer/config.yaml
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from activestereo.inference import BlockMatcher
from activestereo.scaling import scale_to_depth
from activestereo.scenes import from_config
from activestereo.scenes.base import cross_check_disparity
from activestereo.scenes.middlebury import MiddleburyScene
from activestereo.types import Estimate, FloatArray, StereoRig
from activestereo.utils import RunContext, boxsum, load_config

#: Middlebury's leaderboard metric. Reported as an order-of-magnitude sanity
#: check only: we downsample and they do not (ADR-0012).
BAD_THRESHOLD = 2.0

#: exp001's occlusion hallucination rate for block matching on random dots. H1's
#: second falsifier is stated relative to it.
EXP001_RDS_HALLUCINATION = 0.796


def build_matchers(scene: MiddleburyScene, cfg: dict) -> dict:
    """One matcher set per scene: the search range is a property of the scene.

    ``ndisp`` comes from ``calib.txt`` and differs per scene by a factor of three
    across this corpus, so a single corpus-wide value would either truncate the
    hard scenes or waste most of the volume on the easy ones.
    """
    ceiling = int(cfg["matcher"]["max_disparity"])
    if scene.ndisp > ceiling:
        raise SystemExit(
            f"{scene.name}: calib.txt says ndisp={scene.ndisp} at downsample "
            f"{scene.downsample}, above the max_disparity ceiling of {ceiling}.\n"
            "Refusing to truncate. A search range shorter than the scene's true "
            "disparity range does not announce itself downstream -- the nearest "
            "surfaces simply go unmatched, which is indistinguishable from the "
            "matcher failing on them, and it biases coverage and error on exactly "
            "the pixels that are easiest to match.\n"
            "Raise matcher.max_disparity, or increase scene.downsample."
        )
    ndisp = scene.ndisp

    matchers: dict = {
        "block": BlockMatcher(max_disparity=ndisp, window=cfg["matcher"]["window"])
    }
    try:
        from activestereo.inference.sgbm import SGBMMatcher

        # SGBM requires a multiple of 16. Round UP: rounding down would silently
        # truncate the search range below the scene's true maximum disparity, so
        # the far surfaces would be scored as matcher failures rather than as a
        # range we never looked in.
        matchers["sgbm"] = SGBMMatcher(max_disparity=-(-ndisp // 16) * 16)
    except ImportError:
        print("OpenCV unavailable; running block matcher only.")
    return matchers


def local_contrast(image: FloatArray, window: int) -> FloatArray:
    """Local standard deviation over a ``window x window`` box.

    The stratifier for control 4. Computed on the *image*, not on an albedo pass:
    there is no albedo pass here, and that limitation is exactly what exp003
    warned about -- on real photographs "texture" and "shading gradient" cannot
    be separated. Said plainly in findings rather than papered over.
    """
    r = window // 2
    valid = np.isfinite(image)
    filled = np.where(valid, image, 0.0)
    n = boxsum(valid.astype(float), r)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(n > 0, boxsum(filled, r) / np.maximum(n, 1.0), np.nan)
        sq = np.where(n > 0, boxsum(filled**2, r) / np.maximum(n, 1.0), np.nan)
        return np.asarray(np.sqrt(np.maximum(sq - mean**2, 0.0)), dtype=float)


def _median(a: FloatArray) -> float:
    finite = a[np.isfinite(a)]
    return float(np.median(finite)) if finite.size else float("nan")


def score(stim, est: Estimate, rig: StereoRig, contrast: FloatArray) -> dict:
    """Every statistic for one (scene, matcher, right-variant) cell.

    Scored on ``scorable`` = matched AND known (ADR-0011). Grading a matcher
    against a pixel whose true disparity nobody knows measures the scanner.
    """
    answered = np.isfinite(est.value)
    err = np.abs(est.value - stim.disparity)
    scorable = stim.scorable
    graded = scorable & answered & np.isfinite(err)

    depth = scale_to_depth(est, rig)
    depth_err = np.abs(depth.value - stim.depth)

    occ = stim.occluded
    var_matched = est.variance[graded & np.isfinite(est.variance)]
    var_occluded = est.variance[occ & answered & np.isfinite(est.variance)]

    # Control 4: split occluded pixels at the median local contrast of matched
    # pixels, so "high contrast" means high relative to what the matcher usually
    # succeeds on rather than relative to an arbitrary constant.
    threshold = _median(contrast[scorable])
    hi = occ & answered & (contrast > threshold) & np.isfinite(est.variance)
    lo = occ & answered & (contrast <= threshold) & np.isfinite(est.variance)

    return {
        "n_scorable": int(scorable.sum()),
        "n_occluded": int(occ.sum()),
        "coverage": float(answered[scorable].mean()) if scorable.any() else float("nan"),
        "bad2": float((err[graded] > BAD_THRESHOLD).mean()) if graded.any() else float("nan"),
        "disparity_error_px": _median(err[graded]),
        "depth_error_m": _median(depth_err[graded]),
        "hallucination": float(answered[occ].mean()) if occ.any() else float("nan"),
        "var_matched_px2": _median(var_matched),
        "var_occluded_px2": _median(var_occluded),
        "var_ratio": (
            _median(var_occluded) / _median(var_matched)
            if var_matched.size and _median(var_matched) > 0
            else float("nan")
        ),
        "var_occluded_hi_contrast_px2": _median(est.variance[hi]),
        "var_occluded_lo_contrast_px2": _median(est.variance[lo]),
        "n_occluded_hi_contrast": int(hi.sum()),
        "contrast_threshold": threshold,
        # A variance that never varies cannot rank anything, so a var_ratio of
        # 1.0 from such an estimator is an identity, not a measurement.
        # SGBMMatcher returns a constant `base_variance` wherever it answers
        # (inference/sgbm.py) -- satisfying the letter of ADR-0005 while carrying
        # no per-pixel information. Recorded per cell so no reader has to know
        # that to interpret the table.
        "variance_spread_px2": float(np.std(var_matched)) if var_matched.size else float("nan"),
        "variance_is_constant": bool(var_matched.size and np.ptp(var_matched) < 1e-12),
    }


def tolerance_sensitivity(scene: MiddleburyScene, tolerances: list[float]) -> dict:
    """Control 3: how much does the occlusion fraction depend on the threshold?

    Our ``matched`` reproduces Middlebury's generator exactly at 1.0 px. That
    validates the implementation and says nothing about whether 1.0 px is right,
    so the sensitivity is measured rather than assumed away.
    """
    from activestereo.scenes.middlebury import _decimate, _in_frame, read_pfm

    k = scene.downsample
    d0 = read_pfm(scene.directory / "disp0.pfm")
    d1 = read_pfm(scene.directory / "disp1.pfm")
    known = _decimate(np.isfinite(d0), k)
    in_frame = _decimate(_in_frame(np.where(np.isfinite(d0), d0, np.nan), d0.shape[1]), k)

    out = {}
    for tol in tolerances:
        matched = _decimate(cross_check_disparity(d0, d1, tolerance=tol), k)
        out[f"{tol:g}px"] = float((in_frame & ~matched & known).mean())
    return out


def run_scene(scene: MiddleburyScene, cfg: dict) -> dict:
    matchers = build_matchers(scene, cfg)
    window = int(cfg["analysis"]["contrast_window"])
    variants = list(cfg["analysis"]["right_variants"])

    base = scene.stimulus("im1")
    contrast = local_contrast(base.left, window)

    cells: dict = {}
    for variant in variants:
        stim = scene.stimulus(variant)
        for name, matcher in matchers.items():
            est = matcher.match(stim.left, stim.right)
            cells.setdefault(name, {})[variant] = score(stim, est, scene.rig, contrast)

    return {
        "shape": list(base.shape),
        "ndisp": scene.ndisp,
        "noise_floor_px": scene.noise_floor(),
        "unknown_fraction": base.unknown_fraction,
        "occlusion_fraction": base.occlusion_fraction,
        "out_of_frame_fraction": float(base.out_of_frame.mean()),
        "tolerance_sweep": tolerance_sensitivity(scene, cfg["analysis"]["tolerance_sweep"]),
        "by_matcher": cells,
    }


def aggregate(
    per_scene: dict, held_out: list[str], matchers: list[str], variants: list[str]
) -> dict:
    """Medians over the **held-out** scenes only. Seen scenes never pool in."""
    out: dict = {}
    for matcher in matchers:
        out[matcher] = {}
        for variant in variants:
            rows = [
                per_scene[s]["by_matcher"][matcher][variant]
                for s in held_out
                if matcher in per_scene[s]["by_matcher"]
            ]
            if not rows:
                continue
            out[matcher][variant] = {
                f"{key}_median": _median(np.array([r[key] for r in rows]))
                for key in (
                    "coverage",
                    "bad2",
                    "disparity_error_px",
                    "depth_error_m",
                    "hallucination",
                    "var_ratio",
                    "var_matched_px2",
                    "var_occluded_px2",
                )
            }
            out[matcher][variant]["n_scenes"] = len(rows)
    return out


def evaluate_hypotheses(summary: dict, per_scene: dict, held_out: list[str]) -> dict:
    """Apply issue #6's falsifiers literally, matcher by matcher."""
    verdicts: dict = {}
    for matcher, variants in summary.items():
        if "im1" not in variants:
            continue
        base = variants["im1"]

        # H1 -- stated for block matching, since exp001's 79.6% is a block-matcher
        # number and the comparison must be like for like.
        ratio = base["var_ratio_median"]
        hall = base["hallucination_median"]
        h1_variance_ok = np.isfinite(ratio) and ratio <= 20.0
        h1_hallucination_ok = np.isfinite(hall) and hall >= 0.5 * EXP001_RDS_HALLUCINATION

        # A constant-variance estimator passes the variance half of H1 by
        # construction: the ratio is exactly 1.0 whatever the image contains.
        # Flagged rather than scored, because "passed" and "could not fail" are
        # different states and only one of them is evidence.
        constant_variance = all(
            per_scene[s]["by_matcher"][matcher]["im1"].get("variance_is_constant", False)
            for s in held_out
            if matcher in per_scene[s]["by_matcher"]
        )

        # H1b -- held-out scenes only, and counted per scene rather than pooled.
        # The falsifier is an absolute count ("3 or more"), which is what issue #6
        # wrote down. Two declared peeks shrank the held-out set from nine scenes
        # to eight; the threshold does not move with it, because a threshold that
        # tracks the sample size is a threshold chosen after seeing the sample.
        ratios = [
            per_scene[s]["by_matcher"][matcher]["im1"]["var_ratio"]
            for s in held_out
            if matcher in per_scene[s]["by_matcher"]
        ]
        above = [r for r in ratios if np.isfinite(r) and r >= 1.0]
        h1b = len(above) < 3

        # H2 -- each photometric variant against im1.
        #
        # Paired per scene, then the median taken: `im1`, `im1E` and `im1L` are the
        # same geometry and the same ground truth, differing only in the right
        # image, so every scene is its own control. A difference of medians would
        # discard that pairing and let scene-to-scene spread in the base coverage
        # -- which runs from Shelves to Jadeplant, i.e. wide -- swamp the effect
        # the design isolates. Fixed before any H2 number was seen.
        h2: dict = {}
        for variant in ("im1E", "im1L"):
            if variant not in variants:
                continue
            paired = [
                (
                    per_scene[s]["by_matcher"][matcher]["im1"],
                    per_scene[s]["by_matcher"][matcher][variant],
                )
                for s in held_out
                if matcher in per_scene[s]["by_matcher"]
            ]
            cov_drops = np.array([a["coverage"] - b["coverage"] for a, b in paired])
            rises = np.array(
                [
                    b["disparity_error_px"] / a["disparity_error_px"] - 1.0
                    if a["disparity_error_px"] > 0
                    else np.nan
                    for a, b in paired
                ]
            )
            cov_drop = _median(cov_drops)
            err_rise = _median(rises)
            h2[variant] = {
                "coverage_drop": float(cov_drop),
                "error_rise_fraction": float(err_rise),
                "per_scene_coverage_drop": [float(c) for c in cov_drops],
                "per_scene_error_rise": [float(r) for r in rises],
                "coverage_held_flat": bool(cov_drop <= 0.10),
                "error_rose_enough": bool(np.isfinite(err_rise) and err_rise >= 0.25),
                "survives": bool(cov_drop <= 0.10 and np.isfinite(err_rise) and err_rise >= 0.25),
            }

        verdicts[matcher] = {
            "variance_is_constant_by_construction": bool(constant_variance),
            "H1_variance_ratio_median": float(ratio),
            "H1_variance_under_20x": bool(h1_variance_ok),
            "H1_variance_test_is_vacuous": bool(constant_variance),
            "H1_hallucination_median": float(hall),
            "H1_hallucination_at_least_half_exp001": bool(h1_hallucination_ok),
            "H1_survives": bool(h1_variance_ok and h1_hallucination_ok),
            "H1b_per_scene_ratios": [float(r) for r in ratios],
            "H1b_n_scenes_at_or_above_1": len(above),
            "H1b_survives": bool(h1b),
            "H2": h2,
        }
    return verdicts


def run(config_path: Path) -> Path:
    cfg = load_config(config_path)
    ctx = RunContext(
        tag=cfg.get("experiment", {}).get("tag", "exp004"), seed=cfg["seed"], config=cfg
    )

    scenes = from_config(cfg)
    seen = set(cfg["analysis"]["seen_scenes"])
    variants = list(cfg["analysis"]["right_variants"])

    per_scene: dict = {}
    for scene in scenes:
        label = scene.directory.name.split("-")[0]
        per_scene[label] = run_scene(scene, cfg)
        print(f"[exp004] scored {label:<12} {per_scene[label]['shape']} ndisp={scene.ndisp}")

    held_out = [s for s in per_scene if s not in seen]
    matcher_names = sorted({m for s in per_scene.values() for m in s["by_matcher"]})
    summary = aggregate(per_scene, held_out, matcher_names, variants)
    verdicts = evaluate_hypotheses(summary, per_scene, held_out)

    payload = {
        "n_scenes": len(per_scene),
        "held_out_scenes": held_out,
        "seen_scenes": sorted(seen),
        "downsample": cfg["scene"]["downsample"],
        "by_matcher_heldout": summary,
        "hypotheses": verdicts,
        "per_scene": per_scene,
    }
    ctx.path("summary.json").write_text(json.dumps(payload, indent=2))

    print(f"\n=== held-out medians ({len(held_out)} scenes, im1) ===")
    print(
        f"{'matcher':<8}{'cover':>8}{'bad2':>8}{'err_px':>9}"
        f"{'err_mm':>9}{'halluc':>9}{'var_ratio':>11}"
    )
    for matcher, v in summary.items():
        if "im1" not in v:
            continue
        r = v["im1"]
        print(
            f"{matcher:<8}{r['coverage_median']:>8.3f}{r['bad2_median']:>8.3f}"
            f"{r['disparity_error_px_median']:>9.3f}{r['depth_error_m_median'] * 1000:>9.1f}"
            f"{r['hallucination_median']:>9.3f}{r['var_ratio_median']:>11.2f}"
        )

    print(f"\n=== seen scene, reported separately: {sorted(seen)} ===")
    for label in sorted(seen):
        if label not in per_scene:
            continue
        for matcher, cells in per_scene[label]["by_matcher"].items():
            c = cells["im1"]
            print(
                f"{label:<12}{matcher:<8}cover={c['coverage']:.3f} bad2={c['bad2']:.3f} "
                f"halluc={c['hallucination']:.3f} var_ratio={c['var_ratio']:.2f}"
            )

    print("\n=== hypotheses ===")
    print(json.dumps(verdicts, indent=2))
    print(f"\nrun-id: {ctx.run_id}\nresults: {ctx.dir}")
    return ctx.dir


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, required=True)
    run(ap.parse_args().config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
