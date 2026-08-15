"""exp002 -- contrast-invariant tuning of the migrated energy-model encoder.

Hypothesis and acceptance criteria live in ``config.yaml`` and in issue #1.
This runner is deliberately thin: all reusable logic belongs in ``src``.

Usage
-----
    python -m experiments.exp002_energy_model_validation.run \
        --config experiments/exp002_energy_model_validation/config.yaml
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from activestereo.encoding import GaborEnergyEncoder
from activestereo.utils import RunContext, load_config


def run(config_path: Path) -> Path:
    cfg = load_config(config_path)
    ctx = RunContext(
        tag=cfg.get("experiment", {}).get("tag", "exp002"), seed=cfg["seed"], config=cfg
    )

    enc_cfg = cfg["encoding"]
    bank_cfg = enc_cfg["bank"]
    disparities = np.arange(
        bank_cfg["center"] - bank_cfg["half_width"],
        bank_cfg["center"] + bank_cfg["half_width"] + bank_cfg["step"],
        bank_cfg["step"],
    )
    encoder = GaborEnergyEncoder(
        disparities, frequency=enc_cfg["frequency"], sigma=enc_cfg["sigma"]
    )

    stim = enc_cfg["stimulus"]
    shape = tuple(stim["shape"])
    d0 = stim["disparity"]
    noise = stim["noise"]
    gains = enc_cfg["gain_sweep"]
    step = bank_cfg["step"]

    baseline_within_tolerance: list[float] = []
    per_seed_gain_means: list[list[float]] = []

    for seed in cfg["seeds"]:
        rng = np.random.default_rng(seed)
        # One shared random-dot pattern per seed: only the right eye's gain
        # varies across the sweep, isolating the effect of contrast alone
        # rather than confounding it with a fresh texture draw per condition.
        base = rng.random((shape[0], shape[1] + d0))
        left = base[:, : shape[1]] + rng.normal(0, noise, shape)

        gain_means = []
        for gain in gains:
            right = gain * base[:, d0 : d0 + shape[1]] + rng.normal(0, noise, shape)
            resp = encoder.encode(left, right)
            valid = np.all(np.isfinite(resp), axis=0)
            peak = encoder.disparities[np.argmax(resp, axis=0)]
            gain_means.append(float(np.mean(peak[valid])) if valid.any() else float("nan"))
            if gain == 1.0:
                err = np.abs(peak[valid] - d0)
                frac_within = float(np.mean(err <= step)) if valid.any() else 0.0
                baseline_within_tolerance.append(frac_within)
        per_seed_gain_means.append(gain_means)

    gain_means_arr = np.array(per_seed_gain_means)  # (n_seeds, n_gains)
    drift_per_seed = gain_means_arr.max(axis=1) - gain_means_arr.min(axis=1)

    summary = {
        "baseline_within_tolerance_fraction_median": float(np.median(baseline_within_tolerance)),
        "baseline_within_tolerance_fraction_per_seed": baseline_within_tolerance,
        "gain_drift_px_median": float(np.median(drift_per_seed)),
        "gain_drift_px_per_seed": drift_per_seed.tolist(),
        "gain_means_per_seed": gain_means_arr.tolist(),
        "gains": gains,
        "n_seeds": len(cfg["seeds"]),
    }
    acceptance = {
        "falsifier_1_peak_near_d0": summary["baseline_within_tolerance_fraction_median"] >= 0.95,
        "falsifier_2_gain_invariant": summary["gain_drift_px_median"] <= 0.5,
    }
    summary["acceptance"] = acceptance
    summary["hypothesis_survives"] = all(acceptance.values())

    ctx.path("summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    print(f"\nrun-id: {ctx.run_id}\nresults: {ctx.dir}")
    print(f"\nHypothesis survives: {summary['hypothesis_survives']}")
    return ctx.dir


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, required=True)
    run(ap.parse_args().config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
