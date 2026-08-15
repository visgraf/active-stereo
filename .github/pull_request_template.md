## What and why

<!-- One paragraph. Link the issue. -->

Closes #

## Layer(s) touched

- [ ] L1 geometry  - [ ] L2 encoding  - [ ] L3 inference
- [ ] L4 scaling   - [ ] L5 control   - [ ] L6 policy
- [ ] docs / experiments / infra

## Checklist

- [ ] `pytest -q` passes locally
- [ ] New behaviour has a test; a fixed bug has a **regression** test
- [ ] Public functions document **units and frames**
- [ ] Invalid pixels are `nan`, never a sentinel
- [ ] Estimators return variance, not a bare point estimate
- [ ] No new dependency, or the dependency is justified below
- [ ] An ADR was added if this decision constrains future work
- [ ] `results/` and `data/` untouched
- [ ] The diff contains nothing that was not asked for

## Closures

<!-- Confirm none are violated, or explain. -->
- Scaling closure (no metres below L4):
- Control-regime closure (L5 does not re-derive depth):
- Reference-frame closure (frames explicit):

## Numerical impact

<!-- Does any existing result change? If so, which, and by how much? -->
