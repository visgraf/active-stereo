"""exp007 -- Middlebury Stereo Evaluation v3, training-set placement.

Runs the three validated matchers on the 15 trainingQ pairs, writes results in
the SDK's own format (disp0<name>.pfm + time<name>.txt inside the MiddEval3
tree), and scores everything with the benchmark's evaluator. Two conventions
per matcher, mirroring the benchmark's own SGM/SGM_s pairing:

- ``<name>_s`` -- raw output, refusals as INFINITY (sparse convention);
- ``<name>``   -- the same field after a declared scanline background fill
  (dense convention, comparable to the dense leaderboard).

The fill lives here, not in ``src/``: it is benchmark adaptation, not part of
any estimator, and promoting it to the library would quietly institutionalise
exactly the confident hole-filling exp004 showed to be the dangerous move.

    python -m experiments.exp007_middeval3_training.run \
        --config experiments/exp007_middeval3_training/config.yaml
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

import numpy as np

from activestereo.encoding import MultiScaleEnergyEncoder
from activestereo.inference import BlockMatcher, EnergyDecoder
from activestereo.scenes.middeval3 import MiddEval3Scene, training_scenes
from activestereo.scenes.middlebury import write_pfm
from activestereo.types import FloatArray
from activestereo.utils import RunContext, load_config


def middeval3_root(cfg: dict) -> Path:
    return Path(os.environ.get("ACTIVESTEREO_MIDDEVAL3_ROOT", cfg["root"])).expanduser()


def build_matcher(kind: str, spec: dict, ndisp: int):
    if kind == "block":
        return BlockMatcher(max_disparity=ndisp, window=spec["window"])
    if kind == "sgbm":
        from activestereo.inference.sgbm import SGBMMatcher

        # SGBM requires a multiple of 16. Round UP, as exp004 did: rounding
        # down would silently truncate the search range.
        return SGBMMatcher(max_disparity=-(-ndisp // 16) * 16, block_size=spec["window"])
    if kind == "energy":
        encoder = MultiScaleEnergyEncoder(
            np.arange(0, ndisp + 1, dtype=float),
            scales=[tuple(s) for s in spec["scales"]],
            combine=spec["combine"],
            floor=spec["floor"],
        )
        return EnergyDecoder(
            encoder=encoder,
            flatness=spec["flatness"],
            centroid_halfwidth=spec["centroid_halfwidth"],
        )
    raise ValueError(f"unknown matcher kind: {kind}")


def _row_fill(d: FloatArray) -> FloatArray:
    """One row-wise pass: invalid pixels take the smaller nearest valid
    neighbour to their left/right. Pixels in fully-invalid rows stay invalid."""
    d = d.copy()
    H, W = d.shape
    cols = np.arange(W)
    invalid = ~np.isfinite(d)

    left_idx = np.maximum.accumulate(np.where(~invalid, cols, -1), axis=1)
    right_idx = np.minimum.accumulate(np.where(~invalid, cols, W)[:, ::-1], axis=1)[:, ::-1]

    rows = np.arange(H)[:, None]
    left_val = np.where(left_idx >= 0, d[rows, np.clip(left_idx, 0, W - 1)], np.inf)
    right_val = np.where(right_idx < W, d[rows, np.clip(right_idx, 0, W - 1)], np.inf)
    fill = np.minimum(left_val, right_val)
    return np.asarray(np.where(invalid & np.isfinite(fill), fill, d))


def fill_background(disparity: FloatArray) -> FloatArray:
    """Fill invalid pixels with the smaller neighbouring disparity, row-wise.

    The standard benchmark postprocess (LR-check pipelines from SGM onward):
    a pixel with no match is most often half-occluded, and a half-occluded
    pixel belongs to the *background*, i.e. the smaller disparity of its two
    nearest valid horizontal neighbours. Rows with no valid pixel at all get
    a column-wise pass of the same rule, and anything still invalid (an
    all-invalid map has nothing to propagate) takes the field's median.

    This is exactly the confident-guessing move the project's experiments
    argue against -- applied here knowingly, as a declared adaptation to a
    benchmark whose dense convention scores a refusal as an error.
    """
    d = _row_fill(np.asarray(disparity, dtype=float))
    if not np.isfinite(d).all():
        d = _row_fill(d.T).T
    remaining = ~np.isfinite(d)
    if remaining.any() and not remaining.all():
        d = d.copy()
        d[remaining] = np.median(d[~remaining])
    return d


def run_matchers(cfg: dict, scenes: list[MiddEval3Scene]) -> dict:
    """Write disp0/time files for every scene x method into the SDK tree."""
    log: dict[str, dict] = {}
    for scene in scenes:
        entry: dict[str, object] = {
            "ndisp": scene.ndisp,
            "dyavg": scene.dyavg,
            "dymax": scene.dymax,
        }
        left, right = scene.left, scene.right
        for kind, spec in cfg["methods"].items():
            name = spec["name"]
            matcher = build_matcher(kind, spec, scene.ndisp)
            t0 = time.perf_counter()
            est = matcher.match(left, right)
            elapsed = time.perf_counter() - t0

            raw = est.value
            write_pfm(scene.directory / f"disp0{name}_s.pfm", raw)
            write_pfm(scene.directory / f"disp0{name}.pfm", fill_background(raw))
            for variant in (name, f"{name}_s"):
                (scene.directory / f"time{variant}.txt").write_text(f"{elapsed:.2f}\n")

            entry[name] = {
                "seconds": round(elapsed, 2),
                "refusal_fraction": float(np.mean(~np.isfinite(raw))),
            }
            print(
                f"  {scene.directory.name:12s} {name:7s} {elapsed:7.1f}s  "
                f"refused {100 * np.mean(~np.isfinite(raw)):5.1f}%"
            )
        log[scene.directory.name] = entry
    return log


def run_eval(cfg: dict, root: Path) -> dict:
    """Score every method and anchor with the SDK's evaluator, all thresholds.

    Output rows come from ``runeval -b`` (brief mode): dataset, algorithm,
    mask coverage %, bad%, invalid%, totbad%, avgErr. bad% is the sparse
    convention (errors among valid pixels), totbad% the dense one (refusals
    charged in full).
    """
    ours = [spec["name"] for spec in cfg["methods"].values()]
    methods = ours + [f"{n}_s" for n in ours] + list(cfg["anchors"])
    res = cfg["resolution"]
    tables: dict[str, list[dict]] = {}
    for t in cfg["thresholds"]:
        out = subprocess.run(
            ["./runeval", "-b", res, "training", str(t), *methods],
            cwd=root / "MiddEval3",
            capture_output=True,
            text=True,
            check=True,
        )
        rows = []
        for line in out.stdout.splitlines():
            parts = line.split()
            if len(parts) == 7 and parts[0] != "dataset":
                rows.append(
                    {
                        "dataset": parts[0],
                        "algorithm": parts[1],
                        "mask_pct": float(parts[2]),
                        "bad_pct": float(parts[3]),
                        "invalid_pct": float(parts[4]),
                        "totbad_pct": float(parts[5]),
                        "avgerr": float(parts[6]),
                    }
                )
        tables[str(t)] = rows
    return tables


def aggregate(rows: list[dict]) -> dict[str, dict[str, float]]:
    """Unweighted means over the 15 pairs, per algorithm.

    The online table applies its own per-dataset weights, so these aggregates
    are for comparisons *within* this run (all algorithms share the ruler),
    not for quoting against the website's weighted averages.
    """
    by_alg: dict[str, list[dict]] = {}
    for r in rows:
        by_alg.setdefault(r["algorithm"], []).append(r)
    return {
        alg: {
            "bad_pct": float(np.mean([r["bad_pct"] for r in rs])),
            "invalid_pct": float(np.mean([r["invalid_pct"] for r in rs])),
            "totbad_pct": float(np.mean([r["totbad_pct"] for r in rs])),
            "avgerr": float(np.mean([r["avgerr"] for r in rs])),
            "n": len(rs),
        }
        for alg, rs in sorted(by_alg.items())
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument(
        "--eval-only",
        action="store_true",
        help="skip matching; re-score whatever disp0 files are already in the tree",
    )
    args = ap.parse_args()
    cfg = load_config(args.config)
    root = middeval3_root(cfg)

    scenes = training_scenes(root, cfg["resolution"])
    print(f"{len(scenes)} training scenes under {root}")

    ctx = RunContext(tag="exp007", seed=0, config=dict(cfg))

    log = {} if args.eval_only else run_matchers(cfg, scenes)
    tables = run_eval(cfg, root)

    summary = {
        "resolution": cfg["resolution"],
        "threshold_note": (
            "thresholds are in quarter-resolution pixels; t=0.5 approximates "
            "the official full-resolution bad2.0 (SDK README), evaluated "
            "against Q-size ground truth"
        ),
        "scenes": log,
        "per_scene": tables,
        "aggregate": {t: aggregate(rows) for t, rows in tables.items()},
    }
    ctx.path("summary.json").write_text(json.dumps(summary, indent=2))

    print("\naggregate (unweighted mean over 15 pairs), t=0.5 ~ official bad2.0:")
    agg = summary["aggregate"]["0.5"]
    print(f"{'algorithm':10s} {'bad%':>7s} {'invalid%':>9s} {'totbad%':>8s} {'avgerr':>7s}")
    for alg, a in agg.items():
        print(
            f"{alg:10s} {a['bad_pct']:7.2f} {a['invalid_pct']:9.2f} "
            f"{a['totbad_pct']:8.2f} {a['avgerr']:7.2f}"
        )
    print(f"\nrun-id: {ctx.run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
