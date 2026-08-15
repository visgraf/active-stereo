# exp001 — Block matching vs SGBM under foveal confinement

**Issue:** none filed (this reference predates real issue tracking; #1 was later filed for exp002)
**Status:** scaffolded, not yet run on a real scene

## Hypothesis

With the ADR-0003 foveal confinement term active, SGBM achieves lower foveal
depth error than block matching at equal disparity range. Without the term, the
difference is not detectable.

## Acceptance criteria

Median absolute depth error inside the foveal radius is lower for SGBM by a
margin exceeding the seed-to-seed spread across 5 seeds.

## Runs

| Run ID | SHA | Config | Result | Notes |
|---|---|---|---|---|
| _pending_ | | | | Awaiting Blender scene migration (#2) |

## Findings

_Nothing yet. The current `synthesize()` is a fronto-parallel placeholder: it has
no depth variation, so it cannot discriminate the matchers. Any number produced
before #2 lands is measuring the placeholder, not the hypothesis._

## Threats to validity

- The placeholder scene has constant depth; the foveal/peripheral distinction is
  therefore vacuous until a slanted or structured scene is used.
- The ADR-0003 coefficient is uncalibrated. Its value sets how aggressively the
  periphery is discounted, which is exactly the quantity this experiment is
  sensitive to. Calibrate first, or report a sweep.
- SGBM's variance is currently a constant, not a real posterior width. Comparing
  fused results across matchers with differently-honest variances is not yet a
  fair comparison.
