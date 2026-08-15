---
description: Audit a diff or module against CLAUDE.md section 3
---

Audit $ARGUMENTS against the invariants in CLAUDE.md §3 and the three closures.

Check each, and report per-file with line references:

- **Units and frames** — does every public function document them? Any implicit
  degrees, any `(x, y)` where the repo uses `(row, col)`?
- **Invalid representation** — any `0`, `-1`, or other sentinel where `nan` is
  required? Any place a sentinel could be mistaken for a real measurement
  downstream?
- **Spatial mixing** — any blur, filter, resample, or downsample that touches a
  field with invalid entries *without* masking first? (ADR-0002)
- **Uncertainty** — any estimator returning a bare point estimate? (ADR-0005)
- **Determinism** — any use of the global `np.random` state instead of an
  injected `Generator`?
- **Scaling closure** — anything below L4 returning metres?
- **Control-regime closure** — is L5 re-deriving depth rather than consuming it?
- **Import direction** — does `src` import from `experiments`?

Report violations plainly, worst first. Say "no violations found" if that is the
case rather than manufacturing findings.
