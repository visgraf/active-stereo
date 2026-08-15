# ADR-0003: Confine confidence to the fovea with a Taylor-remainder term

- **Status:** Accepted
- **Date:** 2026-08-15
- **Context of discovery:** Matcher comparison, block matching vs SGBM

## Context

The disparity-to-depth inversion at L4 is linearised about the current fixation.
That linearisation is only locally valid, but nothing in the pipeline said so.

Observed symptom: **block matching appeared to match or beat SGBM**, contradicting
theory and every published comparison. The pipeline reported uniform confidence
across the whole visual field, so peripheral estimates entered fusion weighted
equally with foveal ones. SGBM's advantage is concentrated where the linearisation
holds; averaging it away with peripheral noise erased the difference.

The missing physics: the second-order Taylor remainder of the inversion grows
with eccentricity `eta` from the fovea. Omitting it is not a small approximation —
it is the difference between a model of *foveated* vision and a model that
pretends the periphery is as good as the centre.

## Decision

Add an eccentricity-dependent variance penalty, quadratic in `eta`:

    var_total = var_measurement + c * eta^2

implemented as `policy.foveation.linearization_penalty` and applied by
`confine_to_fovea`. `eta` is normalised by the centre-to-corner-pixel distance so
that `c` is comparable across resolutions. Variance only ever increases, so the
term can never manufacture confidence.

With this in place, SGBM outperforms block matching, as theory predicts.

## Alternatives considered

- **Linear in `eta`.** Rejected: does not confine tightly enough; the periphery
  still dominates fusion through sheer pixel count.
- **Quartic, or a hard foveal mask.** Rejected: discards peripheral information
  entirely. The periphery is genuinely informative for the *gaze policy* even
  when it is poor for metric depth — a hard mask would starve L6.
- **Empirical per-pixel variance calibrated from ground truth.** Rejected for now:
  accurate but scene-specific and not portable, and it hides the mechanism. The
  analytic term is a claim about the model that can be wrong and therefore tested.
- **Fixing it at L3 by degrading peripheral matching.** Rejected: conflates
  matcher quality with model validity. The matcher is not worse in the periphery;
  our *linearisation* is.

## Consequences

- Matcher comparisons become theoretically well-behaved and therefore meaningful.
- `c` is a new free parameter requiring calibration per scene. Normalising `eta`
  keeps it stable across resolutions, which limits the damage.
- Fusion now naturally prefers foveal evidence, which is the correct inductive
  bias for an active-vision system and closes the loop with L6: the policy has a
  reason to move the fovea.

## Verification

`tests/regression/test_adr0003_foveal_confinement.py` — the penalty must be
exactly quadratic in `eta`, zero at the fovea, monotone outward, never
variance-reducing, must downweight the periphery in fusion, and must be
resolution-independent under normalisation.
