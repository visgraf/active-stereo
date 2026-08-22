"""Per-scene visual composites for exp007: raw vs filled, all three matchers.

Reads the ``disp0AS*.pfm`` files the exp007 runner wrote into the MiddEval3
tree and, for every trainingQ scene, renders one composite: the left image and
ground truth beside each matcher's raw output and its background-filled dense
submission. Refusals render in an unmistakable red, and every disparity panel
in a scene shares one color scale taken from that scene's ground truth -- the
two choices that make the fill's effect *visible* rather than averaged away.

Requires an exp007 run to have populated the tree first:

    python -m experiments.exp007_middeval3_training.run \\
        --config experiments/exp007_middeval3_training/config.yaml
    python scripts/make_exp007_figures.py
    python scripts/build_deck.py slides/exp007_middeval3_training

Figure suptitles quote the dense bad% at t=0.5 from the run's summary.json so
each image is self-contained; pass --summary to pin a different run.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import cm

from activestereo.scenes.middlebury import read_pfm

#: The run whose numbers annotate the figures, unless --summary overrides.
PINNED_SUMMARY = Path("results/exp007-20260821T230639-65476a0/summary.json")

SENTINEL = (0.85, 0.15, 0.15)  # refusals: red, outside viridis entirely

METHODS = (("ASblk", "block"), ("ASsgbm", "sgbm"), ("ASnrg", "energy"))


def middeval3_root() -> Path:
    return Path(os.environ.get("ACTIVESTEREO_MIDDEVAL3_ROOT", "~/datasets/middeval3")).expanduser()


def colorize(disp: np.ndarray, vmin: float, vmax: float) -> np.ndarray:
    """Viridis over [vmin, vmax]; non-finite pixels get the sentinel colour."""
    d = np.asarray(disp, dtype=float)
    invalid = ~np.isfinite(d)
    norm = np.clip((d - vmin) / (vmax - vmin), 0.0, 1.0)
    rgb = cm.viridis(np.where(invalid, 0.0, norm))[..., :3]
    rgb[invalid] = SENTINEL
    return np.asarray(rgb)


def scene_bad(summary: dict, scene: str) -> dict[str, float]:
    """Dense bad% at t=0.5 per method, from the pinned run's per-scene table."""
    return {
        r["algorithm"]: r["bad_pct"] for r in summary["per_scene"]["0.5"] if r["dataset"] == scene
    }


def render_scene(scene_dir: Path, out: Path, summary: dict) -> None:
    name = scene_dir.name
    gt = read_pfm(scene_dir / "disp0GT.pfm")
    gt = np.where(np.isinf(gt), np.nan, gt)
    vmin, vmax = (float(v) for v in np.nanpercentile(gt, [1, 99]))
    left = plt.imread(scene_dir / "im0.png")

    panels: list[tuple[str, np.ndarray]] = [
        ("left image (im0)", left),
        ("ground truth", colorize(gt, vmin, vmax)),
    ]
    for method, label in METHODS:
        raw = read_pfm(scene_dir / f"disp0{method}_s.pfm")
        filled = read_pfm(scene_dir / f"disp0{method}.pfm")
        refused = 100.0 * float(np.mean(np.isinf(raw)))
        panels.append((f"{label} raw (refused {refused:.0f}%)", colorize(raw, vmin, vmax)))
        panels.append((f"{label} filled", colorize(filled, vmin, vmax)))

    bad = scene_bad(summary, name)
    title = (
        f"{name} — dense bad% (t=0.5): "
        + " · ".join(f"{label} {bad[m]:.1f}" for m, label in METHODS)
        + "   (red = refusal)"
    )

    fig, axes = plt.subplots(2, 4, figsize=(14, 5.6))
    for ax, (panel_title, img) in zip(axes.ravel(), panels, strict=True):
        ax.imshow(img, cmap="gray" if img.ndim == 2 else None)
        ax.set_title(panel_title, fontsize=9)
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle(title, fontsize=11)
    fig.tight_layout()
    fig.savefig(out / f"{name}.png", dpi=95)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--summary", type=Path, default=PINNED_SUMMARY)
    ap.add_argument("--out", type=Path, default=Path("slides/exp007_middeval3_training"))
    args = ap.parse_args()

    summary = json.loads(args.summary.read_text())
    split = middeval3_root() / "MiddEval3" / "trainingQ"
    scene_dirs = sorted(d for d in split.iterdir() if (d / "calib.txt").exists())
    if not scene_dirs:
        raise SystemExit(f"no scenes under {split}; run scripts/fetch_middeval3.py first")

    missing = [d.name for d in scene_dirs if not (d / "disp0ASblk.pfm").exists()]
    if missing:
        raise SystemExit(
            f"no exp007 results in the tree for: {missing}\n"
            "Run the exp007 runner first; these figures visualise its output "
            "rather than recomputing anything."
        )

    figures = args.out / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    for d in scene_dirs:
        render_scene(d, figures, summary)
        print(d.name)
    print(f"\n{len(scene_dirs)} composites under {figures}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
