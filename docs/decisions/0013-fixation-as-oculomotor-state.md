# ADR-0013: Fixation is oculomotor state — the eyes rotate

- **Status:** Accepted. **Supersedes ADR-0007.**
- **Date:** 2026-08-23
- **Context of discovery:** design review of the L5/L6 active loop in
  `scripts/demo_active_stereo.py`

## Context

The demo's "active loop" (`scripts/demo_active_stereo.py:100-149`) does not
close. Verified line-by-line: saliency is computed once, outside the loop, and
never recomputed after a fixation; the loop never re-renders and never re-runs
L2 or L3, so the stimulus is fixed for the whole sequence; the vergence
"measurement" reads `stim.disparity` — the ground truth — with a hardcoded
variance of 0.25, while the real L3 estimate sits unused in `main()`; the
Kalman state is logged and consumed by no computation; `visited` affects only
inhibition of return. No action changes any subsequent observation. The demo
is a fixation-sequence generator with an oracle readout, not an
active-inference loop.

The cause is type-level, not a bug in the loop body. `StereoRig` carries a
scalar `vergence` — oculomotor state living in the anatomy type — and no gaze
direction; `Scene.render(rig, rng)` cannot express "render this world as seen
from fixation F". There is nothing for an action to change.

ADR-0007 is upstream of both facts. It chose the off-axis (shifted-frustum)
projection so that stimulus and L1 agree, and explicitly deferred a toed-in
model as open work (its item 4). That choice froze the framework in a geometry
where fixation has no degrees of freedom: a frustum shift has no gaze
direction to move.

## Decision

**Fixation is a rotation of each eye about its optical centre** (toed-in; the
zero-disparity locus is the Vieth–Müller circle). This supersedes ADR-0007's
off-axis projection as the model of the *active observer*. The off-axis model
is retained, with narrowed scope, as the **capture model of static stimuli**
(photographs and existing renders), whose convergence is frozen into their
pixels.

The justification, in priority order:

1. **The SO(3) argument.** A rotation lives in SO(3) and is independent of the
   projection surface. The whole model therefore lifts to a spherical or
   omnidirectional sensor by swapping the projection underneath, with the
   oculomotor layer untouched. Frustum asymmetry is definitionally planar —
   there is no such thing as an off-axis frustum on a sphere — and cannot be
   lifted at all.
2. **Biological fidelity.** Rotation is what eyes do, and it makes
   `geometry/horopter.py` the correct horopter of the model rather than
   documentation of a divergence — closing the gap ADR-0007 item 4 left open.

Concretely:

