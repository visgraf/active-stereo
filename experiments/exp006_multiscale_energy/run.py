"""exp006 -- the multi-scale energy bank, validity-gated (issue #13).

Stage A evaluates the declared grid on the dev set only (RDS, chart renders,
and the two burned photographs), selects a configuration by the declared
criterion, and stops. The selection goes to issue #13; Stage B unlocks in the
accompanying commit and runs the eight held-out scenes once.

    python -m experiments.exp006_multiscale_energy.run --stage a \
        --config experiments/exp006_multiscale_energy/config.yaml
"""

from __future__ import annotations

import argparse
import json
import resource
import time
from pathlib import Path

import numpy as np

from activestereo.encoding import MultiScaleEnergyEncoder
from activestereo.inference import BlockMatcher, EnergyDecoder
from activestereo.metrics import local_contrast, score_all
from activestereo.scenes import RandomDotStereogram, disk
from activestereo.scenes.blender import BlenderRenderScene
from activestereo.scenes.middlebury import MiddleburyScene
from activestereo.types import Estimate, StereoRig
from activestereo.utils import RunContext, load_config


def _median(a) -> float:
    finite = np.asarray(a, dtype=float)
    finite = finite[np.isfinite(finite)]
    return float(np.median(finite)) if finite.size else float("nan")


def median_abs_error(stim, est: Estimate) -> float:
    err = np.abs(est.value - stim.disparity)
    return _median(err[stim.scorable & np.isfinite(err)])


def build_decoder(cfg: dict, bank_max: int, spec: dict) -> EnergyDecoder:
    encoder = MultiScaleEnergyEncoder(
        np.arange(0, bank_max + 1, dtype=float),
        scales=[tuple(s) for s in spec["scales"]],
        combine=spec["combine"],
        floor=spec["floor"],
    )
    return EnergyDecoder(
        encoder=encoder,
        flatness=cfg["readout"]["flatness"],
        centroid_halfwidth=cfg["readout"]["centroid_halfwidth"],
    )


def chance_floor(stim, bank_max: int, rng: np.random.Generator) -> float:
    """Median |Δd| a uniform guesser over the answerable bank achieves."""
    truth = stim.disparity[stim.scorable]
    guess = rng.uniform(2, bank_max - 2, size=truth.size)
    return _median(np.abs(guess - truth))


# --- Stage A ----------------------------------------------------------------


def grid_specs(cfg: dict) -> list[dict]:
    g = cfg["grid"]
    return [
        {"scales": scales, "combine": combine, "floor": floor}
        for scales in g["scale_sets"]
        for combine in g["combine"]
        for floor in g["floor"]
    ]


