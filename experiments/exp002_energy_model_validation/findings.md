# exp002 — Contrast-invariant tuning of the migrated energy-model encoder

**Issue:** #1
**Status:** run once — hypothesis does **not** survive as jointly stated (see below)

## Hypothesis

The migrated `DisparityEncoder` (L2, `encoding/`) reproduces the canonical
energy-model signature: for a synthetic stereo pair with known constant
disparity `d0`, the peak-response channel sits at `d0`, and that peak channel
is invariant to interocular contrast gain.

This is not a Protocol-conformance check (that belongs in
`tests/unit/test_encoding.py`). It is a claim about mechanism: a
shift-and-correlate encoder repackaged into K bins can also peak near `d0` on
high-contrast noise textures, so the gain-invariance sweep is the part that
actually discriminates a true quadrature energy model from one that only looks
like it through the Protocol.

## What would falsify it

- Peak channel off `d0` by more than 1 bank-step for more than 5% of valid
  pixels at gain=1.0.
- Population-mean peak channel drifting by more than 0.5 px across the
  gain sweep `{0.5, 0.75, 1.0, 1.25, 1.5}`.

## Acceptance criteria

Both thresholds above must hold on the median over 5 seeds (0-4), each an
independent random-dot draw via an explicit `rng` (CLAUDE.md §3 — no global
NumPy state).

## Runs

| Run ID | SHA | Config | Result | Notes |
|---|---|---|---|---|
| `exp002-20260815T200128-965a3ad` | `965a3ad` | `config.yaml` as committed | falsifier 1 fails, falsifier 2 survives | `results/exp002-20260815T200128-965a3ad/summary.json` |

## Findings

**Falsifier 2 (gain invariance) survives, decisively.** Median population-mean
peak-channel drift across the full gain sweep `{0.5, 0.75, 1.0, 1.25, 1.5}` was
**0.031 px** (per-seed: 0.024–0.035 px) — two orders of magnitude under the
0.5 px threshold. This is the mechanism claim the hypothesis actually cares
about, and it held essentially at noise level, matching the exact algebraic
argument in `encoding/energy.py`'s module docstring (pooling is linear and
happens before rectification, so a positive gain factors out of every channel
identically; rectification then commutes with that positive scaling).

**Falsifier 1 (peak-near-`d0` precision) does not survive.** Only 50–58% of
valid pixels landed within ±1 bank-step of `d0=8` at gain=1.0 (median 58.0%),
against the ≥95% threshold. This is *not* a bias problem: the per-seed
population-**mean** peak channel is 7.93–8.16, i.e. centred almost exactly on
`d0`. It's a per-pixel **precision** problem — individual pixels scatter by a
few px around the correct mean.

Likely mechanism, not yet independently confirmed: the 7×7 pooling window
(`encoding.bank.step`-independent, hard-coded as the encoder's `window`
default) is meant to do what `BlockMatcher`'s box-sum does for SSD cost —
average out single-pixel noise. But `BlockMatcher` pools 49 *raw pixel*
differences, effectively close to 49 independent samples. This encoder pools
49 *already-Gabor-filtered* coherence values, and adjacent Gabor windows
(radius ≈18 px) overlap almost completely across a 7 px pooling window — the
49 pooled values are highly correlated with each other, not independent, so
the effective noise reduction from pooling is much weaker than the raw-pixel
case despite using the same window size. If this diagnosis is right, a wider
pooling window (relative to the ~18 px kernel radius) or averaging over
several independent stimulus draws per pixel should tighten the per-pixel
distribution without changing the encoder's mechanism.

**I have not changed `window`, `sigma`, `frequency`, or either threshold to
retest this** — per the plan, a failing result gets reported and escalated,
not quietly tuned into a pass. Whether to (a) treat the ≥95%/±1px threshold as
having been an uninformed guess at experiment-design time and restate it
against the population-mean statistic instead, (b) widen the pooling window
and rerun, or (c) treat this as a genuine limitation of a single-frequency,
single-scale encoder is a call for you, not something to resolve by adjusting
knobs until the number turns green.

## Threats to validity

- Bank resolution (`encoding.bank.step` in `config.yaml`) sets its own
  tolerance. Fixed once here; must not be retuned later to make the result pass.
- Constant-disparity-only stimuli validate encoder *sanity*, not *sufficiency*
  for real disparity fields — the same trap exp001 hit (see its findings.md:
  "measuring the placeholder, not the hypothesis"). A pass here says nothing
  about slanted or discontinuous scenes.
- `synthetic_pair` bypasses L1 (`geometry`) entirely: no rectification, no
  projection artifacts. Says nothing about rectified real or Blender-rendered
  imagery.
- **Positive-result spuriousness (the main one):** an implementation that
  satisfies the Protocol via correlation rather than quadrature summation can
  still land near `d0` on noise-texture stimuli. Only the gain-invariance
  sweep separates the two mechanisms — a result run with fewer than the full
  5-point sweep, or with gain points too close together, would not be
  informative even if it "passes."
- L3 is not wired to consume this encoder's output as part of this experiment;
  a pass here says nothing about downstream matching performance.
