# ADR-0006: Stimulus generation lives beside L1, not inside it

- **Status:** Accepted
- **Date:** 2026-08-15
- **Context of discovery:** Porting the prototype's RDS and Blender demos

## Context

The prototype generated its synthetic stereo pairs inline, using the same
projection code the estimator later inverts. That is convenient and it is also a
measurement error: if the stimulus is produced by the very model being evaluated,
a perfect score demonstrates only that the code is self-consistent.

There is a second problem. The `exp001` placeholder scene was fronto-parallel, so
the foveal/peripheral distinction it was meant to probe was vacuous. Scene
construction had no home, so it defaulted to whatever the runner needed that day.

## Decision

A first-class `activestereo.scenes` package, parallel to the six layers rather
than inside any of them, exposing a `Scene` Protocol that returns a
`StereoStimulus`: left, right, ground-truth depth, ground-truth disparity, and
two boolean masks (`matched`, `in_frame`).

`scenes` is the ground truth; `geometry` (L1) is the generative model the
framework *reasons with*. They may agree — RDS synthesis deliberately calls
`depth_to_disparity` so the stimulus is exactly on-model — but the separation
makes that agreement a stated choice rather than an accident, and it leaves room
for rendered scenes that are deliberately off-model.

## Alternatives considered

- **Put scene generation in `geometry` (L1).** Rejected: it is precisely the
  conflation described above. L1 is a *model*; a stimulus is *data*.
- **Put it in `experiments/`.** Rejected: guarantees each experiment reinvents its
  own stimulus, so results are not comparable across experiments.
- **Use only rendered scenes, no synthetics.** Rejected: rendered scenes carry
  monocular cues (shading, texture gradients, occlusion contours) that a depth
  estimate could exploit. An RDS is the only stimulus that proves a depth estimate
  came from binocular matching.
- **Use only synthetics.** Rejected in the other direction: an RDS has no
  photometric realism, so it cannot expose failures that matter in XR.

## Consequences

- Evaluation can distinguish "the matcher failed" from "there was nothing to
  find", because occlusion is ground truth rather than an estimate.
- `exp001` can finally test its own hypothesis.
- One more package to keep in sync with L1's conventions. Mitigated by having
  `scenes.rds` call L1's `depth_to_disparity` rather than reimplement it.

## Verification

`tests/unit/test_scenes.py` — matched pixels correspond exactly, ground-truth
depth and disparity are mutually consistent, no monocular cue predicts depth,
occlusion appears only within one disparity-step of an edge.
`tests/integration/test_rds_end_to_end.py` — the full six-layer pipeline on an RDS.
