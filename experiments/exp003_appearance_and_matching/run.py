"""exp003 -- does specularity break stereo differently from texture loss?

Hypotheses, falsifiers and threats to validity live in ``config.yaml`` and in
issue #4. This runner is deliberately thin: all reusable logic belongs in
``src``.

Render the stimulus set first (12 conditions, a few minutes on Cycles)::

    python scripts/render_chart_sweep.py --out results/stimuli/chart

then::

    python -m experiments.exp003_appearance_and_matching.run \
        --config experiments/exp003_appearance_and_matching/config.yaml
"""

from __future__ import annotations

import argparse
import itertools
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from activestereo.inference import BlockMatcher
from activestereo.scaling import scale_to_depth
from activestereo.scenes.blender import BlenderRenderScene
from activestereo.utils import RunContext, load_config

TEXTURE_ORDER = ("dense", "mid", "coarse", "none")

# H2b says glossy coverage must be "comparable or higher" than matte. This is
# what "comparable" means, fixed before the first run and not revisited after.
COVERAGE_TOLERANCE = 0.05


def build_matchers(cfg) -> dict:
    matchers = {
        "block": BlockMatcher(
            max_disparity=cfg["matcher"]["max_disparity"],
            window=cfg["matcher"]["window"],
        )
    }
    try:
        from activestereo.inference.sgbm import SGBMMatcher

        matchers["sgbm"] = SGBMMatcher(max_disparity=cfg["matcher"]["max_disparity"])
    except ImportError:
        print("OpenCV unavailable; running block matcher only.")
    return matchers


def score_condition(scene: BlenderRenderScene, matchers: dict, texture_window: int) -> dict:
    """Score every matcher on one render, per material patch.

    Scored on ``matched`` pixels only -- where a correspondent genuinely exists.
    Half-occlusions are a different failure (exp001 measures those) and pooling
    them in would let occlusion structure masquerade as an appearance effect.
    Here the geometry is identical across every patch, so it cancels anyway; the
    restriction is belt and braces.

    ``confine_to_fovea`` is deliberately *not* applied. It inflates variance with
    eccentricity, and eccentricity is the confound the permutation sweep exists
    to remove -- applying it would reintroduce, as a modelling term, exactly what
    the design spends 12 renders averaging out.
    """
    stim = scene.stimulus()
    appearance = scene.appearance(window=texture_window)
    conditions = scene.conditions()
    mismatch = appearance.specular_mismatch(stim.disparity)

    out: dict[str, dict] = {}
    for name, matcher in matchers.items():
        depth = scale_to_depth(matcher.match(stim.left, stim.right), scene.rig)
        answered = np.isfinite(depth.value)
        err = np.abs(depth.value - stim.depth)

        per_patch = {}
        for index, spec in conditions.items():
            on_patch = (appearance.material_index == index) & stim.matched
            if not on_patch.any():
                continue
            scorable = on_patch & answered & np.isfinite(err)
            per_patch[spec["label"]] = {
                "texture": spec["texture"],
                "roughness": spec["roughness"],
                "n_matched": int(on_patch.sum()),
                "coverage": float(answered[on_patch].mean()),
                "depth_error_m": (
                    float(np.median(err[scorable])) if scorable.any() else float("nan")
                ),
                "texture_contrast": float(np.nanmedian(appearance.texture_contrast[on_patch])),
                "specular_mismatch": float(np.nanmedian(mismatch[on_patch])),
            }
        out[name] = per_patch
    return out


def _median(values: list[float]) -> float:
    finite = [v for v in values if np.isfinite(v)]
    return float(np.median(finite)) if finite else float("nan")


def aggregate(per_condition: dict, matchers: list[str]) -> dict:
    """Pool over lighting and permutation; permutation spread is the noise floor."""
    summary: dict = {}
    for matcher in matchers:
        by_label: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for scores in per_condition.values():
            for label, stats in scores.get(matcher, {}).items():
                for key in ("coverage", "depth_error_m", "texture_contrast", "specular_mismatch"):
                    by_label[label][key].append(stats[key])
        summary[matcher] = {
            label: {
                "texture": label.split("_")[0],
                # "finish", not "roughness": the per-render dicts already use
                # "roughness" for the numeric Principled value, and two meanings
                # under one key is how a plot ends up mislabelled.
                "finish": label.split("_")[1],
                **{f"{k}_median": _median(v) for k, v in stats.items()},
                "coverage_spread": float(np.std(stats["coverage"])),
                "depth_error_spread": float(np.nanstd(stats["depth_error_m"])),
                "n_renders": len(stats["coverage"]),
            }
            for label, stats in by_label.items()
        }
    return summary