def stage_a(cfg: dict) -> dict:
    a = cfg["stage_a"]
    rig = StereoRig(
        baseline=a["rig"]["baseline"],
        focal_px=a["rig"]["focal_px"],
        vergence=np.deg2rad(a["rig"]["vergence_deg"]),
    )
    rds_cfg = a["rds"]
    scene = RandomDotStereogram(
        disk,
        shape=tuple(rds_cfg["shape"]),
        near=rds_cfg["near"],
        far=rds_cfg["far"],
        radius=rds_cfg["radius"],
        dot_size=rds_cfg["dot_size"],
        density=rds_cfg["density"],
    )
    block = BlockMatcher(max_disparity=rds_cfg["max_disparity"], window=rds_cfg["window"])
    rds_stims = [scene.render(rig, np.random.default_rng(s)) for s in rds_cfg["seeds"]]
    block_err = _median([median_abs_error(s, block.match(s.left, s.right)) for s in rds_stims])

    dev_photo_stims = {}
    for name in a["dev_photos"]:
        import os

        root = Path(
            os.environ.get("ACTIVESTEREO_DATA_ROOT", "~/datasets/middlebury2014")
        ).expanduser()
        sc = MiddleburyScene(root / f"{name}-perfect", downsample=a["downsample"])
        dev_photo_stims[name] = (sc.stimulus("im1"), sc.ndisp)

    chart_stims = [
        BlenderRenderScene(Path(a["charts_root"]) / c).stimulus() for c in a["chart_conditions"]
    ]

    # --- grid evaluation, declared criterion ---------------------------------
    rows = []
    for spec in grid_specs(cfg):
        t0 = time.time()
        rds_errs = []
        for stim in rds_stims:
            dec = build_decoder(cfg, rds_cfg["max_disparity"], spec)
            rds_errs.append(median_abs_error(stim, dec.match(stim.left, stim.right)))
        margins = []
        for stim, ndisp in dev_photo_stims.values():
            dec = build_decoder(cfg, ndisp, spec)
            est = dec.match(stim.left, stim.right)
            err = median_abs_error(stim, est)
            floor = chance_floor(stim, ndisp, np.random.default_rng(0))
            margins.append(floor / err if err > 0 else float("inf"))
        chart_errs = [
            median_abs_error(stim, build_decoder(cfg, 48, spec).match(stim.left, stim.right))
            for stim in chart_stims
        ]
        row = {
            **spec,
            "photo_margin_median": _median(margins),
            "rds_err_ratio_vs_block": _median(rds_errs) / block_err,
            "chart_err_median": _median(chart_errs),
            "seconds": round(time.time() - t0, 1),
        }
        rows.append(row)
        print(
            f"[exp006/A] scales={row['scales']} {row['combine']:<7} floor={row['floor']:g} "
            f"margin={row['photo_margin_median']:.2f} rds_ratio={row['rds_err_ratio_vs_block']:.2f}"
        )

    # Declared selection: maximise photo margin, tiebreak RDS ratio.
    selected = max(rows, key=lambda r: (r["photo_margin_median"], -r["rds_err_ratio_vs_block"]))
    spec = {k: selected[k] for k in ("scales", "combine", "floor")}
    print(f"[exp006/A] selected: {spec}")

    # --- selected config: full RDS seeds + H3a gain sweep --------------------
    final: dict[str, list[float]] = {"energy_err": [], "energy_cov": [], "block_err": []}
    for seed in rds_cfg["final_seeds"]:
        stim = scene.render(rig, np.random.default_rng(seed))
        dec = build_decoder(cfg, rds_cfg["max_disparity"], spec)
        est = dec.match(stim.left, stim.right)
        final["energy_err"].append(median_abs_error(stim, est))
        final["energy_cov"].append(float(np.isfinite(est.value)[stim.scorable].mean()))
        final["block_err"].append(median_abs_error(stim, block.match(stim.left, stim.right)))
    energy_err = _median(final["energy_err"])
    block_err5 = _median(final["block_err"])
    rds_valid = bool(energy_err <= 2.0 * block_err5)

    sweep: dict[str, dict[str, float]] = {}
    stim0 = rds_stims[0]
    dec = build_decoder(cfg, rds_cfg["max_disparity"], spec)
    base_e = median_abs_error(stim0, dec.match(stim0.left, stim0.right))
    base_b = median_abs_error(stim0, block.match(stim0.left, stim0.right))
    for gain in a["gain_sweep"]:
        right = stim0.right * gain
        sweep[f"{gain:g}"] = {
            "energy_multiplier": median_abs_error(stim0, dec.match(stim0.left, right)) / base_e,
            "block_multiplier": median_abs_error(stim0, block.match(stim0.left, right)) / base_b,
        }
    worst = max(v["energy_multiplier"] for v in sweep.values())

    verdicts = {
        "selected": spec,
        "selection_table": rows,
        "rds_energy_err_px": energy_err,
        "rds_block_err_px": block_err5,
        "rds_err_ratio": energy_err / block_err5,
        "rds_coverage": _median(final["energy_cov"]),
        "rds_valid_regime_for_H3a": rds_valid,
        "H3a_gain_sweep": sweep,
        "H3a_worst_energy_multiplier": float(worst),
        "H3a_falsified": bool(rds_valid and worst > 1.1),
        "H3a_void": bool(not rds_valid),
    }
    return {"verdicts": verdicts}


# --- Stage B ----------------------------------------------------------------


