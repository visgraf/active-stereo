# ADR-0005: Estimators return an estimate and its variance, never a bare value

- **Status:** Accepted
- **Date:** 2026-08-15

## Context

The framework is Bayesian: MLE cue fusion (L4), Kalman filtering (L5), and
information-maximising gaze (L6) all require uncertainty. Recovering it after the
fact is impossible, and an estimator that has lost its uncertainty tends to be
replaced by a heuristic weight that nobody can justify.

## Decision

Every estimator returns `Estimate(value, variance)`. Invalid entries are `nan` in
both arrays — never `0`, never `-1`. `Estimate.precision` returns inverse variance
with zeros on invalid entries, so an invalid measurement contributes nothing to
fusion rather than poisoning it.

## Alternatives considered

- **Return the point estimate; compute variance on demand.** Rejected: the
  information needed (cost curvature, filter innovation) is local to the
  estimator and gone by the time a caller asks.
- **Full posterior distributions.** Rejected for now as the default — the cost is
  real and Gaussian summaries suffice for the current claims. `Estimate` is the
  place to extend if a layer needs multimodality, which L3 with belief propagation
  plausibly will.
- **Sentinel values for invalid.** Rejected: a `-1` disparity silently becomes a
  real depth downstream. `nan` propagates loudly.

## Consequences

- Fusion, filtering, and the gaze policy are all expressible without ad-hoc
  weights.
- Every new estimator must say something honest about its own uncertainty, which
  is often the hardest part. That difficulty is the point.
- Memory doubles for every field. Irrelevant at our sizes.

## Verification

`tests/unit/test_types.py`, `tests/unit/test_scaling.py`, and
`tests/unit/test_inference.py::test_invalid_pixels_are_nan_not_sentinel`.
