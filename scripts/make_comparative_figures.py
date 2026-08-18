"""Score all three stimulus families through one set of definitions.

    python scripts/make_comparative_figures.py
    python scripts/build_deck.py slides/comparative_stimulus_families

exp001 (random dots), exp003 (rendered charts) and exp004 (photographs) are a
deliberate progression from fully synthetic to fully measured, but each published
its own statistics computed its own way: exp001 has a hallucination rate and no
variance ratio, exp003 has variance ratios and never measured hallucination,
exp004 has both plus a contrast stratification neither of the others attempted.
Putting the published numbers side by side would put three different definitions
in one table.

So everything here is **re-scored from the stimuli** through
``activestereo.metrics``, and the script cross-checks itself against each
experiment's published headline before drawing anything. If a recomputed number
disagrees with the record, it raises rather than plotting.

**This is a synthesis, not an experiment.** It has no hypotheses and no
falsifiers. Anything it surfaces that is new -- and the contrast stratification
applied backwards to random dots and renders is new -- is exploratory, labelled as
such in the figures themselves, and needs its own pre-registered test before it
counts as a result.

**What is comparable.** Rates and ratios are dimensionless and travel between
families. Absolute errors do not: the families differ in rig, depth range, image
size and disparity range. Disparity range especially is a live confound -- a
matcher searching 247 candidates has more chances to find a spurious minimum than
one searching 48 -- so it is reported beside every family rather than hidden.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from activestereo.inference import BlockMatcher
from activestereo.metrics import local_contrast, score_all
from activestereo.scenes import RandomDotStereogram, disk
from activestereo.scenes.blender import BlenderRenderScene
from activestereo.scenes.middlebury import MiddleburyScene
from activestereo.types import StereoRig

INK = "#101a1f"
SLATE = "#55676e"
FAINT = "#8fa1a7"
CYAN = "#0d6e7d"
VERM = "#b03f2a"
AMBER = "#a8712f"
RULE = "#d3dedf"
TIMES = "\u00d7"  # by escape: ruff RUF001 flags the literal

FAMILIES = ("random dots", "rendered chart", "photographs")
FAMILY_COLOR = {
    "random dots": "#8fa1a7",
    "rendered chart": AMBER,
    "photographs": VERM,
}

WINDOW = 7

#: Published headlines each re-score must reproduce. The whole point of a shared
#: implementation is that it agrees with the records it is meant to unify, so a
#: disagreement is a bug here and not a discovery.
PUBLISHED = {
    "random dots": {"hallucination_block": 0.796, "hallucination_sgbm": 0.090},
    "photographs": {"hallucination_block": 0.826, "variance_ratio_block": 0.324},
}
TOLERANCE = 0.02

#: exp003's variance ratios use a **textured-matched** baseline, not all matched
#: pixels: its chart deliberately contains textureless patches whose variance is
#: 637x the textured level, and pooling them into the denominator swamps it.
#:
#: That is not a definition the shared metric can adopt, because "textureless
#: patch" is a concept only the chart has -- it needs an albedo pass to identify.
#: So the chart appears in the shared-definition figure at ~0.8x, which looks like
#: anti-calibration and is not: it is an inflated denominator. Both numbers are
#: plotted, and the reason is on the figure.
EXP003_TEXTURED_BASELINE = {"textureless": 637.0, "occluded": 4.7}


def _style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": RULE,
            "axes.labelcolor": SLATE,
            "axes.titlesize": 9.5,
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


def _matchers(max_disparity: int) -> dict:
    out: dict = {"block": BlockMatcher(max_disparity=max_disparity, window=WINDOW)}
    try:
        from activestereo.inference.sgbm import SGBMMatcher

        out["sgbm"] = SGBMMatcher(max_disparity=-(-max_disparity // 16) * 16)
    except ImportError:
        print("OpenCV unavailable; block matcher only.")
    return out


def _score_one(stim, matchers, max_disparity, family, label) -> list[dict]:
    contrast = local_contrast(stim.left, WINDOW)
    rows = []
    for name, matcher in matchers.items():
        est = matcher.match(stim.left, stim.right)
        rows.append(
            {
                "family": family,
                "label": label,
                "matcher": name,
                "max_disparity": max_disparity,
                **score_all(stim, est, contrast=contrast),
            }
        )
    print(f"[comparative] {family:<15} {label:<14} d={max_disparity}")
    return rows


def score_random_dots(seeds=(0, 1, 2, 3, 4)) -> list[dict]:
    """exp001's stimulus and rig, without the foveal term.

    ``confine_to_fovea`` adds an eccentricity penalty to *variance* and never
    touches values, so exp001's published hallucination rate is reproducible
    without it. A variance ratio for this family is therefore a new quantity that
    exp001 never published, and is labelled as such wherever it appears.
    """
    rig = StereoRig(baseline=0.064, focal_px=800.0, vergence=np.deg2rad(1.467))
    scene = RandomDotStereogram(
        disk, shape=(240, 320), near=0.9, far=1.6, radius=0.4, dot_size=2, density=0.5
    )
    matchers = _matchers(48)
    rows = []
    for seed in seeds:
        stim = scene.render(rig, np.random.default_rng(seed))
        rows += _score_one(stim, matchers, 48, "random dots", f"seed {seed}")
    return rows


def score_rendered_chart(root: Path) -> list[dict]:
    """exp003's twelve renders: 3 lighting rigs x 4 material permutations.

    Also records the *textured-matched* variance, so exp003's own ratios can be
    reproduced alongside the shared-definition ones. Identifying a textured patch
    needs the albedo pass, which is why no other family can offer this.
    """
    matchers = _matchers(48)
    rows = []
    for light in ("ambient", "key", "grazing"):
        for perm in range(4):
            name = f"{light}_p{perm}"
            directory = root / name
            if not directory.is_dir():
                raise SystemExit(
                    f"missing {directory}. Render the chart sweep first:\n"
                    "  python scripts/render_chart_sweep.py --out results/stimuli/chart"
                )
            scene = BlenderRenderScene(directory)
            stim = scene.stimulus()
            appearance = scene.appearance()
            labels = {m["material_index"]: m["label"] for m in scene.chart["materials"]}
            textured = np.isin(
                appearance.material_index,
                [k for k, v in labels.items() if not v.startswith("none")],
            )
            new = _score_one(stim, matchers, 48, "rendered chart", name)
            for row, matcher in zip(new, matchers.values(), strict=True):
                est = matcher.match(stim.left, stim.right)
                ok = np.isfinite(est.value) & np.isfinite(est.variance)
                row["var_textured_matched"] = float(
                    np.nanmedian(est.variance[textured & stim.scorable & ok])
                )
                row["var_occluded"] = float(np.nanmedian(est.variance[stim.occluded & ok]))
            rows += new
    return rows


def score_photographs(root: Path, scenes: list[str], downsample: int) -> list[dict]:
    rows = []
    for name in scenes:
        scene = MiddleburyScene(root / f"{name}-perfect", downsample=downsample)
        rows += _score_one(scene.stimulus("im1"), _matchers(scene.ndisp), scene.ndisp,
                           "photographs", name)
    return rows


def med(rows, family, matcher, key) -> float:
    vals = [r[key] for r in rows if r["family"] == family and r["matcher"] == matcher]
    finite = [v for v in vals if np.isfinite(v)]
    return float(np.median(finite)) if finite else float("nan")


def exp003_ratio(rows) -> float:
    """exp003's occluded-vs-textured ratio, in exp003's own aggregation order.

    A **ratio of medians**: pool pixels within a render, take the median across
    renders, then divide. exp004 does the opposite -- per-scene ratios, then a
    median of those -- and on this data the two give 4.7 and 4.0 for the same
    pixels. Neither is wrong; they are different summaries, and each experiment's
    record is stated in its own. The synthesis reproduces each record in the
    convention that record used, rather than imposing one and quietly disagreeing
    with both.
    """
    chart = [r for r in rows if r["family"] == "rendered chart" and r["matcher"] == "block"]
    occluded = float(np.nanmedian([r["var_occluded"] for r in chart]))
    textured = float(np.nanmedian([r["var_textured_matched"] for r in chart]))
    return occluded / textured if textured > 0 else float("nan")


def cross_check(rows) -> None:
    """Refuse to draw anything if the shared code disagrees with the records."""
    checks = [
        ("random dots", "block", "hallucination", PUBLISHED["random dots"]["hallucination_block"]),
        ("random dots", "sgbm", "hallucination", PUBLISHED["random dots"]["hallucination_sgbm"]),
        ("photographs", "block", "hallucination", PUBLISHED["photographs"]["hallucination_block"]),
        (
            "photographs",
            "block",
            "variance_ratio",
            PUBLISHED["photographs"]["variance_ratio_block"],
        ),
    ]
    print("\n--- cross-check against published findings ---")
    bad = []
    got003 = exp003_ratio(rows)
    want003 = EXP003_TEXTURED_BASELINE["occluded"]
    ok003 = np.isfinite(got003) and abs(got003 - want003) <= 0.3
    print(
        f"  {'rendered chart':<15}{'block':<7}{'var_ratio (exp003 defn)':<24} "
        f"published {want003:.1f}  recomputed {got003:.2f}   {'ok' if ok003 else 'MISMATCH'}"
    )
    if not ok003:
        bad.append(("rendered chart", "block", "var_ratio_exp003", want003, got003))
    for family, matcher, key, expected in checks:
        got = med(rows, family, matcher, key)
        tol = TOLERANCE if expected < 1.0 else 0.3  # exp003 quotes "5x" to one figure
        ok = np.isfinite(got) and abs(got - expected) <= tol
        print(
            f"  {family:<15}{matcher:<7}{key:<16} published {expected:.3f}  "
            f"recomputed {got:.3f}   {'ok' if ok else 'MISMATCH'}"
        )
        if not ok:
            bad.append((family, matcher, key, expected, got))
    if bad:
        raise SystemExit(
            "\nrecomputed values disagree with the published records:\n"
            + "\n".join(f"  {f}/{m}/{k}: {e:.3f} vs {g:.3f}" for f, m, k, e, g in bad)
            + "\nThe shared metrics exist to unify these experiments, so a "
            "disagreement is a bug in the unification, not a finding. Fix it "
            "before drawing anything."
        )


# --- figures ----------------------------------------------------------------


def fig_families(root_chart: Path, root_photo: Path, downsample: int, out: Path) -> None:
    rig = StereoRig(baseline=0.064, focal_px=800.0, vergence=np.deg2rad(1.467))
    rds = RandomDotStereogram(
        disk, shape=(240, 320), near=0.9, far=1.6, radius=0.4, dot_size=2, density=0.5
    ).render(rig, np.random.default_rng(0))
    chart = BlenderRenderScene(root_chart / "key_p0").stimulus()
    photo = MiddleburyScene(root_photo / "Motorcycle-perfect", downsample=downsample).stimulus()

    fig, axes = plt.subplots(2, 3, figsize=(12.6, 6.4))
    for col, (stim, title, sub) in enumerate(
        (
            (rds, "exp001 — random dots", "textured everywhere, matte, evenly lit"),
            (chart, "exp003 — rendered chart", "geometry fixed, appearance varied"),
            (photo, "exp004 — photographs", "ground truth we did not author"),
        )
    ):
        axes[0][col].imshow(stim.left, cmap="gray", interpolation="nearest")
        axes[0][col].set_title(f"{title}\n{sub}", fontsize=9)
        axes[1][col].imshow(stim.left, cmap="gray", interpolation="nearest")
        axes[1][col].imshow(
            np.ma.masked_where(~stim.occluded, stim.occluded.astype(float)),
            cmap=matplotlib.colors.ListedColormap([AMBER]),
            alpha=0.9,
            interpolation="nearest",
        )
        axes[1][col].set_title(
            f"half-occlusion: {100 * stim.occlusion_fraction:.1f}% of frame", fontsize=8.5
        )
        for ax in (axes[0][col], axes[1][col]):
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_edgecolor(RULE)
    fig.suptitle(
        "Three stimulus families, in the order they were used. Amber is ground-truth "
        "half-occlusion —\nthe chart has the least of it, because coplanar patches against one "
        "backdrop barely occlude anything.",
        fontsize=8.5,
        color=SLATE,
        y=1.03,
    )
    fig.tight_layout()
    fig.savefig(out / "01_families.png")
    plt.close(fig)


def fig_hallucination(rows, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.2, 4.4))
    xs = np.arange(len(FAMILIES))
    width = 0.36
    for k, matcher in enumerate(("block", "sgbm")):
        vals = [med(rows, f, matcher, "hallucination") for f in FAMILIES]
        bars = ax.bar(
            xs + (k - 0.5) * width,
            vals,
            width=width,
            color=VERM if matcher == "block" else CYAN,
            label=matcher,
        )
        for bar, v in zip(bars, vals, strict=True):
            ax.annotate(
                f"{v:.1%}",
                (bar.get_x() + bar.get_width() / 2, v),
                textcoords="offset points",
                xytext=(0, 3),
                ha="center",
                fontsize=8.5,
            )
    ax.set_xticks(xs)
    ax.set_xticklabels(
        [f"{f}\n(search range {med(rows, f, 'block', 'max_disparity'):.0f} px)" for f in FAMILIES]
    )
    ax.set_ylabel("fraction of half-occlusions answered")
    ax.set_title("Confident answers where no correspondent exists")
    ax.legend()
    ax.grid(axis="y", lw=0.5, alpha=0.5)
    ax.set_axisbelow(True)
    ax.set_ylim(0, 1.05)
    fig.text(
        0.5,
        -0.08,
        "Block matching barely moves across three completely different stimulus families. "
        "SGBM's advantage\nis a property of random dots. Search range is printed because a "
        "wider one gives more chances to find a\nspurious minimum, and is a confound this "
        "comparison cannot remove.",
        ha="center",
        fontsize=8.5,
        color=SLATE,
    )
    fig.savefig(out / "02_hallucination.png")
    plt.close(fig)


def fig_variance_ratio(rows, out: Path) -> None:
    """The spine of the synthesis -- and the figure most able to mislead.

    The chart appears twice on purpose. Under the shared definition its ratio is
    below 1.0, which looks like the same anti-calibration exp004 found on
    photographs and is not: exp003's chart deliberately contains textureless
    patches whose reported variance is 637x the textured level, and pooling those
    into the "matched" baseline swamps it. Under exp003's own textured baseline
    the chart is 4.7x -- correctly directioned, merely too small.

    Plotting only the shared number would manufacture a tidy monotone trend out of
    an artefact of one stimulus's design.
    """
    fig, ax = plt.subplots(figsize=(9.4, 4.8))
    labels = [
        "random dots",
        "rendered chart\n(shared baseline)",
        "rendered chart\n(exp003 baseline)",
        "photographs",
    ]
    vals = [
        med(rows, "random dots", "block", "variance_ratio"),
        med(rows, "rendered chart", "block", "variance_ratio"),
        exp003_ratio(rows),
        med(rows, "photographs", "block", "variance_ratio"),
    ]
    colors = [FAMILY_COLOR["random dots"], "#e0cdae", AMBER, VERM]
    bars = ax.bar(np.arange(len(labels)), vals, color=colors, width=0.58)
    for bar, v in zip(bars, vals, strict=True):
        ax.annotate(
            f"{v:.2f}{TIMES}",
            (bar.get_x() + bar.get_width() / 2, v),
            textcoords="offset points",
            xytext=(0, 4),
            ha="center",
            fontsize=10,
            fontweight="bold",
        )
    ax.axhline(1.0, color=INK, lw=1.2)
    ax.annotate(
        "1.0 — as confident in an occlusion as on a genuine match",
        (-0.45, 1.08),
        fontsize=8,
        color=INK,
        ha="left",
    )
    ax.set_yscale("log")
    ax.set_xticks(np.arange(len(labels)))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel(f"occluded variance / matched variance ({TIMES}, log)")
    ax.set_title("Block matcher: how loudly it doubts itself in a half-occlusion")
    ax.grid(axis="y", lw=0.5, alpha=0.5)
    ax.set_axisbelow(True)
    ax.margins(y=0.3)
    ax.annotate(
        "artefact, not a result — this baseline\nincludes the chart's own deliberately\n"
        f"textureless patches (637{TIMES} the textured level)",
        xy=(1.0, vals[1]),
        xytext=(1.0, vals[1] * 0.30),
        ha="center",
        va="top",
        fontsize=7.5,
        color=SLATE,
        arrowprops={"arrowstyle": "-", "color": FAINT, "lw": 0.8},
    )
    ax.set_ylim(vals[1] * 0.08, None)
    fig.text(
        0.5,
        -0.12,
        "Only on photographs does the ratio genuinely cross below 1.0. exp001 never published "
        "this quantity;\nit is recomputed here with the same code as the other two.",
        ha="center",
        fontsize=8.5,
        color=SLATE,
    )
    fig.savefig(out / "03_variance_ratio.png")
    plt.close(fig)


def fig_contrast_stratified(rows, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(9.0, 4.6))
    groups = ("matched", "occluded_lo", "occluded_hi")
    names = ("matched", "occluded\nlow contrast", "occluded\nHIGH contrast")
    xs = np.arange(len(groups))
    width = 0.26
    for k, family in enumerate(FAMILIES):
        vals = []
        for key in groups:
            per = [
                r[key] / r["matched"]
                for r in rows
                if r["family"] == family and r["matcher"] == "block" and r["matched"] > 0
            ]
            finite = [v for v in per if np.isfinite(v)]
            vals.append(float(np.median(finite)) if finite else np.nan)
        bars = ax.bar(
            xs + (k - 1) * width, vals, width=width, color=FAMILY_COLOR[family], label=family
        )
        for bar, v in zip(bars, vals, strict=True):
            if np.isfinite(v):
                ax.annotate(
                    f"{v:.2f}",
                    (bar.get_x() + bar.get_width() / 2, v),
                    textcoords="offset points",
                    xytext=(0, 3),
                    ha="center",
                    fontsize=7.5,
                )
    ax.axhline(1.0, color=INK, lw=1.0)
    ax.set_yscale("log")
    ax.set_xticks(xs)
    ax.set_xticklabels(names)
    ax.set_ylabel(f"variance relative to matched ({TIMES}, log)")
    ax.set_title("EXPLORATORY — the exp004 contrast split, applied backwards")
    ax.legend(ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    ax.grid(axis="y", lw=0.5, alpha=0.5)
    ax.set_axisbelow(True)
    ax.margins(y=0.25)
    ax.annotate(
        "EXPLORATORY: post-hoc, no falsifier,\non data whose results are known",
        xy=(0.985, 0.96),
        xycoords="axes fraction",
        ha="right",
        va="top",
        fontsize=8,
        color=VERM,
        fontweight="bold",
        bbox={"facecolor": "#f7ddd6", "edgecolor": VERM, "boxstyle": "round,pad=0.4", "lw": 0.8},
    )
    fig.savefig(out / "04_contrast_stratified.png")
    plt.close(fig)


def fig_coverage_error(rows, out: Path) -> None:
    fig, (a, b) = plt.subplots(1, 2, figsize=(12.2, 4.2))
    xs = np.arange(len(FAMILIES))
    width = 0.36
    for k, matcher in enumerate(("block", "sgbm")):
        a.bar(
            xs + (k - 0.5) * width,
            [med(rows, f, matcher, "coverage") for f in FAMILIES],
            width=width,
            color=VERM if matcher == "block" else CYAN,
            label=matcher,
        )
        b.bar(
            xs + (k - 0.5) * width,
            [med(rows, f, matcher, "bad_rate") for f in FAMILIES],
            width=width,
            color=VERM if matcher == "block" else CYAN,
            label=matcher,
        )
    for ax, title, ylabel in (
        (a, "Coverage on pixels that do have a correspondent", "fraction answered"),
        (b, "bad-2.0 on those answers", "fraction wrong by > 2 px"),
    ):
        ax.set_xticks(xs)
        ax.set_xticklabels(FAMILIES)
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.legend()
        ax.grid(axis="y", lw=0.5, alpha=0.5)
        ax.set_axisbelow(True)
    fig.text(
        0.5,
        -0.06,
        "Difficulty is not constant across families and this does not try to make it so: "
        "bad-2.0 is a fixed\npixel threshold on stimuli with different disparity ranges. "
        "Read the trend, not the level.",
        ha="center",
        fontsize=8.5,
        color=SLATE,
    )
    fig.tight_layout()
    fig.savefig(out / "05_coverage_error.png")
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--chart", type=Path, default=Path("results/stimuli/chart"))
    ap.add_argument("--corpus", type=Path, default=None)
    ap.add_argument("--downsample", type=int, default=3)
    ap.add_argument("--out", type=Path, default=Path("slides/comparative_stimulus_families"))
    args = ap.parse_args(argv)

    corpus = args.corpus or Path(
        os.environ.get("ACTIVESTEREO_DATA_ROOT", "~/datasets/middlebury2014")
    ).expanduser()
    photo_scenes = [
        "Motorcycle", "Piano", "Pipes", "Playroom",
        "Playtable", "Recycle", "Shelves", "Vintage",
    ]

    figures = args.out / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    _style()

    rows = (
        score_random_dots()
        + score_rendered_chart(args.chart)
        + score_photographs(corpus, photo_scenes, args.downsample)
    )
    cross_check(rows)

    fig_families(args.chart, corpus, args.downsample, figures)
    fig_hallucination(rows, figures)
    fig_variance_ratio(rows, figures)
    fig_contrast_stratified(rows, figures)
    fig_coverage_error(rows, figures)

    summary = {
        "families": {
            family: {
                matcher: {
                    key: med(rows, family, matcher, key)
                    for key in (
                        "coverage",
                        "hallucination",
                        "bad_rate",
                        "variance_ratio",
                        "max_disparity",
                        "n_occluded",
                    )
                }
                for matcher in ("block", "sgbm")
            }
            for family in FAMILIES
        },
        "published_cross_check": PUBLISHED,
        "note": (
            "Synthesis, not an experiment: no hypotheses, no falsifiers. The contrast "
            "stratification applied to random dots and renders is exploratory and needs "
            "its own pre-registered test."
        ),
        "rows": rows,
    }
    (args.out / "data.json").write_text(json.dumps(summary, indent=2))

    print("\n--- medians by family (block matcher) ---")
    for family in FAMILIES:
        print(
            f"  {family:<15} coverage {med(rows, family, 'block', 'coverage'):.3f}  "
            f"halluc {med(rows, family, 'block', 'hallucination'):.3f}  "
            f"var_ratio {med(rows, family, 'block', 'variance_ratio'):.3f}  "
            f"bad2 {med(rows, family, 'block', 'bad_rate'):.3f}"
        )
    print(f"\nwrote {figures} and {args.out / 'data.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
