# ADR-0014: The Listing coefficient is a parameter, and 0.25 is a rectification property

- **Status:** Accepted. **Refines ADR-0013** — it does not supersede it.
  ADR-0013's decision that torsion is *determined, not free* is correct and
  stands, and its status is unchanged; this ADR narrows exactly one of its
  declared open questions.
- **Date:** 2026-08-23
- **Context of discovery:** design review of ADR-0013's torsion clause,
  arriving from Chat as hypotheses with pointers (CLAUDE.md §5)

## Context

ADR-0013 (lines 65–70) declared "L2 vs strict Listing (L1)" an open question,
defaulted to L2, and gave the μ/4 coefficient without justification. ADR-0013
is merged and append-only, and modifying it is prompt-gated by the governance
change of PR #23 — so this correction costs a new ADR. That is the system
working as designed, not overhead to route around: the rule that stops an
amendment to 0013 is the successor of the rule this project adopted after an
amendment path was found around a weaker one.

The question itself was mis-shaped. Strict Listing (L1) is exactly the zero
of the L2 family: L2 tilts each eye's Listing plane temporally by `k · μ` for
vergence `μ`, and L1 is `k = 0`. A fork between "L1" and "L2" is therefore a
fork between two points of a one-parameter family — parameterising subsumes
both, and there is nothing left to resolve by argument.

## Decision

1. **The coefficient is a parameter.** `eye_rotations` takes `k` as a
   constructor/keyword parameter, **default `k = 0.25`**; strict Listing is
   available as `k = 0`. The implementation gains a parameter, not a branch
   (`docs/plans/fixation-migration.md` step 3 is updated accordingly).
2. **The open question becomes "what is k"** — a sweep, not an argument. The
   experiment: sweep `k`, measure residual vertical disparity in the plane of
   regard and matcher performance under ADR-0013's RECTIFY default, and check
   whether the minimum lands near 0.25 as the theory predicts. **This doubles
   as a validation test of `eye_rotations` itself:** if the minimum does not
   land near 0.25, the implementation has a sign or axis error. That property
   — one sweep that both measures the biology and audits the code — is the
   reason to shape the question this way.

### Why 0.25 is the default

- **Empirical.** The measured ratio of Listing-plane tilt to vergence angle
  is ≈ 0.21 in monkeys (Misslisch et al. 2001) and 0.17–0.25 across human
  studies (Mok et al. 1992; Minken & van Gisbergen 1994; Bruno & van den Berg
  1997); broader treatments report 0.2–0.5, which is why L2 is sometimes
  called an ad hoc extension rather than a law (see also van Rijn & van den
  Berg 1993; Tweed 1997; Somani et al. 1998). Given that spread, a hardcoded
  constant would be false precision — an independent second reason for
  Decision 1.
- **Geometric, and load-bearing.** 0.25 is the theoretical optimum (Tweed
  1997; van Rijn & van den Berg 1993): it rotates the eyes so that images of
  the **visual plane** — the plane containing both lines of sight — are
  aligned on the two retinas. The engineering reading, stated plainly:
  **L2 at k = 0.25 is the torsion that zeroes vertical disparity in the plane
  of regard.** It is a rectification property found by oculomotor
  physiologists. This is why biological fidelity and matcher convenience
  coincide here, and why the choice *conditions* ADR-0013's RECTIFY default
  rather than merely coexisting with it.
- **The observable**, for migration step 3's analytic tests:
  elevation-dependent torsion — intorsion for upward proximal gaze, extorsion
  for downward, opposite in sign between the two eyes.

*Provenance:* the figures above are literature-sourced. They arrived from
Chat and were corroborated by web search against the cited literature
(abstract/summary level) on 2026-08-23; they have not been independently
re-derived in-repo. Per the handoff contract (CLAUDE.md §5), treat the
citations as the authority and this paragraph as the audit trail.

## Alternatives considered

- **Keep the L1/L2 fork as declared.** Rejected: `k = 0` subsumes L1, so the
  fork invites an argument over what is actually a measurement, and any
  resolution would be re-litigated the first time a sweep produced a number
  other than exactly 0 or 0.25.
- **Hardcode 0.25.** Rejected: the empirical spread (0.17–0.5 across studies
  and species) makes a constant false precision, and it would forfeit the
  sweep's second role as an implementation audit.
- **Free torsion.** Already rejected in ADR-0013, which stands: `Fixation`
  exposes no torsion DOF; `k` parameterises the *law*, not the state.

## Consequences

- **The vertical-disparity cue is peripheral by construction — a prediction,
  not a caveat.** Because L2 at the default aligns visual-plane images, it
  removes vertical disparity precisely at fixation. The vertical-disparity
  cue to viewing distance that ADR-0013 promoted from nuisance to cue is
  therefore a **peripheral, large-field quantity, not a foveal one**. This is
  falsifiable, and it is consistent with the psychophysics: the induced
  effect and distance-scaling results require large fields, and there is a
  vertical-disparity *pooling* literature for exactly that reason.
- **Interaction with ADR-0003, sharpening the scaling closure.** Foveal
  confinement makes the horizontal-disparity depth estimate precise but
  local; the vertical-disparity distance cue is coarse but global. They are
  **complementary, not redundant**: L4 fuses a precise *relative* estimate
  with a coarse *absolute* one, rather than averaging two versions of the
  same quantity. That is a sharper statement of the scaling closure than
  ADR-0013 makes, and it is *generated* by the L2 choice rather than assumed.
- **A quantity to be computed, deliberately not recorded here.** The
  L1-vs-L2 vertical displacement at the project's actual stimulus scales is
  to be computed from `eye_rotations` at migration step 3 and benchmarked
  against measured in-repo scales: exp007's MiddEval3 `dyavg` (up to
  ≈ 0.5 px at Q) and the matchers' median |Δd| (≈ 0.07 px best-case RDS,
  exp006; ≈ 0.2–0.5 px on well-behaved Middlebury/MiddEval3 scenes — hard
  scenes run far higher). A hand-derived estimate existed and was excluded
  from this ADR as unverified arithmetic; the number that gets recorded will
  be the computed one.

## Verification

- Migration step 3's analytic tests pin the law: `k = 0` reduces to strict
  Listing; symmetric horizontal fixation gives zero torsion at any `k`;
  eccentric near fixation gives the elevation-dependent torsion signs above,
  opposite between the eyes.
- The `k`-sweep experiment is the standing pin: residual vertical disparity
  in the plane of regard minimised near `k = 0.25`, with a minimum elsewhere
  read as an `eye_rotations` sign/axis error until proven otherwise.
