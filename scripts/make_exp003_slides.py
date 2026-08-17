"""Generate the figures, tables and graphs for the exp003 slide deck.

Reads the rendered stimulus set, re-runs the matchers, and writes PNGs plus a
machine-readable ``data.json`` into ``slides/exp003_appearance_and_matching/``.

Usage
-----
    python scripts/make_exp003_slides.py

Presentation assets only. Nothing here is a result: the results live in
``experiments/exp003_appearance_and_matching/findings.md``, pinned to a run-id.
This script re-derives the same numbers for display, and prints them so a
mismatch with findings.md is visible rather than silent.

The "safe matching" mask
------------------------
The interesting question in exp003 is not where the matcher is *right* but where
it *believes itself*. A pixel is drawn as safe when it is answered **and** its
reported variance is within ``SAFE_FACTOR`` of the well-textured baseline. That
is a display threshold for the slides, not a value used by the pipeline -- the
absolute scale of the curvature-derived variance is a proxy, so only ratios
against a baseline measured in the same scene are meaningful.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from activestereo.inference import BlockMatcher
from activestereo.scaling import scale_to_depth
from activestereo.scenes.blender import BlenderRenderScene

LIGHTING = ("ambient", "key", "grazing")
PERMUTATIONS = (0, 1, 2, 3)
TEXTURES = ("dense", "mid", "coarse", "none")
SAFE_FACTOR = 10.0

INK = "#101a1f"
SLATE = "#55676e"
FAINT = "#8fa1a7"
CYAN = "#0d6e7d"
VERM = "#b03f2a"
RULE = "#d3dedf"
TIMES = "\u00d7"  # multiplication sign, via escape: ruff RUF001 flags the literal
ERRMAP = "Reds"  # white at zero: on a slide, pale must mean "fine"
TEXCOLORS = {"dense": "#0d6e7d", "mid": "#3f8f96", "coarse": "#8aa9a4", "none": "#b03f2a"}


def _style() -> None:
    import matplotlib as mpl

    mpl.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": RULE,
            "axes.labelcolor": INK,
            "axes.titlecolor": INK,
            "axes.titlesize": 11,
            "axes.titleweight": "600",
            "axes.labelsize": 9.5,
            "xtick.color": SLATE,
            "ytick.color": SLATE,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "text.color": INK,
            "font.family": "sans-serif",
            "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
            "axes.spines.top": False,
            "axes.spines.right": False,
            "legend.frameon": False,
            "legend.fontsize": 9,
            "savefig.bbox": "tight",
            "savefig.dpi": 160,
        }
    )


def analyse(root: Path) -> tuple[dict, dict]:
    """Score every render. Returns (per-patch records, cached arrays for figures)."""
    matcher = BlockMatcher(max_disparity=48, window=7)
    records: list[dict] = []
    per_render: list[dict] = []
    panels: dict[str, dict] = {}

    for light in LIGHTING:
        for perm in PERMUTATIONS:
            name = f"{light}_p{perm}"
            scene = BlenderRenderScene(root / name)
            stim = scene.stimulus()
            appearance = scene.appearance()
            est = matcher.match(stim.left, stim.right)
            depth = scale_to_depth(est, scene.rig)
            err = np.abs(depth.value - stim.depth)
            answered = np.isfinite(depth.value)
            mismatch = appearance.specular_mismatch(stim.disparity)
            labels = {m["material_index"]: m["label"] for m in scene.chart["materials"]}

            textured = np.isin(
                appearance.material_index,
                [k for k, v in labels.items() if not v.startswith("none")],
            )
            baseline = float(np.nanmedian(est.variance[textured & stim.matched & answered]))
            safe = answered & (est.variance <= SAFE_FACTOR * baseline)

            for index, label in labels.items():
                on = (appearance.material_index == index) & stim.matched
                if not on.any():
                    continue
                ok = on & answered & np.isfinite(err)
                records.append(
                    {
                        "lighting": light,
                        "permutation": perm,
                        "label": label,
                        "texture": label.split("_")[0],
                        "finish": label.split("_")[1],
                        "coverage": float(answered[on].mean()),
                        "safe_fraction": float(safe[on].mean()),
                        "error_m": float(np.median(err[ok])) if ok.any() else float("nan"),
                        "variance": float(np.nanmedian(est.variance[on & answered])),
                        "texture_contrast": float(
                            np.nanmedian(appearance.texture_contrast[on])
                        ),
                        "specular_mismatch": float(np.nanmedian(mismatch[on])),
                    }
                )

            # Category variances aggregated exactly as findings.md does: pool
            # pixels within a render, then take the median across renders. A
            # median-of-per-patch-medians is also defensible but gives 730x
            # where the record says 637x, and a slide that disagrees with the
            # record of record is a liability regardless of which is nicer.
            textureless = np.isin(
                appearance.material_index,
                [k for k, v in labels.items() if v.startswith("none")],
            )
            per_render.append(
                {
                    "lighting": light,
                    "permutation": perm,
                    "textured": float(
                        np.nanmedian(est.variance[textured & stim.matched & answered])
                    ),
                    "textureless": float(
                        np.nanmedian(est.variance[textureless & stim.matched & answered])
                    ),
                    "occluded": float(np.nanmedian(est.variance[stim.occluded & answered])),
                }
            )

            occluded = stim.occluded & answered
            records.append(
                {
                    "lighting": light,
                    "permutation": perm,
                    "label": "__occluded__",
                    "texture": "occluded",
                    "finish": "occluded",
                    "coverage": float(answered[stim.occluded].mean()),
                    "safe_fraction": float(safe[stim.occluded].mean()),
                    "error_m": float("nan"),
                    "variance": float(np.nanmedian(est.variance[occluded])),
                    "texture_contrast": float("nan"),
                    "specular_mismatch": float("nan"),
                }
            )

            if perm == 0:
                panels[light] = {
                    "beauty": stim.left,
                    "predicted": depth.value,
                    "truth": stim.depth,
                    "error": err,
                    "safe": safe,
                    "answered": answered,
                    "index": appearance.material_index,
                    "matched": stim.matched,
                    "occluded": stim.occluded,
                    "mismatch": mismatch,
                    "labels": labels,
                }
            print(f"[slides] scored {name}")
    return {"records": records, "per_render": per_render, "safe_factor": SAFE_FACTOR}, panels


def category_variance(per_render, key: str) -> float:
    """Median across renders of the within-render pooled variance.

    Must match findings.md's aggregation exactly. Pooling the other way round --
    per-patch medians, then a median of those -- is equally defensible and gives
    730x where the record says 637x. A slide that quietly disagrees with the
    record of record is a liability whichever number is prettier.
    """
    return float(np.nanmedian([r[key] for r in per_render]))


def med(records, **filters):
    sel = [r for r in records if all(r[k] == v for k, v in filters.items())]
    if not sel:
        return {}
    keys = ("coverage", "safe_fraction", "error_m", "variance", "texture_contrast",
            "specular_mismatch")
    return {k: float(np.nanmedian([r[k] for r in sel])) for k in keys}


# ---------------------------------------------------------------- panels


SAFE_COLORS = ["#e9eff0", "#f0c9bf", CYAN]
SAFE_NAMES = ["no answer", "answered, distrusted", "answered, trusted"]


def _safe_legend(ax):
    """Label the three states, so the panel reads without the caption."""
    from matplotlib.patches import Patch

    ax.legend(
        handles=[
            Patch(facecolor=c, edgecolor=RULE, label=n)
            for c, n in zip(SAFE_COLORS, SAFE_NAMES, strict=True)
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.03),
        ncol=3,
        fontsize=8,
        handlelength=1.1,
        handleheight=1.1,
        columnspacing=1.0,
    )


def _triptych(ax_row, panel, title_prefix, vmax_err=0.12):
    """Predicted depth | depth error | pixels the matcher trusts."""
    import matplotlib.pyplot as plt

    pred = np.where(panel["matched"], panel["predicted"], np.nan)
    im0 = ax_row[0].imshow(pred, cmap="viridis", vmin=1.0, vmax=1.7)
    ax_row[0].set_title(f"{title_prefix}predicted depth")
    plt.colorbar(im0, ax=ax_row[0], fraction=0.035, pad=0.02, label="m")

    err = np.where(panel["matched"], panel["error"], np.nan)
    im1 = ax_row[1].imshow(err, cmap=ERRMAP, vmin=0.0, vmax=vmax_err)
    ax_row[1].set_title(f"{title_prefix}depth error")
    plt.colorbar(im1, ax=ax_row[1], fraction=0.035, pad=0.02, label="m")

    # 0 = no answer, 1 = answered but distrusted, 2 = safe
    state = np.zeros_like(panel["safe"], dtype=float)
    state[panel["answered"]] = 1.0
    state[panel["safe"]] = 2.0
    from matplotlib.colors import ListedColormap

    ax_row[2].imshow(state, cmap=ListedColormap(SAFE_COLORS), vmin=0, vmax=2)
    ax_row[2].set_title(f"{title_prefix}pixels matched safely")
    _safe_legend(ax_row[2])

    for ax in ax_row:
        ax.set_xticks([])
        ax.set_yticks([])


def _patch_labels(ax, panel, textures_only=True):
    """Annotate each patch with its condition."""
    for index, label in panel["labels"].items():
        if index > 8:
            continue
        sel = panel["index"] == index
        if not sel.any():
            continue
        rows, cols = np.where(sel)
        text = label.split("_")[0] if textures_only else label.replace("_", "\n")
        ax.text(
            cols.mean(),
            rows.mean(),
            text,
            ha="center",
            va="center",
            fontsize=7.5,
            color="white",
            weight="600",
            path_effects=None,
            bbox={"boxstyle": "round,pad=0.18", "fc": INK, "ec": "none", "alpha": 0.72},
        )


def fig_texture(panels, records, out: Path):
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(13.5, 3.6))
    _triptych(axes, panels["key"], "")
    _patch_labels(axes[0], panels["key"])
    fig.suptitle(
        "Texture test — key lighting. Left column of patches is dense texture, "
        "right column is perfectly uniform.",
        fontsize=10.5, color=SLATE, y=1.04,
    )
    fig.savefig(out / "02_texture_panels.png")
    plt.close(fig)

    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 3.6))
    xs = np.arange(4)
    cov = [med(records, texture=t, finish="matte")["coverage"] for t in TEXTURES]
    err = [1000 * med(records, texture=t, finish="matte")["error_m"] for t in TEXTURES]
    colors = [TEXCOLORS[t] for t in TEXTURES]

    a.bar(xs, cov, color=colors, width=0.62)
    a.set_xticks(xs, [t for t in TEXTURES])
    a.set_ylim(0, 1.05)
    a.set_ylabel("fraction of pixels answered")
    a.set_title("Coverage falls only at zero texture")
    for x, v in zip(xs, cov, strict=True):
        a.text(x, v + 0.02, f"{v:.1%}", ha="center", fontsize=9, color=INK, weight="600")

    b.bar(xs, err, color=colors, width=0.62)
    b.set_xticks(xs, [t for t in TEXTURES])
    b.set_yscale("log")
    b.set_ylabel("median depth error (mm, log)")
    b.set_title(f"...but error explodes 100{TIMES}")
    for x, v in zip(xs, err, strict=True):
        b.text(x, v * 1.25, f"{v:.2f}", ha="center", fontsize=9, color=INK, weight="600")
    fig.savefig(out / "02_texture_graph.png")
    plt.close(fig)


def fig_material(panels, records, out: Path):
    import matplotlib.pyplot as plt

    panel = panels["grazing"]
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 3.6))
    im = axes[0].imshow(panel["mismatch"], cmap="magma", vmin=0, vmax=1)
    axes[0].set_title("interocular specular mismatch")
    plt.colorbar(im, ax=axes[0], fraction=0.035, pad=0.02)
    _patch_labels(axes[0], panel, textures_only=False)

    err = np.where(panel["matched"], panel["error"], np.nan)
    im1 = axes[1].imshow(err, cmap=ERRMAP, vmin=0, vmax=0.02)
    axes[1].set_title("depth error")
    plt.colorbar(im1, ax=axes[1], fraction=0.035, pad=0.02, label="m")

    from matplotlib.colors import ListedColormap

    state = np.zeros_like(panel["safe"], dtype=float)
    state[panel["answered"]] = 1.0
    state[panel["safe"]] = 2.0
    axes[2].imshow(state, cmap=ListedColormap(SAFE_COLORS), vmin=0, vmax=2)
    axes[2].set_title("pixels matched safely")
    _safe_legend(axes[2])
    for ax in axes:
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle(
        "Material test — grazing light, the strongest highlights. "
        "Top row matte, bottom row glossy.",
        fontsize=10.5, color=SLATE, y=1.04,
    )
    fig.savefig(out / "03_material_panels.png")
    plt.close(fig)

    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 3.6))
    xs = np.arange(4)
    w = 0.36
    matte = [1000 * med(records, texture=t, finish="matte")["error_m"] for t in TEXTURES]
    glossy = [1000 * med(records, texture=t, finish="glossy")["error_m"] for t in TEXTURES]
    a.bar(xs - w / 2, matte, w, label="matte", color=CYAN)
    a.bar(xs + w / 2, glossy, w, label="glossy", color=VERM)
    a.set_xticks(xs, list(TEXTURES))
    a.set_yscale("log")
    a.set_ylabel("median depth error (mm, log)")
    a.set_title("At matched texture, gloss changes nothing")
    a.legend()

    bins, p50, p90 = _specular_tail()
    b.plot(bins, p90, "o-", color=VERM, lw=2, ms=5, label="90th percentile")
    b.plot(bins, p50, "o-", color=CYAN, lw=2, ms=5, label="median")
    b.set_yscale("log")
    b.set_xlabel("interocular specular mismatch (percentile bin)")
    b.set_ylabel("depth error (mm, log)")
    b.set_title("The damage is in the tail, not the average")
    b.legend()
    fig.savefig(out / "03_material_graph.png")
    plt.close(fig)


_TAIL_CACHE: dict = {}


def _specular_tail():
    return _TAIL_CACHE["bins"], _TAIL_CACHE["p50"], _TAIL_CACHE["p90"]


def compute_specular_tail(root: Path) -> None:
    """Post-hoc: error against measured specular mismatch, textured glossy only."""
    matcher = BlockMatcher(max_disparity=48, window=7)
    mis_all, err_all = [], []
    for light in LIGHTING:
        for perm in PERMUTATIONS:
            scene = BlenderRenderScene(root / f"{light}_p{perm}")
            stim = scene.stimulus()
            appearance = scene.appearance()
            depth = scale_to_depth(matcher.match(stim.left, stim.right), scene.rig)
            err = np.abs(depth.value - stim.depth)
            mismatch = appearance.specular_mismatch(stim.disparity)
            labels = {m["material_index"]: m["label"] for m in scene.chart["materials"]}
            keep = [
                k for k, v in labels.items() if v.endswith("glossy") and not v.startswith("none")
            ]
            sel = (
                np.isin(appearance.material_index, keep)
                & stim.matched
                & np.isfinite(err)
                & np.isfinite(mismatch)
            )
            mis_all.append(mismatch[sel])
            err_all.append(err[sel])
    mis = np.concatenate(mis_all)
    err = np.concatenate(err_all)
    edges = np.quantile(mis, [0, 0.5, 0.8, 0.95, 0.99, 1.0])
    labels, p50, p90 = [], [], []
    for lo, hi, name in zip(
        edges[:-1], edges[1:], ["0-50", "50-80", "80-95", "95-99", "99-100"], strict=True
    ):
        s = (mis >= lo) & (mis <= hi)
        labels.append(name)
        p50.append(1000 * float(np.median(err[s])))
        p90.append(1000 * float(np.quantile(err[s], 0.9)))
    _TAIL_CACHE.update({"bins": labels, "p50": p50, "p90": p90, "edges": edges.tolist()})


def fig_lighting(panels, records, out: Path):
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap

    fig, axes = plt.subplots(3, 3, figsize=(12.5, 9.4))
    for row, light in enumerate(LIGHTING):
        panel = panels[light]
        axes[row][0].imshow(np.clip(panel["beauty"], 0, 1), cmap="gray")
        axes[row][0].set_ylabel(light, fontsize=12, weight="600", color=INK)
        err = np.where(panel["matched"], panel["error"], np.nan)
        im = axes[row][1].imshow(err, cmap=ERRMAP, vmin=0, vmax=0.35)
        state = np.zeros_like(panel["safe"], dtype=float)
        state[panel["answered"]] = 1.0
        state[panel["safe"]] = 2.0
        axes[row][2].imshow(
            state, cmap=ListedColormap(SAFE_COLORS), vmin=0, vmax=2
        )
        if row == 0:
            axes[row][0].set_title("rendered (prediction input)")
            axes[row][1].set_title("depth error")
            axes[row][2].set_title("pixels matched safely")
        plt.colorbar(im, ax=axes[row][1], fraction=0.035, pad=0.02, label="m")
        if row == len(LIGHTING) - 1:
            _safe_legend(axes[row][2])
        for ax in axes[row]:
            ax.set_xticks([])
            ax.set_yticks([])
    _patch_labels(axes[0][0], panels["ambient"])
    fig.suptitle(
        "Lighting test — identical geometry and identical materials in all three rows.",
        fontsize=10.5, color=SLATE, y=0.995,
    )
    fig.savefig(out / "04_lighting_panels.png")
    plt.close(fig)

    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 3.6))
    xs = np.arange(3)
    cov = [med(records, lighting=x, texture="none", finish="matte")["coverage"] for x in LIGHTING]
    err = [
        1000 * med(records, lighting=x, texture="none", finish="matte")["error_m"]
        for x in LIGHTING
    ]
    cols = ["#b03f2a", "#c98b4b", "#0d6e7d"]
    a.bar(xs, cov, color=cols, width=0.6)
    a.set_xticks(xs, list(LIGHTING))
    a.set_ylim(0, 1.08)
    a.set_ylabel("fraction of pixels answered")
    a.set_title("Blank wall: coverage depends entirely on the light")
    for x, v in zip(xs, cov, strict=True):
        a.text(x, v + 0.02, f"{v:.1%}", ha="center", fontsize=9, color=INK, weight="600")

    b.bar(xs, err, color=cols, width=0.6)
    b.set_xticks(xs, list(LIGHTING))
    b.set_yscale("log")
    b.set_ylabel("median depth error (mm, log)")
    b.set_title(f"...and so does the error, by 100{TIMES}")
    for x, v in zip(xs, err, strict=True):
        b.text(x, v * 1.3, f"{v:.1f}", ha="center", fontsize=9, color=INK, weight="600")
    fig.savefig(out / "04_lighting_graph.png")
    plt.close(fig)


def fig_calibration(records, per_render, out: Path):
    """The slide-1 thesis figure: variance vs the error it is supposed to track."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    base = category_variance(per_render, "textured")
    groups = [
        ("textured\n(correct)", base, CYAN),
        ("blank wall\n(wrong)", category_variance(per_render, "textureless"), CYAN),
        ("half-occluded\n(fabricated)", category_variance(per_render, "occluded"), VERM),
    ]
    xs = np.arange(len(groups))
    vals = [g[1] / base for g in groups]
    ax.bar(xs, vals, color=[g[2] for g in groups], width=0.58)
    ax.set_yscale("log")
    ax.set_xticks(xs, [g[0] for g in groups])
    ax.set_ylabel("reported variance, relative to textured (log)")
    ax.set_title("How loudly does the matcher warn you?")
    for x, v in zip(xs, vals, strict=True):
        ax.text(x, v * 1.3, f"{v:.0f}{TIMES}", ha="center", fontsize=11, color=INK, weight="700")
    ax.axhline(SAFE_FACTOR, color=SLATE, ls="--", lw=1)
    ax.text(
        2.45, SAFE_FACTOR * 1.15, f"'safe' threshold ({SAFE_FACTOR:.0f}{TIMES})",
        ha="right", fontsize=8.5, color=SLATE,
    )
    fig.savefig(out / "01_calibration.png")
    plt.close(fig)


