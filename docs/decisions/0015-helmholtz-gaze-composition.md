# ADR-0015: Gaze angles compose in Helmholtz order

- **Status:** Accepted. **Refines ADR-0013** — its `Fixation` fields and their
  signs stand; this ADR pins the composition step 2 left unpinned.
- **Date:** 2026-08-23
- **Context of discovery:** design review of migration step 3
  (`geometry/oculomotor.py`), planning `fixation_distance`

## Context

`Fixation` (types.py, migration step 2) pins the *fields*: `azimuth` (rad,
positive toward +X/right) and `elevation_down` (rad, positive toward +Y/down).
It does not pin how the two angles **compose** into a gaze direction. Fick
order (rotate about the head-fixed vertical axis first, then elevate about the
carried horizontal axis) and Helmholtz order (elevate about the fixed
interaural X axis first, then rotate within the elevated plane) agree on both
axes' signs and on every cardinal direction, and differ at O(azimuth ×
elevation) off the axes — small at project scales, but a genuine second
convention if left implicit, which CLAUDE.md §3 forbids. Step 3 forced the
choice: `fixation_distance(rig, fixation)` needs a definite cyclopean
direction.

## Decision

Gaze angles compose in **Helmholtz order**. The cyclopean direction is

    d = ( sin az,  cos az · sin el,  cos az · cos el )     (unit, head frame)

with `az = azimuth`, `el = elevation_down`. Implemented once, in
`geometry.oculomotor._cyclopean_direction`; every consumer of gaze angles goes
through `geometry/oculomotor.py`, never a private re-derivation.

**Why Helmholtz and not Fick — recorded so it survives a well-read reviewer.**
Fick is the more common convention for *single-eye* orientation, and much of
the oculomotor literature states monocular results in Fick coordinates.
Someone will eventually "correct" this module to Fick citing that literature.
The reason it would be a regression is binocular: under Helmholtz,
`d_y / d_z = tan(el)` **independent of azimuth**, so every gaze direction at
elevation `el` lies in the single plane obtained by rotating the horizontal
plane about the interaural axis by `el`. That plane contains the baseline —
i.e. **the plane of regard (both eyes + fixation point) is exactly the
elevated plane, for every azimuth**. Two things stand on that planarity:

1. `fixation_distance` is exact and closed-form — a chord of the Vieth–Müller
   circle inside the plane of regard, `D = h·cos az + sqrt(h²·cos²az +
   (b/2)²)` with `h = (b/2)/tan μ` — with elevation not entering at all.
   Under Fick the eyes/fixation-point plane depends on azimuth and the chord
   construction is no longer exact.
2. ADR-0014's geometric justification for `k = 0.25` — L2 torsion aligns the
   images of the **visual plane** (the plane containing both lines of sight)
   — is stated in plane-of-regard terms. Helmholtz makes "the plane of regard
   at elevation el" a well-defined object those statements can quantify over
   exactly.

## Alternatives considered

- **Fick order.** Rejected for binocular geometry: the planarity property
  above fails, `fixation_distance` becomes approximate or iterative, and
  ADR-0014's visual-plane statements hold only to first order. Fick's
  advantage (familiarity from monocular oculomotor work) does not bear on any
  computation this project does.
- **Leave it implicit in the implementation.** Rejected: that is exactly how
  a second convention is born. The divergence is O(az·el) — big enough to
  matter at image-corner eccentricities in a test tolerance, small enough to
  survive review unnoticed.
- **Store the direction vector instead of angles.** Rejected in ADR-0013
  already (per-eye rotations / non-angular state); the Hering decomposition
  into version and vergence is load-bearing for L5.

## Consequences

- The plane of regard is a first-class, exact object; step 4's toed-in
  projection and the ADR-0014 k-sweep can quantify over it without
  linearisation caveats.
- Any future consumer converting `(azimuth, elevation_down)` to a direction
  must use `geometry.oculomotor`, not re-derive; a Fick-style re-derivation
  is a unit/frame bug even where the numeric difference is below test
  tolerance.
- The Blender adapter (step 12) converts at its own boundary from this
  definition, as ADR-0013 already requires for the +Z-up frame.

## Verification

`tests/unit/test_oculomotor.py`: the handedness anchors pin the axis signs of
the composed direction (positive azimuth ⇒ +X gaze component; positive
elevation_down ⇒ +Y); the gaze-lines-intersect test pins the closed-form
`fixation_distance` against the geometric definition of fixation (distance
from the fixation point to both gaze lines < 1e-12 m, and the angle the gaze
lines subtend recovers `vergence` to rtol 1e-9) across an azimuth × elevation
× vergence × k sweep — the chord formula is only exact if the planarity
property holds, so the sweep would fail under a Fick composition.
