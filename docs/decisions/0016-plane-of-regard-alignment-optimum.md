# ADR-0016: The plane-of-regard alignment optimum is k = 1/2

- **Status:** Accepted. **Corrects ADR-0014** — it does not supersede it.
  ADR-0014's Decision 1 (the Listing coefficient is a parameter) stands and is
  strengthened. Its *geometric justification* for the 0.25 default
  (`0014:52-60`) is wrong, and the consequences drawn from that justification
  (`0014:85-92`) do not follow as reasoned.
- **Date:** 2026-08-25
- **Context of discovery:** deriving the acceptance tolerance for migration
  step 4 before writing the test
  (`docs/lab-notebook/2026-08-25-plane-of-regard-optimum.md`)

## Context

ADR-0014:56-57 states the engineering reading of its default plainly:

> **L2 at k = 0.25 is the torsion that zeroes vertical disparity in the plane
> of regard.**

and ADR-0014:116-118 makes that a standing pin: residual vertical disparity in
the plane of regard "minimised near `k = 0.25`, with a minimum elsewhere read as
an `eye_rotations` sign/axis error until proven otherwise".

Measured, the minimum is at **k = 1/2**. At sagittal gaze it is not a minimum
but an exact zero — machine zero, independent of baseline, focal length,
vergence and elevation. The reason is an identity rather than a cancellation:
at `k = 1/2` the tilted-Listing composition `A(p_e→g_e)·A(ẑ→p_e)` **is** the
Helmholtz rotation `R_x(el_e)·R_y(az_e)` of that eye's own gaze, to 1e-16. By
ADR-0015's planarity property, Helmholtz composition carries no torsion about
the plane of regard, so the plane images on the horizontal meridian of both
retinas simultaneously. The optimum is ADR-0015 restated in oculomotor terms.

**The sign/axis clause is discharged, not invoked.** `eye_rotations` was
reimplemented independently — trigonometric axis-angle Rodrigues against the
module's trig-free form, and the fixation point by bisection on the subtended
angle against the module's closed-form Vieth–Müller chord — and agrees to
4.021e-15 (18 ε) over 144 (az, el, μ, k) configurations including eccentric
azimuth, reproducing `k_null = 1/2`. No `src/` code changes under this ADR.

## Decision

1. **Record the geometric fact.** The `k` that aligns the images of the plane of
   regard on the two retinas is **1/2**, exactly and at sagittal gaze only.
   ADR-0014:52-60's identification of that optimum with 0.25 is withdrawn.

2. **`k = 0.25` becomes PROVISIONAL, and is not re-justified here.** The default
   value is unchanged in code. What changes is its standing: ADR-0014 rested it
   on two legs — an empirical range and a geometric optimum asserted to coincide
   with it. The geometric leg is gone. The default now rests on an empirical
   number **whose convention is in question** (item 3), so it is recorded as
   provisional pending that audit. This ADR deliberately does **not** substitute
   k = 1/2 as the default: the plant's actual gain is a measurement, not a
   corollary of a rectification property.

3. **Flag the convention conflict; do not resolve it here.** Two families of
   literature numbers cannot both be this repo's `k`, which tilts *each* eye's
   Listing plane temporally by `k·μ` (dihedral angle between the two planes
   `= 2·k·μ`):
   - reports of the angle **between** the two Listing planes as somewhat less
     than the vergence angle map to `k` just under 1/2;
   - reports of a **per-eye** horizontal-primary-position gain of ≈ 0.25–0.35
     map to `k` ≈ 0.25–0.35.

   ADR-0014's cited range "0.17–0.25 across human studies … broader treatments
   report 0.2–0.5" is consistent with these being *two different quantities*
   rather than one quantity with a wide spread. Resolving this requires reading
   the primary sources for their convention, which has not been done; it is
   registered as open work, not settled by assertion in either direction.

4. **Re-register the k-sweep.** ADR-0014's Decision 2 (the question is a
   measurement, not an argument) survives. What it loses is its **second role as
   an implementation audit** — that role assumed the sweep's minimum was known
   in advance to be 0.25, and it is now discharged by the independent
   reimplementation above, which is a direct check rather than an inference from
   a minimum's location. The sweep's remaining purpose is sharper: it measures
   **which convention the empirical numbers are in**, by locating the plant gain
   against a geometric optimum now known to sit at 1/2.

5. **Mark ADR-0014:85-92 unsupported-as-reasoned.** That passage derives "the
   vertical-disparity cue is peripheral by construction" from the premise that
   the default aligns visual-plane images. The premise is false at k = 0.25, so
   the derivation does not go through. **Its conclusion is not asserted to be
   false here** — it may well hold at k ≈ 1/2, and the psychophysical
   corroboration ADR-0014 cites is independent of the premise. It is marked as
   requiring re-derivation once `k` is settled, and its ADR-0003 corollary
   (`0014:93-99`) inherits that status.

