# DRAFT ISSUE (not posted) — Fixation as oculomotor state: close the L5/L6 loop

Labels: `feat`, `L1 geometry`, `L5 control`, `L6 policy`, `scenes`
Branch: `feat/fixation-state` · ADR: [0013](../decisions/0013-fixation-as-oculomotor-state.md) (supersedes ADR-0007)
Migration plan: [`docs/plans/fixation-migration.md`](../plans/fixation-migration.md)

## The change

The active loop in `scripts/demo_active_stereo.py:100-149` does not close: no
action changes any subsequent observation. Saliency is computed once outside
the loop; nothing is re-rendered or re-matched; the vergence measurement reads
ground truth (`stim.disparity`) with a hardcoded variance of 0.25; the Kalman
state feeds no computation. The type-level cause: `StereoRig` has `vergence`
but no gaze direction, and `Scene.render(rig, rng)` cannot express "this world
seen from fixation F".

Per ADR-0013, **fixation becomes a rotation of each eye about its optical
centre** (toed-in, Vieth–Müller), carried by a new `Fixation` type
(`azimuth`, `elevation_down`, `vergence`; torsion determined by the binocular
Listing law inside the single `eye_rotations` function, with the tilt
coefficient `k` a parameter — default 0.25, strict Listing at `k = 0` — per
ADR-0014, which refines ADR-0013's declared L1/L2 open question into a
measurable sweep). The off-axis model is retained as
the capture model of static stimuli; `rig.vergence` narrows to "capture
convergence", and any `RefixableScene` requires `rig.vergence == 0` so the two
vergence fields are disjoint by domain.

New pieces, in dependency order: `Fixation` (types) → `eye_rotations`,
toed-in projection with vertical disparity, `target_to_fixation`
(the one pixel→rotation boundary; takes the belief `Estimate`, returns a
coarse-prior `Fixation` plus its vergence variance), `rectify` (exact
rotation homographies) → `RefixableScene` Protocol + static degradation →
`CyclopeanBelief` in L4 (`weight_fn` parameterised) → refixable RDS synthesis
(world-frame surface, surface-attached hash texture, backward warp into
rectified geometry) → closed-loop demo.

## Hypothesis (what makes this falsifiable)

With one refixable scene, a second fixation chosen by the policy carries new
information: the disparity estimate at the second fixation's fovea, after
belief fusion, is strictly better than the first view's estimate at that same
location. If it is not — if refixation does not improve foveal disparity on a
clean RDS — the loop is still not closed and the change has failed its own
premise.

## Acceptance criteria

One per migration step (see the plan for the full order); the suite is green
after every step, `ruff` and `mypy src` included.

1. `Fixation` exists, frozen, validated (`vergence >= 0`), with
   `Fixation.forward()`; head-frame convention documented with units and
   signs.
2. `eye_rotations(rig, fixation, k=0.25)` is the only code that produces
   SO(3) from gaze; torsion is determined, not a stored field, and the
   Listing coefficient `k` is a parameter (ADR-0014): default 0.25, strict
   Listing at `k = 0`, no L1/L2 branch anywhere.
3. Toed-in binocular projection produces horizontal **and** vertical
   disparity; the Vieth–Müller circle is its zero-disparity locus.
4. `target_to_fixation` accepts an `Estimate` (never a bare float) and
   returns `(Fixation, vergence_variance)`; variance propagation is tested.
5. Rectification is an exact per-eye homography with ADR-0002-masked warps.
6. `RefixableScene` exists; Middlebury/Blender/legacy-RDS are **not**
   instances and degrade to the static path; `render_at` on a converged rig
   raises `ValueError`.
7. `CyclopeanBelief(weight_fn=...)` fuses across fixations in the head frame;
   the default reproduces `fuse_mle`; a custom `weight_fn` is honoured.
8. The demo's oracle readout is gone: `active_loop` consumes the L3 estimate.
9. A refixable RDS renders **the same world** at two fixations: same world
   point → same dot value; occlusion structure consistent with the surface;
   `autostereogram_check` passes.
10. The end-to-end closed-loop integration test passes (below).
11. `render_stereo.py` supports `--convergence-mode {OFFAXIS,TOE}` and records
    the actual mode; loaders branch on it; docs and the ADR index updated.

## How the suite catches a wrong implementation

- **Wrong locus (planar instead of toed-in):** the projection test requires
  zero disparity *on the Vieth–Müller circle*; a shifted-frustum
  implementation puts zeros on a fronto-parallel plane and fails it.
- **Torsion sign or law error:** analytic pins — `k = 0` must reduce to
  strict Listing; symmetric horizontal fixation must give yaw-only rotations,
  zero torsion, and zero vertical disparity on the horizontal meridian at any
  `k`; eccentric near fixation must give elevation-dependent torsion
  (intorsion upward, extorsion downward, opposite between the eyes) with the
  default `k = 0.25` tilt. A flipped sign inverts the vertical-disparity
  field and fails the pinned values — and ADR-0014's `k`-sweep doubles as the
  end-to-end audit: a residual-vertical-disparity minimum away from 0.25
  indicates a sign or axis error in `eye_rotations`.
- **Wrong rotation direction / frame mix-up:** the rectified toed-in pair must
  reproduce the off-axis disparity to first order near the axis at forward
  fixation.
- **Belief stored in the wrong frame:** frame-invariance test — updating from
  two fixations of the same world must commute; a retinal-frame belief fails
  after the first saccade.
- **Oracle regression:** `target_to_fixation`'s signature takes an `Estimate`;
  a bare-float depth cannot type-check, so the line-125 defect cannot be
  reintroduced silently.
- **Wiring errors between correct components:** the closed-loop test — two
  policy-chosen fixations on one refixable-RDS world; assert (i) the belief is
  frame-invariant across the saccade and (ii) foveal disparity error at the
  second fixation improves over the first view's estimate there. Every
  per-component test can pass while `render_at` → rectify → L3 → L4 → belief →
  `target_to_fixation` is mis-composed; only this test exercises the
  composition.

## Out of scope (follow-ups)

- Gaze-contingent Blender rendering (explicit per-eye extrinsics exported from
  `eye_rotations`; Blender's native `TOE` is yaw-only/zero-torsion and only
  correct for symmetric horizontal fixation).
- 2D matching on the raw pair — "the rectification fork", ADR-0013's declared
  open question, deserving its own experiment.
- Removing `StereoRig.vergence` entirely.
- exp008: measure the compounding of the anti-calibrated variance channel
  under recursive fusion, and calibrate `weight_fn`. The anti-calibration is
  conditional on contrast — high-contrast half-occlusions invert, low-contrast
  ones inflate safely (exp006 `findings.md:83-86`, exp004 contrast control) —
  and high contrast is what L6 preferentially fixates (exp004
  `findings.md:115,219-220`), so the policy is drawn to the inverted region
  rather than incidentally exposed to it.
- Vertical disparity as an L4 viewing-distance cue (MiddEval3's
  `dyavg`/`dymax` already parsed at `scenes/middeval3.py:72-77`).