- **`Fixation`**, a new frozen dataclass in `types.py`, carries oculomotor
  state as gaze, not as a pixel coordinate:
  `azimuth` (rad, + toward +X/right), `elevation_down` (rad, + downward /
  +Y — the sign is in the name because "elevation" alone is a sign-error
  trap), `vergence` (rad, total angle at the fixation point; 0 = infinity;
  must be ≥ 0, matching `rig_from_calib`'s no-diverged-rig stance). The head
  frame is pinned here: cyclopean origin, +X right, +Y down, +Z forward.
- **Torsion is determined, not stored.** `Fixation` exposes 3 DOF of gaze;
  the third rotational DOF of each eye is computed inside one function,
  `geometry.oculomotor.eye_rotations(rig, fixation)` — the only place gaze
  becomes SO(3) — by the binocular extension of Listing's law, **default L2**
  (each eye's Listing plane rotates temporally by ≈ μ/4 under vergence μ).
  *Declared open question:* L2 vs strict Listing (L1). Not cosmetic — they
  produce different vertical-disparity fields at eccentric near fixations —
  but switching is localised to `eye_rotations`, and the vertical-disparity
  field is the observable that would decide it (a future experiment).
- **`StereoRig` keeps anatomy** (`baseline`, `focal_px`, `principal_point`)
  **and keeps `vergence` with narrowed semantics**: the capture convergence of
  a static, off-axis-captured stimulus (Middlebury `doffs`, Blender
  `convergence_distance`) — frozen capture geometry, which genuinely is
  anatomy of the capture rig and not a state anyone can change.
  **Precedence rule:** a refixable scene has no capture convergence, so
  `RefixableScene` implementations **require `rig.vergence == 0`, validated at
  construction and in `render_at`**. The two vergence fields are therefore
  disjoint by domain — `rig.vergence > 0` only on static capture with no
  `Fixation`; `Fixation.vergence` only where `rig.vergence == 0` — and the
  ambiguity is unconstructible, not merely documented.
- **The single pixel→rotation boundary.** `next_fixation()` keeps returning a
  `(row, col)` target; the conversion to a rotation lives in exactly one
  function, `geometry.oculomotor.target_to_fixation(target_px,
  depth_at_target: Estimate, rig, current) -> (Fixation, vergence_variance)`.
  It must **not** take a bare float depth: the target is peripheral *by
  construction* — L6 selects for uncertainty — and ADR-0003 declares
  peripheral depth untrustworthy, so the returned `Fixation` is explicitly a
  **coarse prior that L5 corrects post-saccade**, with the belief's variance
  propagated first-order into the returned vergence variance (which sets the
  Kalman's post-saccade prior). A scalar depth parameter is an oracle-shaped
  hole and would reintroduce the exact defect this ADR exists to remove.
- **Rectify by default** (declared open question, see Consequences): because
  fixation is a pure rotation about each optical centre, the raw→rectified map
  is a per-eye homography, exact and depth-independent. L2/L3 consume the
  rectified pair; every matcher keeps searching along scanlines by
  construction, untouched.
- **Cross-fixation belief** lives in L4: `scaling.belief.CyclopeanBelief`, an
  `Estimate` of inverse depth on a fixed angular grid in the cyclopean head
  frame, fused recursively per fixation. Its weighting function is a
  **constructor parameter** (`weight_fn`, default = `fuse_mle` precision
  weighting), not hardcoded — see Consequences for why.
- **Vertical disparity is henceforth a CUE**, not only a nuisance: under
  rotation it is real, grows with eccentricity and vergence, and is a
  candidate L4 input for viewing distance. (MiddEval3's calibration already
  ships measured `dyavg`/`dymax`, parsed at `scenes/middeval3.py:72-77` — a
  concrete hook.)

**What would have to change for this same `Fixation` to drive a renderer.**
Today the analysis direction consumes it: L3 inverts a pair rendered at a
tracked fixation. For L1 to *produce* the pair instead, a renderer needs only
the per-eye extrinsics from the same `eye_rotations(rig, fixation)` — exported
as camera rotations — and a `RefixableScene.render_at(rig, fixation, rng)`
implementation; nothing about `Fixation` itself changes, which is the test
that the abstraction is right: both directions consume it unchanged. A real
eye tracker supplies 2 DOF of gaze per eye and no torsion; of the two torsion
options considered, only **torsion-determined** survives that constraint — a
free-torsion `Fixation` could never be populated from tracker data in either
direction.

**What would have to change for an omnidirectional sensor.** Only the
pixel↔ray conversions: the unprojection inside `target_to_fixation` and the
projection/rectification functions swap their camera model. `Fixation`,
`eye_rotations`, the torsion law, the L5 filter, and the L6 policy are
expressed in angles and rotations and do not change. This paragraph is the
acceptance test of the decomposition: if adding a spherical sensor touches
anything beyond those functions, the abstraction was wrong.

## Alternatives considered

- **Gaze fields on `StereoRig`.** Rejected: anatomy is constant over a trial
  while oculomotor state changes per saccade. A frozen rig forces
  reconstructing the whole rig each fixation, breaks anything keyed on rig
  identity, and conflates what L5 estimates (state) with what L5 must never
  touch (anatomy).
- **Store the per-eye rotation pair (6 DOF) as the state.** Rejected:
  overcomplete — Listing-violating states become representable and silently
  constructible; un-populatable from an eye tracker; and it pushes the torsion
  decision into every constructor instead of one function.
- **Fixation as a pixel coordinate (+ depth).** Rejected: definitionally
  planar — exactly the property that blocks the omnidirectional lift — and it
  keeps the pixel→rotation conversion smeared across call sites instead of in
  one function.
- **3-DOF-free torsion.** Rejected: fails the eye-tracker constraint, admits
  non-physiological vertical-disparity fields, and grows the L5 state for no
  measurable benefit.
- **Remove `vergence` from `StereoRig` now.** Rejected on the frozen-capture
  argument above: for a photograph the convergence is capture anatomy. (The
  cost — 42 fixture-consuming tests, 7 inline constructions, 2 loaders, 3
  scripts, 3 experiment runners — is why it is also not worth doing
  opportunistically; experiment runners are editable without retro-altering
  SHA-pinned findings, but there is no need.)
- **Match in 2D on the raw pair instead of rectifying.** Not rejected —
  **deferred as a declared open question** ("the rectification fork").
  Biologically closer, but costs ×(2V+1) for a vertical search range V and
  changes every `DisparityMatcher`. Default is RECTIFY; the deciding
  experiment is rectified-vs-2D matching on toed-in stimuli at high
  eccentricity and vergence, where the two genuinely diverge.
- **Keep off-axis and bolt a gaze offset onto it** (ADR-0007's "correction
  term", revisited). Rejected again, for ADR-0007's own reason: the right
  move is the rotation model derived properly, not a fudge factor.

## Consequences

- **Vertical disparity becomes real** and grows with eccentricity and
  vergence. Every matcher in `inference/` searches along scanlines by
  construction, which is why rectification sits between the stimulus and
  L2/L3 (two H×W masked bilinear warps per fixation; ADR-0002 applies to the
  warp). Bare "disparity" henceforth means **pixels in the rectified frame**
  — numerically identical to today's convention for every static stimulus, so
  no second convention is introduced; raw-frame quantities are always named
  (`vertical_disparity`), never bare "disparity".
- **Static stimuli degrade, not raise.** Middlebury, MiddEval3, and existing
  Blender renders cannot be re-fixated; they run the static path at
  `Fixation.forward(rig.vergence)`. exp001–exp007 findings stand as recorded:
  the exp003/exp004 renders were made and logged as `OFFAXIS` in their
  `rig.json` (ADR-0007's verification hook doing its job), are static, and
  remain internally consistent stimulus/model pairs under the retained
  off-axis capture model.
- **Recursive fusion inherits an anti-calibrated variance channel, and the
  anti-calibration is conditional on contrast, not global.** exp006
  (`findings.md:83-86`): at **high-contrast** half-occlusions the
  occluded/matched variance ratio is median **0.254**, below 1.0 in 7 of 8
  scenes and hard-inverted (≤ 0.29) in five; at **low-contrast**
  half-occlusions it is median **1.28**, at or above 1.0 in six scenes —
  inflated variance where evidence is genuinely absent, exactly as designed.
  exp004 agrees, with the honest spread stated: its **0.324** is the block
  matcher's *median* over per-scene ratios spanning **0.059–1.119**
  (`findings.md:69-70`), and its contrast control found variance in
  high-contrast occlusions *below* the matched median in all eight scenes
  (8.3× lower on the median scene, up to 34.5×). SGBM's ratio of 1.0 is
  **vacuous by construction** — it returns a constant variance, so it
  "passed" a test it could not fail (`findings.md:158`) — and is evidence
  about nothing. Hallucination ran 0.826 (exp004, block) to 0.914 (exp006).
  **The mechanism is why this matters for a closed loop:** exp004 records
  that the inversion concentrates where contrast is high — "exactly what a
  saliency-driven gaze policy (L6) selects for … the pixels L6 will
  preferentially fixate" (`findings.md:115,219-220`). So L6 is not
  incidentally exposed to the inverted region; it is **drawn** to it, and
  recursive fusion **compounds** what it finds there: N observations of a
  biased estimate with underestimated variance drive posterior variance
  toward σ²/N, so the belief becomes arbitrarily confident in the wrong
  depth, and each additional fixation on a high-contrast occlusion boundary
  makes it worse. That drawn-to-the-inversion loop is the **motivation for
  exp008**, which measures it; nothing is fixed here.
  `CyclopeanBelief(weight_fn=...)` is the seam that makes the eventual fix a
  one-argument change rather than a rewrite.
- **ADR-0003's linearisation bound was derived under off-axis geometry**; the
  peripheral error model changes under rotation. Its findings stand as
  recorded, but quantitative peripheral-depth claims under Fixation-driven
  geometry need the bound re-derived first.
- `geometry/horopter.py` stops being an aspiration: the Vieth–Müller circle
  is the zero-disparity locus of the new model, and its docstring and
  `docs/architecture.md`'s caveat flip accordingly.
- The framework's biological claim, weakened in ADR-0007's Consequences,
  strengthens again — and the paper's statement of it must be updated in the
  same direction.

## Verification

Pinned by the migration's tests (see `docs/plans/fixation-migration.md`):

- Zero disparity **on the Vieth–Müller circle** under the toed-in projection —
  a planar-locus implementation fails it. (`test_zero_disparity_on_the_horopter`
  continues to pin the *retained* off-axis capture model.)
- Analytic torsion pins: symmetric horizontal fixation → yaw-only, zero
  torsion, zero vertical disparity on the horizontal meridian; eccentric near
  fixation → the L2 μ/4 tilt. A sign error flips the vertical-disparity field
  and fails these.
- First-order agreement between the rectified toed-in pair and the off-axis
  model near the axis at forward fixation — catches a wrong rotation
  direction.
- Belief frame-invariance under refixation — catches storing belief in a
  retinal frame.
- The end-to-end closed-loop test: two fixations on the same refixable-RDS
  world, belief frame-invariant, disparity at the second fixation's fovea
  improved — the only test that composes `render_at` → rectify → L3 → L4 →
  belief → `target_to_fixation`, and the one that catches wiring errors no
  per-component analytic test can.