## Alternatives considered

- **Change the default to k = 1/2.** Rejected, and this is the important
  rejection. It would repeat ADR-0014's actual mistake — reading a *rectification
  optimum* as a *statement about the plant*. `k` parameterises a biological law;
  that the framework's matcher would prefer 1/2 is not evidence the eyes do 1/2.
  Making the convenient value the default would also destroy the k-sweep's
  ability to detect the convention conflict, by moving the default onto the
  answer being tested for.
- **Amend ADR-0014 in place.** Not available: ADRs are append-only and the
  hook enforces it. Nor desirable — the reasoning that produced the error is
  itself the record, and this is the second time the append-only cost has bought
  a traceable correction rather than a silent one (ADR-0014 was the first).
- **Record only in the lab notebook.** Rejected: a standing pin in an accepted
  ADR fired. A notebook entry does not change what `0014:116-118` instructs the
  next reader to conclude, and that instruction — "read a minimum elsewhere as an
  implementation error" — is now actively misleading.
- **Treat the off-axis floor as the headline.** Rejected as premature. There *is*
  an irreducible floor at oblique gaze (no `k` aligns the plane when gaze is
  neither sagittal nor horizontal), but its magnitude ranges over four orders
  depending on whether the criterion is taken over the plane or over the
  Vieth–Müller circle inside it. Until the framework commits to one, the floor is
  recorded with its point set in the notebook and asserted nowhere.

## Consequences

- **L4 vertical-disparity cue work is contaminated until `k` is settled.** At
  k = 0.25, max |row_L − row_R| **on the Vieth–Müller circle, sampled to the
  image edge (|x| ≤ 160 px, the 320-px image width at f = 800 px), el = 0.149,
  sagittal gaze** is 0.38 px at 1.0 m fixation, 0.55 px at 0.7 m and 0.95 px at
  0.4 m; at az = 0.35 each rises ≈ 9%. That is at or above exp007's measured
  MiddEval3 `dyavg` (≈ 0.5 px at Q) and one to two orders above matcher precision
  (0.0714 px block, 0.0074 px energy bank, exp006). That artefact is the **same
  order as the cue it would be mistaken for**, and the two share a channel, so no
  measurement of that channel separates them. Any L4 result that reads vertical
  disparity as a distance cue must state the `k` it was computed at.

  *Why these figures are quoted on the circle and not over the plane of regard,
  when Decision 1 makes the plane the criterion:* a plane figure requires three
  analyst choices — a depth set, an azimuth span, and max vs rms — and the metric
  choice alone moves it by 1.8× (0.41 px max against 0.22 px rms over one and the
  same window). The circle has a single free parameter, the image half-width,
  which the rig fixes rather than the analyst. An append-only document should not
  carry a number that cannot be reproduced from what it states. The plane tables,
  each with its window, are in the companion notebook entry.
- **Migration step 4 gains a sharper acceptance criterion.** The Vieth–Müller
  circle is the exact zero-horizontal-disparity locus of the toed-in model only
  where `az = 0` or `el = 0`; at oblique gaze it misses by ≈ 3e-2 px at the image
  edge. ADR-0007 item 4 can now be closed precisely rather than approximately.
- **The k-sweep gets more expensive and more informative.** It must now sweep
  through 1/2, and report the criterion (plane vs circle) it minimises over.
- **`eye_rotations` is audited.** Independent reimplementation agreement at 18 ε
  is a stronger statement about L1 than anything the module's own tests make,
  and it is now the discharge of record for `0014:118`.

## Verification

`tests/unit/test_oculomotor.py::test_plane_of_regard_alignment_optimum_is_k_half`
pins the null at k = 1/2 as an analytic statement about a stated `k` — machine
zero (`atol` 1e-12 px) across three (baseline, focal) rigs × (μ, el), with
k ∈ {0, 0.25} as a negative control that must exceed it by nine orders. It
deliberately does **not** minimise over `k` and assert the argmin is 0.5: that
would pin the search rather than the physics, and the argmin drifts off 1/2
off-axis while the statement above does not.

`::test_tilted_listing_at_k_half_is_helmholtz` pins the identity of §Context
independently — it needs no projection, so it fails on its own if the
composition is wrong, with k = 0.25 as its negative control.

Item 3 (the convention conflict) is deliberately **unverified**: it is registered
open work, and a test asserting either reading would be the error this ADR exists
to correct.
