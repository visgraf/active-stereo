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

from activestereo.geometry import depth_to_disparity
from activestereo.inference import BlockMatcher
from activestereo.policy.foveation import confine_to_fovea, eccentricity
from activestereo.scaling import scale_to_depth
from activestereo.types import StereoRig
from activestereo.utils import RunContext, load_config


def synthesize(
    shape: tuple[int, int], rig: StereoRig, rng: np.random.Generator, depth: float = 0.7
):
    """A fronto-parallel textured plane at a known depth. Placeholder scene.

    TODO(#2): replace with the Blender-rendered slanted textured scene once the
    render scripts are migrated into ``scripts/``.
    """
    H, W = shape
    # Nearer than fixation, so true disparity is non-zero and inside the search
    # range. At 1.0 m (the fixation distance) disparity is 0 by construction and
    # every pixel is correctly rejected -- a true result about a useless scene.
    Z_true = np.full((H, W), float(depth))
    d_true = depth_to_disparity(Z_true, rig)
    d = round(float(np.nanmedian(d_true)))
    base = rng.random((H, W + max(d, 1)))
    left = base[:, :W]
    right = base[:, d : d + W]
    return left, right, Z_true


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

    shape = tuple(cfg["scene"]["shape"])
    results: dict[str, dict[str, float]] = {}

    for seed in cfg.get("seeds", [cfg["seed"]]):
        rng = np.random.default_rng(seed)
        left, right, Z_true = synthesize(shape, rig, rng, cfg["scene"]["placeholder_depth"])
        eta = eccentricity(shape)
        foveal = eta < 0.15 * np.hypot(*shape)

        for name, matcher in matchers.items():
            est = matcher.match(left, right)
            depth = confine_to_fovea(
                scale_to_depth(est, rig),
                coefficient=cfg["policy"]["foveal_coefficient"],
            )
            err = np.abs(depth.value - Z_true)
            ok = np.isfinite(err) & foveal
            entry = results.setdefault(name, {"foveal_mae": [], "valid_fraction": []})
            entry["foveal_mae"].append(float(np.median(err[ok])) if ok.any() else float("nan"))
            entry["valid_fraction"].append(float(np.isfinite(depth.value).mean()))

    summary = {
        name: {
            "foveal_mae_median": float(np.nanmedian(v["foveal_mae"])),
            "foveal_mae_spread": float(np.nanstd(v["foveal_mae"])),
            "valid_fraction_mean": float(np.mean(v["valid_fraction"])),
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
