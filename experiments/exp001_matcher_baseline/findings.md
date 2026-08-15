# exp001 — Block matching vs SGBM under foveal confinement

**Issue:** #1
**Status:** first real result; hypothesis provisionally supported, with caveats

## Hypothesis

With the ADR-0003 foveal confinement term active, SGBM achieves lower foveal
depth error than block matching at equal disparity range, and hallucinates less
in half-occluded regions.

## Acceptance criteria

Median absolute foveal depth error lower for SGBM by a margin exceeding the
seed-to-seed spread across 5 seeds, **and** a lower hallucination rate in
ground-truth occlusions.

## Runs

| Run ID | SHA | Scene | Result |
|---|---|---|---|
| `exp001-20260815T211624` | (pre-commit) | `rds_disk`, 240×320, dot 2, 5 seeds | Both criteria met |

| Matcher | Foveal MAE (m) | Spread | Coverage | Hallucination |
|---|---|---|---|---|
| block `d48_w7` | 1.27e-3 | 1.24e-5 | 0.993 | **0.796** |
| sgbm `d48_b7`  | 0.0     | 0.0     | 0.877 | **0.090** |

## Findings

Both criteria are met, but the *interesting* number is not the one the hypothesis
was about. Depth error separates the matchers by a margin that is real but tiny
in absolute terms (~1 mm at ~1 m). The hallucination rate separates them by
almost an order of magnitude: **block matching reports confident depth for 80% of
ground-truth half-occluded pixels; SGBM for 9%.**

That is the operationally important difference. A matcher that returns `nan` in a
half-occlusion is telling the truth. A matcher that returns a number is injecting
a confident false measurement into MLE fusion at L4, where it is weighted by a
curvature-derived variance that has no idea it is wrong. Block matching's near-
perfect *coverage* (0.993) is not a virtue here; it is the symptom.

This reframes the case for SGBM. It is not mainly that it matches better — it is
that it declines better.

## Threats to validity

- **SGBM's foveal MAE of exactly 0.0 across all five seeds is suspicious.** The
  `disk` stimulus is piecewise-constant in depth, so the task is unusually easy:
  two integer disparities, no gradient, no curvature. Rerun on `slanted_plane`
  and `corrugated` before treating this as a general result. A number that is
  exactly zero usually means the test was too easy, not that the method is exact.
- **The ADR-0003 coefficient is still uncalibrated** (1e-4). It sets how
  aggressively the periphery is discounted, and the foveal-error comparison is
  directly sensitive to it. Report a sweep, not a point.
- **SGBM's variance is a constant**, not a real posterior width. The two matchers
  are therefore not equally honest about their own uncertainty, which is exactly
  what the fusion at L4 consumes. Any downstream fusion comparison is unfair
  until L3 grows belief propagation.
- **Fronto-parallel-friendly stimulus.** Block matching's square window assumes
  constant disparity across itself, which `disk` satisfies almost everywhere. The
  integration tests show its p90 error is ~4× worse on `slanted_plane`. Using
  only `disk` flatters block matching.

## Next

1. Rerun across all four depth maps and report per-stimulus, not pooled.
2. Sweep the ADR-0003 coefficient over ~2 decades.
3. Add a matched-vs-occluded breakdown to the plot in `scripts/demo_active_stereo.py`.