def stage_b(cfg: dict) -> dict:
    b = cfg["stage_b"]
    if not b.get("stage_b_unlocked", False):
        raise SystemExit(
            "Stage B is locked. Post the selected configuration and Stage A "
            "numbers to issue #13, then flip stage_b_unlocked and write the "
            "selection into stage_b.selected in the SAME commit."
        )
    spec = b.get("selected")
    if not spec:
        raise SystemExit("stage_b.selected is null -- the gate commit must write it.")

    import os

    root = Path(os.environ.get("ACTIVESTEREO_DATA_ROOT", "~/datasets/middlebury2014")).expanduser()
    floor_rng = np.random.default_rng(b["chance_floor_seed"])

    per_scene: dict[str, dict] = {}
    for name in b["held_out"]:
        t0 = time.time()
        scene = MiddleburyScene(root / f"{name}-perfect", downsample=b["downsample"])
        if scene.ndisp > b["max_disparity_ceiling"]:
            raise SystemExit(f"{name}: ndisp={scene.ndisp} above ceiling; refusing to truncate.")
        dec = build_decoder(cfg, scene.ndisp, spec)
        base = scene.stimulus("im1")
        contrast = local_contrast(base.left, b["contrast_window"])
        floor = chance_floor(base, scene.ndisp, floor_rng)

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
            "chance_floor_px": floor,
            "floor_margin": cells["im1"]["median_abs_err_px"] / floor,
            "seconds": round(time.time() - t0, 1),
            "by_variant": cells,
        }
        print(
            f"[exp006/B] {name:<12} err={cells['im1']['median_abs_err_px']:.2f}px "
            f"floor={floor:.1f}px cov={cells['im1']['coverage']:.2f} "
            f"({per_scene[name]['seconds']}s)"
        )

    held = list(b["held_out"])

    def med(variant: str, key: str) -> float:
        return _median([per_scene[s]["by_variant"][variant][key] for s in held])

    v0_margin = _median([per_scene[s]["floor_margin"] for s in held])
    v0_cov = med("im1", "coverage")
    v0_pass = bool(v0_margin <= 0.2 and v0_cov >= 0.50)

    err_med = med("im1", "median_abs_err_px")
    h1_falsified = bool(err_med > 3.0 or v0_cov < 0.50)

    hi_ratios = [
        per_scene[s]["by_variant"]["im1"]["occluded_hi"]
        / per_scene[s]["by_variant"]["im1"]["matched"]
        if per_scene[s]["by_variant"]["im1"]["matched"] > 0
        else float("nan")
        for s in held
    ]
    halluc = med("im1", "hallucination")
    hi_med = _median(hi_ratios)

    mults, drops = [], []
    for s in held:
        v1, ve = (per_scene[s]["by_variant"][k] for k in ("im1", "im1E"))
        mults.append(
            ve["median_abs_err_px"] / v1["median_abs_err_px"]
            if v1["median_abs_err_px"] > 0
            else float("nan")
        )
        drops.append(v1["coverage"] - ve["coverage"])

    verdicts: dict = {
        "V0_floor_margin_median": v0_margin,
        "V0_coverage_median": v0_cov,
        "V0_pass": v0_pass,
        "H1_err_median_px": err_med,
        "H1_falsified": h1_falsified,
    }
    if v0_pass:
        verdicts |= {
            "H2_hallucination_median": halluc,
            "H2_hi_contrast_ratio_median": hi_med,
            "H2_hi_contrast_ratios_per_scene": [float(r) for r in hi_ratios],
            "H2_falsified": bool(halluc >= 0.40 and hi_med < 1.0),
            "H3b_error_multiplier_im1E_median": _median(mults),
            "H3b_coverage_drop_im1E_median": _median(drops),
            "H3b_falsified": bool(
                (np.isfinite(_median(mults)) and _median(mults) >= 2.0) or _median(drops) > 0.15
            ),
        }
    else:
        verdicts |= {
            "H2": "VOID -- V0 failed; calibration is untestable at the chance floor",
            "H3b": "VOID -- V0 failed",
            "raw_H2_hi_contrast_ratio_median": hi_med,
            "raw_H3b_error_multiplier": _median(mults),
        }

    context: dict = {}
    for key, run_dir in (("exp004", b["exp004_run"]), ("exp005", b["exp005_run"])):
        path = Path(run_dir) / "summary.json"
        if path.exists():
            context[key] = run_dir
    peak_rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1 << 20)
    return {
        "per_scene": per_scene,
        "verdicts": verdicts,
        "pinned_context_runs": context,
        "peak_rss_mb": round(peak_rss_mb, 1),
    }


def run(config_path: Path, stage: str) -> Path:
    cfg = load_config(config_path)
    ctx = RunContext(tag=f"exp006{stage}", seed=cfg["seed"], config=cfg)
    payload = {"stage": stage, "readout": cfg["readout"]}
    payload |= stage_a(cfg) if stage == "a" else stage_b(cfg)
    ctx.path("summary.json").write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload["verdicts"], indent=2, default=str)[:4000])
    print(f"\nrun-id: {ctx.run_id}\nresults: {ctx.dir}")
    return ctx.dir


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--stage", choices=["a", "b"], required=True)
    args = ap.parse_args()
    run(args.config, args.stage)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
