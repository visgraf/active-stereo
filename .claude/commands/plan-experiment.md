---
description: Draft a falsifiable experiment plan before any code is written
---

Draft an experiment plan for: $ARGUMENTS

Read `docs/decisions/` for prior decisions that constrain this, and
`experiments/README.md` for the required structure. Do **not** write code yet.

Produce:

1. **Hypothesis** — a claim that could turn out false. Not "try X and see".
2. **What would falsify it** — specific and numeric.
3. **Acceptance criteria** — the measurement, the threshold, the number of seeds.
4. **Confounds and threats to validity** — write these now, before either of us
   has a stake in the outcome. Include at least one way a *positive* result could
   be spurious.
5. **Which layers are touched**, and whether any closure is at risk.
6. **What already exists** in `src/` versus what must be built.
7. **The cheapest version of this experiment** that would still be informative.

If the hypothesis as stated is not falsifiable, say so and propose a sharper one
instead of proceeding.
