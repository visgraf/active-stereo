"""exp005 -- does the energy decoder's profile variance escape the anti-calibration?

Hypotheses, falsifiers, the two-stage protocol and threats live in
``config.yaml`` and issue #12. This runner is deliberately thin: the decoder is
``inference.EnergyDecoder``, the metrics are ``activestereo.metrics``.

Stage A (RDS + synthetic only)::

    python -m experiments.exp005_energy_decoder.run --stage a \
        --config experiments/exp005_energy_decoder/config.yaml

Stage B refuses to run until ``stage_b_unlocked`` is true in the config, which
is flipped in the same commit as the readout-constants comment on issue #12 --
the gate that prevents an undeclared peek at Middlebury.
"""

from __future__ import annotations

import argparse
import json
import resource
import time
from pathlib import Path

import numpy as np

from activestereo.inference import BlockMatcher, EnergyDecoder
from activestereo.metrics import local_contrast, score_all
from activestereo.scenes import RandomDotStereogram, disk
from activestereo.scenes.middlebury import MiddleburyScene
from activestereo.types import Estimate, StereoRig
from activestereo.utils import RunContext, load_config


def _median(a: np.ndarray) -> float:
    finite = np.asarray(a)[np.isfinite(a)]
    return float(np.median(finite)) if finite.size else float("nan")


def median_abs_error(stim, est: Estimate) -> float:
    """Median |Δd| in px over answered scorable pixels -- H1a/H3's error metric."""
    err = np.abs(est.value - stim.disparity)
    graded = stim.scorable & np.isfinite(err)
    return _median(err[graded])


def decoder_from(cfg: dict, max_disparity: int) -> EnergyDecoder:
    r = cfg["readout"]
    return EnergyDecoder(
        max_disparity=max_disparity,
        flatness=r["flatness"],
        centroid_halfwidth=r["centroid_halfwidth"],
    )


# --- Stage A ----------------------------------------------------------------


def stage_a(cfg: dict) -> dict:
    a = cfg["stage_a"]
    rds, rig_cfg = a["rds"], a["rig"]
    rig = StereoRig(
        baseline=rig_cfg["baseline"],
        focal_px=rig_cfg["focal_px"],
        vergence=np.deg2rad(rig_cfg["vergence_deg"]),
    )
    scene = RandomDotStereogram(
        disk,
        shape=tuple(rds["shape"]),
        near=rds["near"],
        far=rds["far"],
        radius=rds["radius"],
        dot_size=rds["dot_size"],
        density=rds["density"],
    )
    matchers = {
        "energy": decoder_from(cfg, rds["max_disparity"]),
        "block": BlockMatcher(max_disparity=rds["max_disparity"], window=rds["window"]),
    }

    per_seed: dict[str, list[dict]] = {name: [] for name in matchers}
    for seed in rds["seeds"]:
        stim = scene.render(rig, np.random.default_rng(seed))
        contrast = local_contrast(stim.left, rds["window"])
        for name, matcher in matchers.items():
            est = matcher.match(stim.left, stim.right)
            per_seed[name].append(
                {
                    "seed": seed,
                    "median_abs_err_px": median_abs_error(stim, est),
                    **score_all(stim, est, contrast=contrast),
                }
            )
        print(f"[exp005/A] scored seed {seed}")

    h1a = {
        name: {
            key: _median(np.array([r[key] for r in rows]))
            for key in ("median_abs_err_px", "coverage", "hallucination", "bad_rate",
                        "variance_ratio")
        }
        for name, rows in per_seed.items()
    }

    # H1b: exp002's stimulus, verbatim from its run.py -- one shared texture per
    # seed; gain 1.0 only (the sweep belongs to exp002; the invariance is pinned
    # bit-exactly in tests/unit/test_energy_decoder.py).
    s2 = a["exp002_stimulus"]
    shape, d0, noise = tuple(s2["shape"]), s2["disparity"], s2["noise"]
    dec = decoder_from(cfg, s2["max_disparity"])
    within: list[float] = []
    for seed in s2["seeds"]:
        rng = np.random.default_rng(seed)
        base = rng.random((shape[0], shape[1] + d0))
        left = base[:, : shape[1]] + rng.normal(0, noise, shape)
        right = base[:, d0 : d0 + shape[1]] + rng.normal(0, noise, shape)
        est = dec.match(left, right)
        ok = np.isfinite(est.value)
        within.append(float(np.mean(np.abs(est.value[ok] - d0) <= 1.0)) if ok.any() else 0.0)
    h1b_fraction = float(np.median(within))

    ratio = h1a["energy"]["median_abs_err_px"] / h1a["block"]["median_abs_err_px"]
    verdicts = {
        "H1a_err_ratio_vs_block": float(ratio),
        "H1a_err_within_2x_block": bool(np.isfinite(ratio) and ratio <= 2.0),
        "H1a_coverage": h1a["energy"]["coverage"],
        "H1a_coverage_at_least_090": bool(h1a["energy"]["coverage"] >= 0.90),
        "H1a_survives": bool(
            np.isfinite(ratio) and ratio <= 2.0 and h1a["energy"]["coverage"] >= 0.90
        ),
        "H1b_within_1px_fraction": h1b_fraction,
        "H1b_survives_above_argmax": bool(h1b_fraction > 0.58),
        "H1b_resolves_issue1_option_a": bool(h1b_fraction >= 0.95),
        "H1b_per_seed": within,
    }
    return {"h1a_medians": h1a, "h1a_per_seed": per_seed, "verdicts": verdicts}


