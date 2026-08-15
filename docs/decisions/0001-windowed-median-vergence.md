# ADR-0001: Estimate vergence from a windowed median, not a single foveal pixel

- **Status:** Accepted
- **Date:** 2026-08-15
- **Context of discovery:** Prototype (`active_stereo_demo.py`), pre-repository

## Context

The L5 vergence controller needs the disparity at the fixation point. The
obvious implementation reads the foveal pixel of the L3 disparity field.

Observed symptom: the control loop oscillated and occasionally diverged. The
cause is structural, not a tuning problem. A single pixel is one sample of a
noisy field, taken at precisely the location where matching is least reliable —
fixation targets are often texture-poor, and a saccade frequently lands the
fovea on a depth discontinuity where the correct disparity is ambiguous. A
single mismatch produces a large spurious vergence error; the loop responds;
the response moves the fovea onto different bad data.

## Decision

Estimate vergence disparity as the **median over a window** (default 15 px)
centred on the fovea, and return `(nan, inf)` when fewer than 25% of the window's
pixels are valid. The Kalman filter in `control/kalman.py` treats that as "no
measurement" and coasts on its prediction.

Estimator variance is `(pi/2) * mean_var / n_valid` — the `pi/2` is the median's
asymptotic efficiency loss relative to the mean.

## Alternatives considered

- **Windowed mean.** Rejected: the failure mode is outliers, not Gaussian noise,
  and the mean has breakdown point 0.
- **Larger window only.** Rejected: does not help if the estimator is still
  non-robust; a big enough window also violates the locality the fovea assumes.
- **Confidence-weighted mean using L3 variance.** Deferred, not rejected. It is
  principled, but L3 variance is currently a crude curvature proxy, so weighting
  by it propagates the matcher's overconfidence. Revisit when L3 gains proper
  belief propagation.
- **Temporal filtering alone.** Rejected as a substitute: filtering a biased
  measurement gives a smooth biased measurement. It is complementary, and is what
  the Kalman filter does.

## Consequences

- Vergence becomes stable enough for the L5/L6 loop to close, which is the
  precondition for any active-sampling result.
- The estimator can now *refuse to answer*, so every consumer must handle
  `(nan, inf)`. This is deliberate: a refusal is information.
- Slight lag on genuine rapid depth changes at the fovea. Acceptable; the plant
  has its own dynamics at that timescale anyway.

## Verification

`tests/regression/test_adr0001_windowed_vergence.py` — a single foveal outlier
must not move the estimate, 30% outliers must not move it beyond tolerance, and
sparse data must produce a refusal rather than a guess.
