# Architecture Decision Records

Numbered, dated, **append-only**. An ADR is never edited once merged; it is
*superseded* by a later ADR that references it.

An ADR is warranted when a choice (a) constrains future work, (b) was
non-obvious, or (c) was learned the hard way. Routine implementation choices do
not need one.

Template: [`0000-template.md`](0000-template.md).

| # | Title | Status | Date |
|---|---|---|---|
| [0001](0001-windowed-median-vergence.md) | Windowed-median vergence estimation | Accepted | 2026-08-15 |
| [0002](0002-saliency-validity-masking.md) | Mask validity before spatial mixing | Accepted | 2026-08-15 |
| [0003](0003-foveal-confinement-linearization-error.md) | Foveal confinement via linearisation remainder | Accepted | 2026-08-15 |
| [0004](0004-layer-module-boundaries.md) | Six layers as module boundaries | Accepted | 2026-08-15 |
| [0005](0005-uncertainty-first-class.md) | Estimators return variance, not point estimates | Accepted | 2026-08-15 |
| [0006](0006-scenes-as-a-separate-package.md) | Stimulus generation lives beside L1 | Accepted | 2026-08-15 |
| [0007](0007-offaxis-not-toein.md) | Off-axis frusta; L1 is not the Vieth–Müller model | Accepted | 2026-08-15 |
| [0008](0008-python-floor-312.md) | Python floor 3.12; mypy is a blocking gate | Accepted | 2026-08-15 |
