"""exp001 — block matching vs SGBM under foveal confinement.

Hypothesis and acceptance criteria live in ``config.yaml`` and in the tracking
issue. This runner is deliberately thin: all reusable logic belongs in ``src``.

Usage
-----
    python -m experiments.exp001_matcher_baseline.run \
        --config experiments/exp001_matcher_baseline/config.yaml
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from activestereo.inference import BlockMatcher
from activestereo.policy.foveation import confine_to_fovea, eccentricity
from activestereo.scaling import scale_to_depth
from activestereo.scenes import (
    RandomDotStereogram,
    corrugated,
    disk,
    slanted_plane,
    staircase,
)
from activestereo.types import StereoRig
from activestereo.utils import RunContext, load_config


def build_scene(cfg) -> RandomDotStereogram:
    """The stimulus. An RDS carries depth in disparity alone, so a depth estimate
    here cannot have come from a monocular cue (ADR-0006).

    Replaced the fronto-parallel placeholder, which had constant depth and
    therefore could not discriminate the matchers at all.
    """
    sc = cfg["scene"]
    return RandomDotStereogram(
        SCENES[sc.get("depth_fn", "disk")],
        name=f"rds_{sc.get('depth_fn', 'disk')}",
        shape=tuple(sc["shape"]),
        dot_size=sc.get("dot_size", 2),
        density=sc.get("density", 0.5),
        binary=sc.get("binary", True),
        noise=sc.get("noise", 0.0),
        **{k: sc[k] for k in ("near", "far", "radius") if k in sc},
    )


SCENES = {
    "disk": disk,
    "staircase": staircase,
    "slanted_plane": slanted_plane,
    "corrugated": corrugated,
}


def run(config_path: Path) -> Path:
    cfg = load_config(config_path)
    rig = StereoRig(
        baseline=cfg["rig"]["baseline"],
        focal_px=cfg["rig"]["focal_px"],
        vergence=np.deg2rad(cfg["rig"]["vergence_deg"]),
    )
    ctx = RunContext(
        tag=cfg.get("experiment", {}).get("tag", "exp001"), seed=cfg["seed"], config=cfg
    )

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

    scene = build_scene(cfg)
    results: dict[str, dict[str, list[float]]] = {}

    for seed in cfg.get("seeds", [cfg["seed"]]):
        stim = scene.render(rig, np.random.default_rng(seed))
        eta = eccentricity(stim.shape)
        foveal = eta < 0.15 * np.hypot(*stim.shape)

        for name, matcher in matchers.items():
            est = matcher.match(stim.left, stim.right)
            depth = confine_to_fovea(
                scale_to_depth(est, rig),
                coefficient=cfg["policy"]["foveal_coefficient"],
            )
            err = np.abs(depth.value - stim.depth)

            # Scored separately: where a match exists a matcher should succeed,
            # and where it does not it should decline. Pooling the two rewards a
            # matcher that hallucinates confidently in half-occlusions.
            scorable = stim.matched & foveal & np.isfinite(err)
            occ = stim.occluded

            entry = results.setdefault(
                name, {"foveal_mae": [], "coverage": [], "hallucination": []}
            )
            entry["foveal_mae"].append(
                float(np.median(err[scorable])) if scorable.any() else float("nan")
            )
            entry["coverage"].append(
                float((stim.matched & np.isfinite(depth.value)).sum() / max(stim.matched.sum(), 1))
            )
            entry["hallucination"].append(
                float((occ & np.isfinite(depth.value)).sum() / max(occ.sum(), 1))
            )

    summary = {
        name: {
            "foveal_mae_median": float(np.nanmedian(v["foveal_mae"])),
            "foveal_mae_spread": float(np.nanstd(v["foveal_mae"])),
            "coverage_mean": float(np.mean(v["coverage"])),
            "hallucination_mean": float(np.mean(v["hallucination"])),
            "n_seeds": len(v["foveal_mae"]),
        }
        for name, v in results.items()
    }
    ctx.path("summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    print(f"\nrun-id: {ctx.run_id}\nresults: {ctx.dir}")
    return ctx.dir


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, required=True)
    run(ap.parse_args().config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
