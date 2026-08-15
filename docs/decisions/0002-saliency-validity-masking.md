# ADR-0002: Mask invalid pixels before any spatial mixing

- **Status:** Accepted
- **Date:** 2026-08-15
- **Context of discovery:** Prototype, active-sampling loop hang

## Context

The L6 gaze policy fixates the maximum of a blurred uncertainty map. The
original implementation blurred the variance field directly, with invalid and
occluded pixels still present.

Observed symptom: **the active-sampling loop never terminated.** It fixated the
same occlusion band on every iteration.

The mechanism is a vicious circle. An occlusion band is *geometrically*
unresolvable — the surface is visible to one eye only, so no fixation can produce
a match there. But invalid pixels read as maximal uncertainty, so the band was
maximally salient, so the policy went there, so nothing was resolved, so it was
still maximally salient.

This is worth stating precisely because it generalises: **invalid is not the same
as uncertain.** Uncertain means "we could learn more by looking." Invalid means
"there is nothing here to learn." Conflating them makes an information-maximising
policy chase the unknowable.

## Decision

Two changes, both required:

1. **Normalised convolution.** `policy.saliency.masked_blur` blurs
   `field * valid` and `valid` with the same kernel and divides, so each output
   is the weighted mean of *valid* neighbours only. Pixels with no valid support
   remain `nan`. This is the only sanctioned way to smooth a field with invalid
   entries in this codebase; a plain Gaussian blur silently treats missing data
   as zero.
2. **Inhibition of return.** `policy.gaze.next_fixation` suppresses a radius
   around each visited location and returns `None` when no candidate remains —
   the signal to terminate the loop rather than spin.

Generalised to a repo-wide invariant (CLAUDE.md §3): any operation that spatially
mixes pixels must mask validity first.

## Alternatives considered

- **Fill invalid pixels with the field mean before blurring.** Rejected: invents
  data, and the invented value still competes for the argmax.
- **Cap saliency at a maximum.** Rejected: treats the symptom. The band still
  wins whenever real uncertainty is below the cap.
- **Iteration budget on the loop.** Rejected as a fix, kept as a backstop. A cap
  turns a hang into a silently truncated result, which is worse than a hang
  because it looks like success.
- **Excluding occlusions at L3 instead.** Rejected: L3 cannot know which
  invalidity is geometric and which is merely a hard match. Handling it at the
  policy layer is the right level.

## Consequences

- The loop terminates, and terminates *for a reason* it can report.
- `masked_blur` costs two convolutions instead of one. Irrelevant at our sizes.
- Every new field-smoothing operation is now obliged to think about validity.
  The `exclude_invalid=False` parameter on `uncertainty_saliency` exists solely
  so the regression test can exhibit the original failure; production code must
  never set it.

## Verification

`tests/regression/test_adr0002_saliency_validity.py` — masked blur must not leak
invalid values, the occlusion band must not be the saliency maximum, and the
active loop must terminate within a bounded number of fixations. One test
deliberately demonstrates that a plain blur *would* have leaked, so the guard
retains its referent.