def evaluate_hypotheses(summary: dict) -> dict:
    """Apply the falsifiers from issue #4 literally, matcher by matcher."""
    verdicts: dict = {}
    for matcher, patches in summary.items():
        matte = {p["texture"]: p for p in patches.values() if p["finish"] == "matte"}
        glossy = {p["texture"]: p for p in patches.values() if p["finish"] == "glossy"}
        levels = [t for t in TEXTURE_ORDER if t in matte and t in glossy]

        # H1a is judged on the matte row: it is the texture axis uncontaminated
        # by specular energy. The glossy row is reported alongside as a
        # diagnostic, not as part of the verdict.
        coverage = [matte[t]["coverage_median"] for t in levels]
        h1a = all(a >= b - 1e-9 for a, b in itertools.pairwise(coverage))
        coverage_glossy = [glossy[t]["coverage_median"] for t in levels]
        h1a_glossy = all(a >= b - 1e-9 for a, b in itertools.pairwise(coverage_glossy))

        err_dense = matte[levels[0]]["depth_error_m_median"]
        err_none = matte[levels[-1]]["depth_error_m_median"]
        ratio = float(err_none / err_dense) if err_dense > 0 else float("inf")
        h1b = ratio < 2.0

        # H2 compares glossy against matte at the SAME texture level, which is
        # the point of matching albedo contrast across the roughness axis.
        diffs, cov_drop = {}, {}
        for t in levels:
            diffs[t] = glossy[t]["depth_error_m_median"] - matte[t]["depth_error_m_median"]
            cov_drop[t] = glossy[t]["coverage_median"] - matte[t]["coverage_median"]
        noise = max(
            max(glossy[t]["depth_error_spread"] for t in levels),
            max(matte[t]["depth_error_spread"] for t in levels),
        )
        h2a = any(d > noise for d in diffs.values())
        # "comparable or higher" needs a number. 5 percentage points, stated
        # here rather than buried, and fixed before the first run.
        h2b = all(c >= -COVERAGE_TOLERANCE for c in cov_drop.values())

        verdicts[matcher] = {
            "H1a_coverage_monotone_in_texture": bool(h1a),
            "H1a_coverage_monotone_glossy_diagnostic": bool(h1a_glossy),
            "H1b_error_stable_when_texture_vanishes": bool(h1b),
            "H1b_error_ratio_none_over_dense": ratio,
            "H2a_gloss_raises_error_beyond_noise": bool(h2a),
            "H2a_gloss_minus_matte_error_m": diffs,
            "H2a_permutation_noise_floor_m": float(noise),
            "H2b_gloss_does_not_reduce_coverage": bool(h2b),
            "H2b_gloss_minus_matte_coverage": cov_drop,
            "H1_survives": bool(h1a and h1b),
            "H2_survives": bool(h2a and h2b),
        }
    return verdicts


def run(config_path: Path) -> Path:
    cfg = load_config(config_path)
    ctx = RunContext(
        tag=cfg.get("experiment", {}).get("tag", "exp003"), seed=cfg["seed"], config=cfg
    )

    root = Path(cfg["scene"]["stimulus_root"])
    conditions = [
        f"{light}_p{perm}"
        for light in cfg["scene"]["lighting"]
        for perm in cfg["scene"]["permutations"]
    ]
    missing = [c for c in conditions if not (root / c / "left.exr").exists()]
    if missing:
        raise SystemExit(
            f"missing {len(missing)} of {len(conditions)} stimulus renders under {root}: "
            f"{missing[:4]}{' ...' if len(missing) > 4 else ''}\n"
            "Render them first:  python scripts/render_chart_sweep.py --out "
            f"{root}\n"
            "A partial set unbalances the design -- a missing permutation "
            "reintroduces the eccentricity confound the sweep removes."
        )

    matchers = build_matchers(cfg)
    texture_window = cfg.get("analysis", {}).get("texture_window", cfg["matcher"]["window"])

    per_condition = {}
    for condition in conditions:
        scene = BlenderRenderScene(root / condition)
        per_condition[condition] = score_condition(scene, matchers, texture_window)
        print(f"[exp003] scored {condition}")

    summary = aggregate(per_condition, list(matchers))
    verdicts = evaluate_hypotheses(summary)
    payload = {
        "n_conditions": len(conditions),
        "conditions": conditions,
        "stimulus_root": str(root),
        "by_matcher": summary,
        "hypotheses": verdicts,
        "per_condition": per_condition,
    }

    ctx.path("summary.json").write_text(json.dumps(payload, indent=2))

    for matcher, patches in summary.items():
        print(f"\n=== {matcher} ===")
        print(
            f"{'material':<15}{'tex_sd':>9}{'spec':>9}{'coverage':>11}{'err_m':>11}{'err_sd':>10}"
        )
        for texture in TEXTURE_ORDER:
            for label, p in sorted(patches.items()):
                if p["texture"] != texture:
                    continue
                print(
                    f"{label:<15}{p['texture_contrast_median']:>9.4f}"
                    f"{p['specular_mismatch_median']:>9.4f}{p['coverage_median']:>11.4f}"
                    f"{p['depth_error_m_median']:>11.5f}{p['depth_error_spread']:>10.5f}"
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
