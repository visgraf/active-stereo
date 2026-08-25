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
| [0007](0007-offaxis-not-toein.md) | Off-axis frusta; L1 is not the Vieth–Müller model | Superseded by [0013](0013-fixation-as-oculomotor-state.md) | 2026-08-15 |
| [0008](0008-python-floor-312.md) | Python floor 3.12; mypy is a blocking gate | Accepted | 2026-08-15 |
| [0009](0009-blender-api-version-adaptive.md) | Branch on the Blender API rather than pin a version | Accepted | 2026-08-15 |
| [0010](0010-multilayer-exr-not-compositor.md) | Render via multi-layer EXR, not the compositor | Accepted | 2026-08-15 |
| [0011](0011-ground-truth-known-mask.md) | Missing ground truth is a fourth mask, not a value of the other three | Accepted | 2026-08-18 |
| [0012](0012-middlebury-real-data-corpus.md) | Middlebury 2014 is the real-data corpus; `doffs` is our vergence | Accepted | 2026-08-18 |
| [0013](0013-fixation-as-oculomotor-state.md) | Fixation is oculomotor state — the eyes rotate | Accepted | 2026-08-23 |
| [0014](0014-listing-coefficient-as-parameter.md) | The Listing coefficient is a parameter; 0.25 is a rectification property | Accepted (refines 0013); geometric justification corrected by [0016](0016-plane-of-regard-alignment-optimum.md) | 2026-08-23 |
| [0015](0015-helmholtz-gaze-composition.md) | Gaze angles compose in Helmholtz order | Accepted (refines 0013) | 2026-08-23 |
| [0016](0016-plane-of-regard-alignment-optimum.md) | The plane-of-regard alignment optimum is k = 1/2 | Accepted (corrects 0014) | 2026-08-25 |
| [0017](0017-rectification-rotation-member.md) | The rectification rotation is the Helmholtz version rotation with azimuth zeroed | Accepted | 2026-08-25 |

This index is maintained; it is a table of contents, not a decision, so the
append-only rule does not cover it.

**How append-only is enforced, precisely.** A PreToolUse hook
(`.claude/hooks/adr_append_only.py`) guards the `Write`/`Edit`/`NotebookEdit`
tool paths: modifying an existing `docs/decisions/0*.md` is denied outright;
creating a new ADR is prompt-gated. The hook fails closed — unparseable
input, unresolvable paths, and internal errors all deny. Enforcement is by
file existence because a path pattern cannot express create-vs-modify:
Edit-family permission rules also match the Write tool, so the previous deny
rule on `docs/decisions/0*.md` also blocked *creating* new ADRs (discovered
2026-08-23 when ADR-0015 could not be written). A newly added ADR is
protected without any list being extended.

**What this does not guarantee.** Bash is a separate tool path: `sed -i`,
`tee`, or a shell redirect targeting an ADR does not pass through the hook.
Those commands are not allowlisted, so they prompt for approval, and narrow
deny rules in `.claude/settings.json` catch the obvious in-place forms — but
shell-string glob matching is brittle (quoting, variables, a prior `cd`,
heredocs, `python -c` all evade it) and is defence in depth, not a boundary.
The invariant actually enforced: **existing ADRs cannot be modified through
the file-editing tools, and any other modification path requires explicit
human approval.** See `docs/method/001-enforcement-and-disclosure.md` for why
this edge is documented rather than claimed closed.