# --- Stage B ----------------------------------------------------------------


def stage_b(cfg: dict) -> dict:
    b = cfg["stage_b"]
    if not b.get("stage_b_unlocked", False):
        raise SystemExit(
            "Stage B is locked. The readout constants and Stage A numbers must "
            "be posted to issue #12 BEFORE the decoder reads any Middlebury "
            "scene; flip stage_b_unlocked in config.yaml in the same commit as "
            "that comment, so the order is auditable. This lock exists because "
            "this project has already had two undeclared peeks (see issue #6)."
        )

    import os

    root = Path(os.environ.get("ACTIVESTEREO_DATA_ROOT", "~/datasets/middlebury2014")).expanduser()
    scenes = list(b["held_out"]) + list(b["seen"])
    per_scene: dict[str, dict] = {}

    for name in scenes:
        t0 = time.time()
        scene = MiddleburyScene(root / f"{name}-perfect", downsample=b["downsample"])
        if scene.ndisp > b["max_disparity_ceiling"]:
            raise SystemExit(
                f"{name}: ndisp={scene.ndisp} above ceiling "
                f"{b['max_disparity_ceiling']}; refusing to truncate (see exp004)."
            )
        dec = decoder_from(cfg, scene.ndisp)
        base = scene.stimulus("im1")
        contrast = local_contrast(base.left, b["contrast_window"])

        cells: dict[str, dict] = {}
        for variant in b["right_variants"]:
            stim = scene.stimulus(variant)
            est = dec.match(stim.left, stim.right)
            cells[variant] = {
                "median_abs_err_px": median_abs_error(stim, est),
                **score_all(stim, est, contrast=contrast),
            }
        per_scene[name] = {
            "ndisp": scene.ndisp,
            "seconds": round(time.time() - t0, 1),
            "by_variant": cells,
        }
        print(f"[exp005/B] scored {name:<12} ndisp={scene.ndisp}  {per_scene[name]['seconds']}s")

    held = list(b["held_out"])

    def held_med(variant: str, key: str) -> float:
        return _median(np.array([per_scene[s]["by_variant"][variant][key] for s in held]))

    hi_ratios = [
        per_scene[s]["by_variant"]["im1"]["occluded_hi"]
        / per_scene[s]["by_variant"]["im1"]["matched"]
        if per_scene[s]["by_variant"]["im1"]["matched"] > 0
        else float("nan")
        for s in held
    ]
    halluc = held_med("im1", "hallucination")
    hi_ratio_med = _median(np.array(hi_ratios))

    mults, drops = [], []
    for s in held:
        v1 = per_scene[s]["by_variant"]["im1"]
        ve = per_scene[s]["by_variant"]["im1E"]
        mults.append(
            ve["median_abs_err_px"] / v1["median_abs_err_px"]
            if v1["median_abs_err_px"] > 0
            else float("nan")
        )
        drops.append(v1["coverage"] - ve["coverage"])
    mult_med, drop_med = _median(np.array(mults)), _median(np.array(drops))

    verdicts = {
        "H2_hallucination_median": halluc,
        "H2_hi_contrast_ratio_median": hi_ratio_med,
        "H2_hi_contrast_ratios_per_scene": [float(r) for r in hi_ratios],
        "H2_falsified": bool(halluc >= 0.40 and hi_ratio_med < 1.0),
        "H2_note": (
            "surviving does not establish adequate calibration, only "
            "non-inversion; declining (hallucination < 0.40) is the safe "
            "alternative outcome, not a pass on calibration"
        ),
        "H3_error_multiplier_im1E_median": mult_med,
        "H3_coverage_drop_im1E_median": drop_med,
        "H3_per_scene_multipliers": [float(m) for m in mults],
        "H3_per_scene_coverage_drops": [float(d) for d in drops],
        "H3_falsified": bool(
            (np.isfinite(mult_med) and mult_med >= 4.0) or drop_med > 0.25
        ),
    }

    context = {}
    exp004 = Path(b["exp004_run"]) / "summary.json"
    if exp004.exists():
        prior = json.loads(exp004.read_text())
        context = {
            "exp004_run": prior.get("per_scene", {}) and b["exp004_run"],
            "block_sgbm_heldout_im1": prior["by_matcher_heldout"],
        }

    peak_rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1 << 20)
    return {
        "per_scene": per_scene,
        "verdicts": verdicts,
        "exp004_context": context,
        "peak_rss_mb": round(peak_rss_mb, 1),
    }


def run(config_path: Path, stage: str) -> Path:
    cfg = load_config(config_path)
    ctx = RunContext(tag=f"exp005{stage}", seed=cfg["seed"], config=cfg)
    payload = {"stage": stage, "readout": cfg["readout"]}
    payload |= stage_a(cfg) if stage == "a" else stage_b(cfg)
    ctx.path("summary.json").write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload.get("verdicts", {}), indent=2))
    print(f"\nrun-id: {ctx.run_id}\nresults: {ctx.dir}")
    return ctx.dir


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--stage", choices=["a", "b"], required=True)
    run(ap.parse_args().config, ap.parse_args().stage)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