def fig_plan(panels, out: Path):
    """Slide 1: the stimulus design. Same geometry, three lighting rigs."""
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(13.5, 3.5))
    for ax, light in zip(axes, LIGHTING, strict=True):
        ax.imshow(np.clip(panels[light]["beauty"], 0, 1), cmap="gray")
        ax.set_title(light, fontsize=12, weight="600")
        ax.set_xticks([])
        ax.set_yticks([])
    _patch_labels(axes[0], panels["ambient"], textures_only=False)
    fig.suptitle(
        "One geometry, eight materials, three lighting rigs. "
        "Ground-truth depth is the identical array in every frame.",
        fontsize=10.5, color=SLATE, y=1.03,
    )
    fig.savefig(out / "01_plan.png")
    plt.close(fig)


def fig_safe_vs_error(records, out: Path):
    """Synthesis: what the variance actually tracks -- contrast, not correctness."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.2, 4.3))
    groups = [
        ("dense\ntexture", "dense", "key", CYAN),
        ("coarse\ntexture", "coarse", "key", CYAN),
        ("blank wall\nflat light", "none", "ambient", VERM),
        ("blank wall\nraking light", "none", "grazing", "#c98b4b"),
    ]
    xs = np.arange(len(groups))
    errs, safes, cols = [], [], []
    for _, tex, light, col in groups:
        m = med(records, texture=tex, finish="matte", lighting=light)
        errs.append(1000 * m["error_m"])
        safes.append(m["safe_fraction"])
        cols.append(col)

    ax.bar(xs - 0.19, safes, 0.38, color=cols, label="fraction the matcher trusts")
    ax.set_ylabel("fraction of pixels trusted")
    ax.set_ylim(0, 1.12)
    ax.set_xticks(xs, [g[0] for g in groups])
    for x, v in zip(xs, safes, strict=True):
        ax.text(x - 0.19, v + 0.03, f"{v:.0%}", ha="center", fontsize=9, weight="600", color=INK)

    twin = ax.twinx()
    twin.bar(xs + 0.19, errs, 0.38, color=FAINT, label="actual error")
    twin.set_yscale("log")
    twin.set_ylabel("median depth error (mm, log)")
    twin.spines["right"].set_visible(True)
    for x, v in zip(xs, errs, strict=True):
        twin.text(x + 0.19, v * 1.35, f"{v:.1f}", ha="center", fontsize=9, color=SLATE)

    ax.set_title("Trust tracks contrast, not correctness")
    handles = [
        plt.Rectangle((0, 0), 1, 1, fc=CYAN),
        plt.Rectangle((0, 0), 1, 1, fc=FAINT),
    ]
    ax.legend(handles, ["fraction trusted (left axis)", "actual error (right axis)"],
              loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=2, fontsize=8.5)
    fig.savefig(out / "04_trust_vs_error.png")
    plt.close(fig)


def write_tables(records, per_render, out: Path) -> dict:
    tables = {
        "texture": [
            {"texture": t, **med(records, texture=t, finish="matte")} for t in TEXTURES
        ],
        "material": [
            {
                "texture": t,
                "matte": med(records, texture=t, finish="matte"),
                "glossy": med(records, texture=t, finish="glossy"),
            }
            for t in TEXTURES
        ],
        "lighting": [
            {
                "lighting": light,
                "textured": med(records, lighting=light, texture="dense", finish="matte"),
                "textureless": med(records, lighting=light, texture="none", finish="matte"),
            }
            for light in LIGHTING
        ],
        "calibration": {
            "textured": category_variance(per_render, "textured"),
            "textureless": category_variance(per_render, "textureless"),
            "occluded": category_variance(per_render, "occluded"),
        },
        "specular_tail": _TAIL_CACHE,
        "safe_factor": SAFE_FACTOR,
    }
    (out / "data.json").write_text(json.dumps(tables, indent=2))
    return tables


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stimuli", type=Path, default=Path("results/stimuli/chart"))
    ap.add_argument("--out", type=Path, default=Path("slides/exp003_appearance_and_matching"))
    args = ap.parse_args()

    figures = args.out / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    _style()

    scored, panels = analyse(args.stimuli)
    records = scored["records"]
    per_render = scored["per_render"]
    compute_specular_tail(args.stimuli)

    fig_plan(panels, figures)
    fig_calibration(records, per_render, figures)
    fig_texture(panels, records, figures)
    fig_material(panels, records, figures)
    fig_lighting(panels, records, figures)
    fig_safe_vs_error(records, figures)
    tables = write_tables(records, per_render, figures.parent)

    print("\n--- headline numbers (compare against findings.md) ---")
    c = tables["calibration"]
    print(
        f"variance textured {c['textured']:.0f}  textureless {c['textureless']:.0f} "
        f"({c['textureless'] / c['textured']:.0f}x)  occluded {c['occluded']:.0f} "
        f"({c['occluded'] / c['textured']:.0f}x)"
    )
    for row in tables["lighting"]:
        t = row["textureless"]
        print(f"{row['lighting']:>8}  blank wall: coverage {t['coverage']:.3f}  "
              f"error {1000 * t['error_m']:.1f} mm")
    print(f"\nwrote {figures} and {figures.parent / 'data.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
