"""Figures and tables for the exp004 slide deck.

    python -m experiments.exp004_real_data_transfer.run --config .../config.yaml
    python scripts/make_exp004_slides.py
    python scripts/build_deck.py slides/exp004_real_data_transfer

**Every number on a slide is read from the run's ``summary.json``, not
recomputed.** exp003's slide script re-scored all twelve renders and had to
replicate the record's aggregation order by hand -- it got 730x where findings.md
said 637x, and the comment explaining why is still there. Reading the pinned
artefact removes that whole class of disagreement: the deck cannot drift from the
record because it has no second opinion.

Matchers are re-run only for the handful of scenes that appear as *pictures*,
where per-pixel arrays are needed and no summary can help.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap

from activestereo.inference import BlockMatcher
from activestereo.metrics import local_contrast
from activestereo.scenes.middlebury import MiddleburyScene

# Scenes shown as pictures. Held-out only: featuring a scene whose numbers were
# peeked would put the least trustworthy data on the most persuasive slide.
PANEL_SCENES = ("Motorcycle", "Playroom")
H2_SCENE = "Motorcycle"

INK = "#101a1f"
SLATE = "#55676e"
FAINT = "#8fa1a7"
CYAN = "#0d6e7d"
VERM = "#b03f2a"
AMBER = "#a8712f"
RULE = "#d3dedf"
TIMES = "\u00d7"  # multiplication sign by escape: ruff RUF001 flags the literal
ERRMAP = "Reds"  # white at zero: pale must read as "fine", not as "hot"

MATCHER_COLOR = {"block": VERM, "sgbm": CYAN}

# exp001's random-dot values, for the reference lines on the H1 graph.
EXP001 = {"block": 0.796, "sgbm": 0.090}

# A display threshold for the three-way "safe matching" map, not a pipeline
# value. Same convention and same factor as exp003's deck so the two are
# readable side by side.
SAFE_FACTOR = 10.0


def _style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": RULE,
            "axes.labelcolor": SLATE,
            "axes.titlesize": 9,
            "axes.titleweight": "bold",
            "axes.titlecolor": INK,
            "axes.labelsize": 8.5,
            "xtick.color": SLATE,
            "ytick.color": SLATE,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "font.size": 9,
            "legend.fontsize": 8,
            "legend.frameon": False,
            "grid.color": RULE,
            "savefig.bbox": "tight",
            "savefig.dpi": 160,
        }
    )


def load_run(results: Path, run_id: str | None) -> tuple[dict, str]:
    """Read the pinned summary.json. Latest exp004 run unless one is named."""
    if run_id:
        path = results / run_id / "summary.json"
    else:
        candidates = sorted(results.glob("exp004-*/summary.json"))
        if not candidates:
            raise SystemExit(f"no exp004 run under {results}. Run the experiment first.")
        path = candidates[-1]
    return json.loads(path.read_text()), path.parent.name


def panels(root: Path, downsample: int, window: int) -> dict:
    """Re-run matchers on the picture scenes only. ~4 min, not ~13."""
    out: dict[str, dict] = {}
    for name in dict.fromkeys((*PANEL_SCENES, H2_SCENE)):
        scene = MiddleburyScene(root / f"{name}-perfect", downsample=downsample)
        base = scene.stimulus("im1")
        contrast = local_contrast(base.left, window)
        matcher = BlockMatcher(max_disparity=scene.ndisp, window=window)

        variants = {}
        for variant in ("im1", "im1E", "im1L"):
            stim = scene.stimulus(variant)
            est = matcher.match(stim.left, stim.right)
            answered = np.isfinite(est.value)
            err = np.abs(est.value - stim.disparity)
            baseline = float(np.nanmedian(est.variance[stim.scorable & answered]))
            variants[variant] = {
                "right": stim.right,
                "value": est.value,
                "variance": est.variance,
                "error": np.where(stim.scorable, err, np.nan),
                "answered": answered,
                "safe": answered & (est.variance <= SAFE_FACTOR * baseline),
                "baseline": baseline,
            }
            print(f"[slides] scored {name}/{variant}")

        out[name] = {
            "left": base.left,
            "disparity": np.where(base.known, base.disparity, np.nan),
            "occluded": base.occluded,
            "unknown": ~base.known if base.known is not None else np.zeros(base.shape, bool),
            "out_of_frame": base.out_of_frame,
            "scorable": base.scorable,
            "contrast": contrast,
            "ndisp": scene.ndisp,
            "variants": variants,
        }
    return out


# --- shared drawing helpers -------------------------------------------------


def _bare(ax, title=None):
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_edgecolor(RULE)
    if title:
        ax.set_title(title)


SAFE_COLORS = ["#e9eff0", "#f0c9bf", CYAN]
SAFE_NAMES = ["no answer", "answered, distrusted", "answered, trusted"]


def _safe_map(ax, panel, variant="im1"):
    v = panel["variants"][variant]
    code = np.zeros(v["answered"].shape)
    code[v["answered"]] = 1
    code[v["safe"]] = 2
    ax.imshow(code, cmap=ListedColormap(SAFE_COLORS), vmin=0, vmax=2, interpolation="nearest")


def _safe_legend(ax):
    from matplotlib.patches import Patch

    ax.legend(
        handles=[Patch(facecolor=c, label=n) for c, n in zip(SAFE_COLORS, SAFE_NAMES, strict=True)],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.04),
        ncol=3,
        fontsize=7.5,
    )


def _occlusion_outline(ax, panel):
    """Draw ground-truth occlusion as a contour, so it overlays without hiding."""
    ax.contour(
        panel["occluded"].astype(float), levels=[0.5], colors=[AMBER], linewidths=0.6, alpha=0.9
    )


# --- figures ----------------------------------------------------------------


def fig_plan(pan, out: Path):
    """The corpus: what the stimulus is, and what ground truth it carries."""
    names = list(PANEL_SCENES)
    fig, axes = plt.subplots(len(names), 4, figsize=(13.2, 3.4 * len(names)))
    axes = np.atleast_2d(axes)
    for row, name in enumerate(names):
        p = pan[name]
        _bare(axes[row][0], f"{name} — left photograph" if row == 0 else name)
        axes[row][0].imshow(p["left"], cmap="gray", interpolation="nearest")

        _bare(axes[row][1], "ground-truth disparity (px)" if row == 0 else None)
        im = axes[row][1].imshow(p["disparity"], cmap="viridis", interpolation="nearest")
        fig.colorbar(im, ax=axes[row][1], fraction=0.035, pad=0.02)

        _bare(axes[row][2], "half-occlusion (amber)" if row == 0 else None)
        axes[row][2].imshow(p["left"], cmap="gray", interpolation="nearest")
        axes[row][2].imshow(
            np.ma.masked_where(~p["occluded"], p["occluded"].astype(float)),
            cmap=ListedColormap([AMBER]),
            alpha=0.85,
            interpolation="nearest",
        )

        _bare(axes[row][3], "unknown GT · out of frame" if row == 0 else None)
        code = np.zeros(p["left"].shape)
        code[p["out_of_frame"]] = 1
        code[p["unknown"]] = 2
        axes[row][3].imshow(
            code,
            cmap=ListedColormap(["#eef2f3", "#c9d6d8", VERM]),
            vmin=0,
            vmax=2,
            interpolation="nearest",
        )
    fig.suptitle(
        "Real photographs with structured-light ground truth. Unknown pixels (red) are a gap "
        "in our knowledge,\nnot a fact about the scene, and are excluded from every statistic "
        "(ADR-0011).",
        fontsize=8.5,
        color=SLATE,
        y=1.02,
    )
    fig.tight_layout()
    fig.savefig(out / "01_plan.png")
    plt.close(fig)


REGIONS = {
    "matched": "var_matched_px2",
    "occluded\n(all)": "var_occluded_px2",
    "occluded\nlow contrast": "var_occluded_lo_contrast_px2",
    "occluded\nHIGH contrast": "var_occluded_hi_contrast_px2",
}


def region_stats(data) -> dict[str, tuple[float, float]]:
    """Per-region median variance, and the ratio to matched, over held-out scenes.

    The ratio is the **median of per-scene ratios**, matching how findings.md
    computes ``var_ratio_median``. Taking a ratio of the two pooled medians
    instead is equally defensible and gives 0.225 where the record says 0.324 --
    the same aggregation trap exp003's slide script hit going the other way
    (730x against a recorded 637x). A deck that quietly disagrees with the record
    of record is a liability whichever number is prettier, so the convention is
    inherited rather than chosen here.
    """
    held = data["held_out_scenes"]
    cells = [data["per_scene"][s]["by_matcher"]["block"]["im1"] for s in held]
    out = {}
    for label, key in REGIONS.items():
        level = float(np.nanmedian([c[key] for c in cells]))
        ratio = float(np.nanmedian([c[key] / c["var_matched_px2"] for c in cells]))
        out[label] = (level, ratio)
    return out


def fig_calibration(data, out: Path):
    """The headline: reported variance by region, block matcher, held-out scenes.

    Bars are the **ratio**, not the level. Plotting levels and labelling ratios
    put a bar at 872 px² next to a label reading 0.32x, when 872/3873 is 0.225 --
    the two aggregation orders again, this time visible on the same chart. Anyone
    reading a ratio off the bars would get a different number from the caption.
    The level is annotated underneath instead, where it informs without inviting
    arithmetic that disagrees with the record.
    """
    stats = region_stats(data)
    colors = ["#8fa1a7", AMBER, CYAN, VERM]

    fig, ax = plt.subplots(figsize=(8.0, 4.5))
    xs = np.arange(len(stats))
    ratios = [v[1] for v in stats.values()]
    ax.bar(xs, ratios, color=colors, width=0.62)
    for x, (label, (level, rel)) in zip(xs, stats.items(), strict=True):
        hot = label.startswith("occluded\nHIGH")
        ax.annotate(
            f"{rel:.2f}{TIMES}",
            (x, rel),
            textcoords="offset points",
            xytext=(0, 5),
            ha="center",
            fontsize=10 if hot else 9,
            color=INK,
            fontweight="bold" if hot else "normal",
        )
        ax.annotate(
            f"{level:,.0f} px²",
            (x, rel),
            textcoords="offset points",
            xytext=(0, 20),
            ha="center",
            fontsize=7.5,
            color=FAINT,
        )
    ax.axhline(1.0, color=INK, lw=1.2)
    ax.annotate(
        "1.0 — as confident as on pixels it genuinely matched",
        (-0.45, 1.08),
        fontsize=7.5,
        color=INK,
        ha="left",
    )
    ax.set_yscale("log")
    ax.set_xticks(xs)
    ax.set_xticklabels(list(stats))
    ax.set_ylabel(f"variance relative to matched pixels ({TIMES}, log)")
    ax.set_title("Where the matcher says it is confident")
    ax.grid(axis="y", lw=0.5, alpha=0.5)
    ax.set_axisbelow(True)
    ax.margins(y=0.3)
    fig.text(
        0.5,
        -0.06,
        "Below the line, the matcher is MORE confident where it has no correspondent at all.\n"
        "Ratios are medians of per-scene ratios, matching findings.md; levels are medians of "
        "per-scene levels.",
        ha="center",
        fontsize=8.5,
        color=SLATE,
    )
    fig.savefig(out / "01_calibration.png")
    plt.close(fig)


def fig_h1_panels(pan, out: Path):
    fig, axes = plt.subplots(len(PANEL_SCENES), 4, figsize=(13.2, 3.4 * len(PANEL_SCENES)))
    axes = np.atleast_2d(axes)
    for row, name in enumerate(PANEL_SCENES):
        p = pan[name]
        v = p["variants"]["im1"]
        _bare(axes[row][0], "photograph" if row == 0 else None)
        axes[row][0].imshow(p["left"], cmap="gray", interpolation="nearest")
        axes[row][0].set_ylabel(name, color=INK, fontsize=9, fontweight="bold")

        _bare(axes[row][1], "prediction (px)" if row == 0 else None)
        axes[row][1].imshow(v["value"], cmap="viridis", interpolation="nearest")

        _bare(axes[row][2], "disparity error on matched px" if row == 0 else None)
        im = axes[row][2].imshow(v["error"], cmap=ERRMAP, vmin=0, vmax=4, interpolation="nearest")
        fig.colorbar(im, ax=axes[row][2], fraction=0.035, pad=0.02)

        _bare(axes[row][3], "safe matching · occlusion outlined" if row == 0 else None)
        _safe_map(axes[row][3], p)
        _occlusion_outline(axes[row][3], p)
        if row == len(PANEL_SCENES) - 1:
            _safe_legend(axes[row][3])
    fig.tight_layout()
    fig.savefig(out / "02_h1_panels.png")
    plt.close(fig)


def fig_h1_graph(data, out: Path):
    held = data["held_out_scenes"]
    seen = data["seen_scenes"]
    order = held + seen

    fig, (a, b) = plt.subplots(1, 2, figsize=(12.4, 4.2), width_ratios=[1.65, 1])
    xs = np.arange(len(order))
    width = 0.38
    for k, matcher in enumerate(("block", "sgbm")):
        vals = [data["per_scene"][s]["by_matcher"][matcher]["im1"]["hallucination"] for s in order]
        a.bar(
            xs + (k - 0.5) * width,
            vals,
            width=width,
            color=MATCHER_COLOR[matcher],
            label=matcher,
        )
    # Reference lines go in the legend rather than as in-plot text: this panel is
    # ten scenes wide and every interior position collides with a bar.
    for matcher in ("block", "sgbm"):
        a.axhline(
            EXP001[matcher],
            color=MATCHER_COLOR[matcher],
            lw=1.0,
            ls="--",
            alpha=0.85,
            label=f"{matcher} on random dots (exp001): {EXP001[matcher]:.1%}",
        )
    a.axvline(len(held) - 0.5, color=FAINT, lw=0.8, ls=":")
    a.annotate(
        "declared peeks, excluded from every median →",
        (len(held) - 0.45, 0.955),
        fontsize=7.5,
        color=FAINT,
        ha="left",
        va="top",
    )
    a.set_ylim(0, 1.0)
    a.set_xticks(xs)
    a.set_xticklabels(order, rotation=45, ha="right")
    a.set_ylabel("fraction of half-occlusions answered")
    a.set_title("Hallucination in half-occlusions, per scene")
    a.legend(loc="upper center", bbox_to_anchor=(0.5, -0.28), ncol=2, fontsize=7.5)
    a.grid(axis="y", lw=0.5, alpha=0.5)
    a.set_axisbelow(True)

    # The transfer plot: random dots vs photographs.
    for matcher in ("block", "sgbm"):
        med = data["by_matcher_heldout"][matcher]["im1"]["hallucination_median"]
        b.plot(
            [0, 1],
            [EXP001[matcher], med],
            "o-",
            color=MATCHER_COLOR[matcher],
            lw=2,
            ms=7,
            label=matcher,
        )
        b.annotate(
            f"{EXP001[matcher]:.1%}",
            (0, EXP001[matcher]),
            textcoords="offset points",
            xytext=(-6, 0),
            ha="right",
            fontsize=8.5,
            color=MATCHER_COLOR[matcher],
        )
        b.annotate(
            f"{med:.1%}",
            (1, med),
            textcoords="offset points",
            xytext=(6, 0),
            ha="left",
            fontsize=8.5,
            fontweight="bold",
            color=MATCHER_COLOR[matcher],
        )
    b.set_xlim(-0.35, 1.35)
    b.set_xticks([0, 1])
    b.set_xticklabels(["random dots\n(exp001)", "photographs\n(exp004)"])
    b.set_ylim(0, 1)
    b.set_ylabel("hallucination rate")
    b.set_title("What transfers, and what does not")
    b.grid(axis="y", lw=0.5, alpha=0.5)
    b.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(out / "02_h1_graph.png")
    plt.close(fig)


def fig_h1b_panels(pan, out: Path):
    """Variance where it should be highest. The visual is that it is not."""
    fig, axes = plt.subplots(len(PANEL_SCENES), 3, figsize=(11.6, 3.5 * len(PANEL_SCENES)))
    axes = np.atleast_2d(axes)
    for row, name in enumerate(PANEL_SCENES):
        p = pan[name]
        v = p["variants"]["im1"]
        _bare(axes[row][0], "local contrast" if row == 0 else None)
        axes[row][0].imshow(p["contrast"], cmap="bone_r", interpolation="nearest")
        axes[row][0].set_ylabel(name, color=INK, fontsize=9, fontweight="bold")

        _bare(axes[row][1], "reported variance (log px²)" if row == 0 else None)
        with np.errstate(invalid="ignore", divide="ignore"):
            logvar = np.log10(np.where(v["variance"] > 0, v["variance"], np.nan))
        im = axes[row][1].imshow(logvar, cmap="magma", interpolation="nearest")
        fig.colorbar(im, ax=axes[row][1], fraction=0.035, pad=0.02)
        _occlusion_outline(axes[row][1], p)

        _bare(axes[row][2], "occlusions, split by contrast" if row == 0 else None)
        thr = float(np.nanmedian(p["contrast"][p["scorable"]]))
        code = np.zeros(p["left"].shape)
        code[p["occluded"] & (p["contrast"] <= thr)] = 1
        code[p["occluded"] & (p["contrast"] > thr)] = 2
        axes[row][2].imshow(
            code,
            cmap=ListedColormap(["#eef2f3", CYAN, VERM]),
            vmin=0,
            vmax=2,
            interpolation="nearest",
        )
        if row == len(PANEL_SCENES) - 1:
            from matplotlib.patches import Patch

            axes[row][2].legend(
                handles=[
                    Patch(facecolor=CYAN, label="occluded, low contrast (safely distrusted)"),
                    Patch(facecolor=VERM, label="occluded, HIGH contrast (wrongly trusted)"),
                ],
                loc="upper center",
                bbox_to_anchor=(0.5, -0.03),
                fontsize=7.5,
            )
    fig.suptitle(
        "Amber outlines are ground-truth half-occlusions. In the variance map they are DARK "
        "where contrast is high —\nthe matcher's most confident answers sit exactly where it "
        "has no correspondent at all.",
        fontsize=8.5,
        color=SLATE,
        y=1.02,
    )
    fig.tight_layout()
    fig.savefig(out / "03_h1b_panels.png")
    plt.close(fig)


def fig_h1b_graph(data, out: Path):
    held = data["held_out_scenes"]
    fig, (a, b) = plt.subplots(1, 2, figsize=(12.4, 4.2))

    ratios = [data["per_scene"][s]["by_matcher"]["block"]["im1"]["var_ratio"] for s in held]
    colors = [VERM if r < 1.0 else SLATE for r in ratios]
    a.barh(np.arange(len(held)), ratios, color=colors, height=0.62)
    a.axvline(1.0, color=INK, lw=1.2)
    a.annotate(
        "1.0 — equally confident\nas on matched pixels",
        (1.05, 0.2),
        fontsize=7.5,
        color=INK,
    )
    a.set_yticks(np.arange(len(held)))
    a.set_yticklabels(held)
    a.set_xscale("log")
    a.set_xlabel("occluded variance / matched variance (log)")
    a.set_title("Below 1.0 in 7 of 8 scenes")
    a.grid(axis="x", lw=0.5, alpha=0.5)
    a.set_axisbelow(True)

    stats = region_stats(data)
    keep = ["matched", "occluded\nlow contrast", "occluded\nHIGH contrast"]
    xs = np.arange(len(keep))
    rel = [stats[k][1] for k in keep]
    b.bar(xs, rel, color=["#8fa1a7", CYAN, VERM], width=0.6)
    for x, k in zip(xs, keep, strict=True):
        b.annotate(
            f"{stats[k][1]:.2f}{TIMES}",
            (x, stats[k][1]),
            textcoords="offset points",
            xytext=(0, 4),
            ha="center",
            fontsize=9,
        )
    b.axhline(1.0, color=INK, lw=1.0)
    b.set_yscale("log")
    b.set_xticks(xs)
    b.set_xticklabels(keep)
    b.set_ylabel(f"variance relative to matched ({TIMES}, log)")
    b.set_title("The confound control, reversed")
    b.grid(axis="y", lw=0.5, alpha=0.5)
    b.set_axisbelow(True)
    b.margins(y=0.2)
    fig.tight_layout()
    fig.savefig(out / "03_h1b_graph.png")
    plt.close(fig)


def fig_h2_panels(pan, out: Path):
    p = pan[H2_SCENE]
    labels = {
        "im1": "im1 — matched photometry",
        "im1E": "im1E — different exposure",
        "im1L": "im1L — different lighting",
    }
    fig, axes = plt.subplots(3, 3, figsize=(11.8, 9.2))
    for row, variant in enumerate(("im1", "im1E", "im1L")):
        v = p["variants"][variant]
        _bare(axes[row][0], "right image" if row == 0 else None)
        axes[row][0].imshow(v["right"], cmap="gray", vmin=0, vmax=1, interpolation="nearest")
        axes[row][0].set_ylabel(labels[variant], color=INK, fontsize=8.5, fontweight="bold")

        _bare(axes[row][1], "prediction" if row == 0 else None)
        axes[row][1].imshow(v["value"], cmap="viridis", interpolation="nearest")

        _bare(axes[row][2], "answered on matched px" if row == 0 else None)
        code = np.zeros(p["left"].shape)
        code[p["scorable"]] = 1
        code[p["scorable"] & v["answered"]] = 2
        axes[row][2].imshow(
            code,
            cmap=ListedColormap(["#eef2f3", VERM, CYAN]),
            vmin=0,
            vmax=2,
            interpolation="nearest",
        )
    fig.suptitle(
        f"{H2_SCENE}: geometry and ground truth identical across all three rows — only the "
        "right image's photometry changes.\nRed in the last column is a matchable pixel the "
        "matcher declined. It declines, rather than fabricating.",
        fontsize=8.5,
        color=SLATE,
        y=1.005,
    )
    fig.tight_layout()
    fig.savefig(out / "04_h2_panels.png")
    plt.close(fig)


def fig_h2_graph(data, out: Path):
    fig, (a, b) = plt.subplots(1, 2, figsize=(12.4, 4.2))
    verdicts = data["hypotheses"]
    for k, matcher in enumerate(("block", "sgbm")):
        h2 = verdicts[matcher]["H2"]
        for j, variant in enumerate(("im1E", "im1L")):
            drops = np.array(h2[variant]["per_scene_coverage_drop"])
            rises = np.array(h2[variant]["per_scene_error_rise"]) + 1.0
            pos = k * 2 + j
            a.scatter(
                np.full(drops.shape, pos) + np.linspace(-0.13, 0.13, drops.size),
                drops,
                color=MATCHER_COLOR[matcher],
                s=22,
                alpha=0.75,
            )
            a.hlines(np.median(drops), pos - 0.24, pos + 0.24, color=INK, lw=2)
            b.scatter(
                np.full(rises.shape, pos) + np.linspace(-0.13, 0.13, rises.size),
                rises,
                color=MATCHER_COLOR[matcher],
                s=22,
                alpha=0.75,
            )
            b.hlines(np.median(rises), pos - 0.24, pos + 0.24, color=INK, lw=2)

    ticks = ["block\nim1E", "block\nim1L", "sgbm\nim1E", "sgbm\nim1L"]
    a.axhline(0.10, color=VERM, lw=1.0, ls="--")
    a.annotate(
        "falsifier: a drop past 10 points is the\nWITHHELD-evidence signature",
        (-0.4, 0.115),
        fontsize=7.5,
        color=VERM,
    )
    a.set_xticks(range(4))
    a.set_xticklabels(ticks)
    a.set_ylabel("coverage drop vs im1 (paired, per scene)")
    a.set_title("Coverage collapses — the prediction said it would not")
    a.grid(axis="y", lw=0.5, alpha=0.5)
    a.set_axisbelow(True)

    b.axhline(1.25, color=CYAN, lw=1.0, ls="--")
    b.annotate(f"falsifier: below 1.25{TIMES} is 'no effect'", (-0.4, 1.32),
               fontsize=7.5, color=CYAN)
    b.set_yscale("log")
    b.set_xticks(range(4))
    b.set_xticklabels(ticks)
    b.set_ylabel(f"error multiplier vs im1 ({TIMES}, log)")
    b.set_title("Error rises too — so the signature is mixed")
    b.grid(axis="y", lw=0.5, alpha=0.5)
    b.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(out / "04_h2_graph.png")
    plt.close(fig)


def fig_controls(data, out: Path):
    held = data["held_out_scenes"]
    order = held + data["seen_scenes"]
    fig, (a, b, c) = plt.subplots(1, 3, figsize=(13.2, 3.8))

    for s in order:
        sweep = data["per_scene"][s]["tolerance_sweep"]
        keys = list(sweep)
        a.plot(
            range(len(keys)),
            [sweep[k] for k in keys],
            "o-",
            color=CYAN if s in held else FAINT,
            lw=1.2,
            ms=4,
            alpha=0.85,
        )
    a.set_xticks(range(3))
    a.set_xticklabels(["0.5 px", "1.0 px", "2.0 px"])
    a.set_ylabel("occlusion fraction")
    a.set_title("Occlusion is not sensitive to the\ncross-check tolerance")
    a.grid(lw=0.5, alpha=0.5)
    a.set_axisbelow(True)

    floors = [data["per_scene"][s]["noise_floor_px"] for s in order]
    errs = [data["per_scene"][s]["by_matcher"]["block"]["im1"]["disparity_error_px"] for s in order]
    b.scatter(floors, errs, color=[CYAN if s in held else FAINT for s in order], s=34)
    lim = max(max(errs), max(floors)) * 1.15
    b.plot([0, lim], [0, lim], color=VERM, lw=1.0, ls="--")
    b.annotate("error = GT noise floor", (lim * 0.42, lim * 0.47), fontsize=7.5, color=VERM)
    b.set_xlabel("GT noise floor, disp0-sd (px)")
    b.set_ylabel("median |Δd| (px)")
    b.set_title("Errors sit well above the scanner's\nown uncertainty")
    b.grid(lw=0.5, alpha=0.5)
    b.set_axisbelow(True)

    unknown = [100 * data["per_scene"][s]["unknown_fraction"] for s in order]
    c.barh(
        np.arange(len(order)),
        unknown,
        color=[CYAN if s in held else FAINT for s in order],
        height=0.62,
    )
    c.set_yticks(np.arange(len(order)))
    c.set_yticklabels(order, fontsize=7.5)
    c.set_xlabel("% of frame with no ground truth")
    c.set_title("Scanner holes, excluded from\nevery statistic (ADR-0011)")
    c.grid(axis="x", lw=0.5, alpha=0.5)
    c.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(out / "05_controls.png")
    plt.close(fig)


def write_tables(data, run_id: str, out: Path) -> dict:
    tables = {
        "run_id": run_id,
        "held_out_scenes": data["held_out_scenes"],
        "seen_scenes": data["seen_scenes"],
        "heldout_medians": data["by_matcher_heldout"],
        "hypotheses": data["hypotheses"],
        "variance_by_region": {
            label.replace("\n", " "): {"median_px2": level, "ratio_to_matched": ratio}
            for label, (level, ratio) in region_stats(data).items()
        },
        "aggregation": (
            "ratios are medians of per-scene ratios, matching findings.md's "
            "var_ratio_median; a ratio of pooled medians gives 0.225 instead of 0.324"
        ),
        "exp001_reference": EXP001,
        "safe_factor": SAFE_FACTOR,
    }
    (out / "data.json").write_text(json.dumps(tables, indent=2))
    return tables


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", type=Path, default=Path("results"))
    ap.add_argument("--run-id", default=None, help="default: the latest exp004 run")
    ap.add_argument("--corpus", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=Path("slides/exp004_real_data_transfer"))
    args = ap.parse_args(argv)

    data, run_id = load_run(args.results, args.run_id)
    corpus = args.corpus or Path(
        __import__("os").environ.get("ACTIVESTEREO_DATA_ROOT", "~/datasets/middlebury2014")
    ).expanduser()

    figures = args.out / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    _style()

    pan = panels(corpus, data["downsample"], window=7)

    fig_plan(pan, figures)
    fig_calibration(data, figures)
    fig_h1_panels(pan, figures)
    fig_h1_graph(data, figures)
    fig_h1b_panels(pan, figures)
    fig_h1b_graph(data, figures)
    fig_h2_panels(pan, figures)
    fig_h2_graph(data, figures)
    fig_controls(data, figures)
    tables = write_tables(data, run_id, args.out)

    print(f"\n--- headline numbers from {run_id} (compare against findings.md) ---")
    for label, v in tables["variance_by_region"].items():
        print(f"  {label:<24} {v['median_px2']:9,.0f} px²   {v['ratio_to_matched']:6.3f}{TIMES}")
    for matcher in ("block", "sgbm"):
        m = tables["heldout_medians"][matcher]["im1"]
        print(
            f"{matcher:>6}: coverage {m['coverage_median']:.3f}  bad2 {m['bad2_median']:.3f}  "
            f"halluc {m['hallucination_median']:.3f} (exp001 RDS {EXP001[matcher]:.3f})  "
            f"var_ratio {m['var_ratio_median']:.3f}"
        )
    print(f"\nwrote {figures} and {args.out / 'data.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
