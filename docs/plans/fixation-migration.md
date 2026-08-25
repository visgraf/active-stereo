# Migration plan: fixation as oculomotor state

Companion to [ADR-0013](../decisions/0013-fixation-as-oculomotor-state.md) and
the [draft issue](../issues/fixation-as-oculomotor-state.md).
Branch `feat/fixation-state`.

**Contract: the suite is green at every step.** Each step is one commit;
`pytest -q`, `ruff check src tests`, and `mypy src` pass after each. Every step
is additive — a new type, new functions, an optional field with a default, a new
Protocol — so **0 existing tests change**; each step ships its own new tests.

**Quote the delta, not the absolute.** Test counts here are
**environment-conditional**: six test modules `importorskip` optional extras, so
32 tests are collected only with the `cv` extra installed. Measured at step 5 —
with `cv`: 280 on `main` (2d5ce20) → 331; `[dev]` only: 248 → 299 (298 passed,
1 skipped). **The invariant across both is the delta: step 5 adds 51 tests and
changes 0 existing ones.** An unconditioned absolute cannot be reproduced by a
second environment, which is how this line was previously wrong.

## Order

1. **Docs (done in this change).** ADR-0013, the draft issue, this plan.
   No code.
2. **`types.py`: `Fixation`.** Frozen dataclass — `azimuth`,
   `elevation_down`, `vergence` (all rad; head frame +X right, +Y down,
   +Z forward); validation `vergence >= 0` and all fields finite;
   `Fixation.forward(vergence)`. Unit tests: validation, frozen-ness,
   `forward()`.

   *Declared open question — angle wrapping and equality. **Split at step 5**:
   one half is resolved, the other still belongs to step 9.* Two `Fixation`s
   differing by 2π are the same oculomotor state but unequal as frozen
   dataclasses. Equality stays structural (pinned by
   `test_fixation_equality_is_structural_not_angular`, which fails if wrapping
   is ever added casually).

   **RESOLVED at step 5 — wrapping at the pixel→rotation boundary.** This block
   said "first bites at step 9+"; it bit at step 5, on the *input* side.
   `target_to_fixation` takes a `current` fixation that can be hand-written or
   loaded from a config, so a wrapped elevation is reachable input.
   `is_forward_gaze` is therefore the **geometry** test
   (`cos(az)·cos(el) > 0`), not the angle test `abs(el) < pi/2`: the two
   disagree on wrapped input, and only the geometry test is right there
   (`el = 7.0` wraps to 0.7168 and is plainly forward). `target_to_fixation` is
   2π-invariant in `current.elevation_down` to floating-point precision, tested.
   Step 9 must not re-litigate this.

   *Why the earlier reasoning missed it:* the argument that constructed
   `Fixation`s are canonical (`atan2` returns in `(-pi, pi]`) is correct — for
   the **output** direction. Wrapping arrived on the **input** direction, which
   that argument does not cover. Same shape as the other misses this step: an
   argument sound in the direction it was aimed, applied to the direction it was
   not.

   **STILL OPEN for step 9 — structural equality and L6's `visited`.** When
   inhibition of return moves from pixel targets to gaze space, two states
   differing by 2π compare unequal. This likely dissolves there rather than
   needing a fix here: inhibition of return is metric (a radius), so L6 needs an
   angular-distance function, not equality, and that function handles 2π by
   construction. Candidate homes are an angular-distance helper in
   `geometry/oculomotor.py`, never a custom `__eq__`.
3. **`geometry/oculomotor.py`: `eye_rotations(rig, fixation, k=0.25)`.** The
   only place gaze becomes SO(3); torsion by the binocular Listing law with
   the tilt coefficient `k` as a **parameter, not a branch** (ADR-0014):
   `k = 0.25` default, `k = 0` is strict Listing. Tests pin analytic cases:
   `k = 0` reduces to strict Listing; symmetric horizontal fixation →
   yaw-only, zero torsion at any `k`; eccentric near fixation → the
   elevation-dependent torsion signs (intorsion for upward proximal gaze,
   extorsion for downward, opposite between the eyes). This step also
   **computes the L1-vs-L2 vertical displacement at the project's actual
   stimulus scales** — the quantity ADR-0014 deliberately left unrecorded —
   benchmarked against exp007's measured MiddEval3 `dyavg` (up to ≈ 0.5 px
   at Q) and the matchers' median |Δd| (≈ 0.07 px best-case RDS, exp006;
   ≈ 0.2–0.5 px on well-behaved scenes).

   *Construction (plan-review outcome, 2026-08-23):* tilted-Listing
   displacement form `R_e = A(p_e→g_e) · A(ẑ→p_e)`, shortest arcs via the
   trig-free Rodrigues form. The second factor is the primary orientation;
   omitting it (the shortest arc alone) mis-points the optical axis by
   ≈ k·μ — 13–32 px at project scales — and is pinned by the
   gaze-lines-intersect test. The cyclopean direction composes in
   **Helmholtz** order (ADR-0015: the plane of regard is exactly the
   elevated plane for every azimuth), which makes `fixation_distance`
   closed-form via a Vieth–Müller chord. Fixation azimuth is
   domain-restricted to (−π/2, π/2): beyond it the chord lands on the
   minor arc, where the inscribed angle is π−μ, and the returned geometry
   would be silently wrong — the functions raise instead.
4. **`geometry/projection.py` (additive): toed-in binocular projection.**
   Forward model for `(rig, fixation)` producing horizontal **and** vertical
   disparity fields. Payoff tests: zero disparity on the Vieth–Müller circle
   (`horopter.py` becomes the correct horopter of the model, closing
   ADR-0007 item 4); first-order agreement with the retained off-axis model
   near the axis at forward fixation. The existing `depth_to_disparity` and
   its tests (including `test_zero_disparity_on_the_horopter`) are untouched:
   they pin the retained off-axis *capture* model.

   ⚠ *Vacuous-pass hazard (flagged at step 3).*
   `horopter.vieth_muller_radius(rig)` reads `rig.vergence`. Under ADR-0013
   any `RefixableScene` has `rig.vergence == 0`, so the helper returns `inf`
   and `vieth_muller_circle` degenerates to the plane at infinity. If this
   step's zero-disparity-on-the-VM-circle acceptance test reaches for the
   helper unchanged on a refixable rig, it compares against a degenerate
   horopter and can pass vacuously — the exp001 exactly-0.0-foveal-MAE
   failure shape. **The load-bearing protection is the precondition
   assertion in the acceptance test itself: assert `np.isfinite(R)` and
   `μ > 0` before any disparity is compared, so degeneracy fails loudly
   instead of passing.** The API accommodation — an optional
   `fixation: Fixation | None = None` parameter on `vieth_muller_radius` /
   `vieth_muller_circle`, with `fixation.vergence` overriding
   `rig.vergence` when given (additive; existing calls and tests
   untouched) — is convenience only: an optional argument that silently
   changes which field is authoritative is its own hazard, and it must not
   substitute for the assertion.
5. **`geometry/oculomotor.py`: `target_to_fixation`. (done)** The single
   pixel→rotation boundary. Takes the belief `Estimate` **field** at the target
   (never a bare float — ADR-0013; field-shaped because `StereoRig` carries no
   image dimensions, so nothing else makes the bounds check possible), returns
   `FixationProposal | TargetRefused`. Scope grew by `rectification_rotation`
   and `is_forward_gaze`; the result types live in `types.py` so L4/L5/L6 can
   consume them without a cross-layer import.

   Full record, including three defects found while verifying:
   [step-5 notebook entry](../lab-notebook/2026-08-25-step-5-target-to-fixation.md).
   The `R_rect` member choice is
   [ADR-0017](../decisions/0017-rectification-rotation-member.md).

   *Declared open questions — all three resolved in the step-5 plan, kept here
   as written so the trace survives.* They were unverified hypotheses from Chat
   (2026-08-25), carried into this file rather than left in the prompt they
   arrived in, per the CLAUDE.md §5 handoff contract.

   a. **RESOLVED — refuse on data quality, raise on caller error.** Refusal is
   a `TargetRefused` carrying a **`frozenset[RefusalReason]`**, not one reason:
   a target can be both `TOO_NEAR` and `BACKWARD_GAZE`, and collapsing
   co-occurrence is the same reduction as collapsing distinct kinds into a bare
   `None`. Original text: a pixel target carrying a bad
   depth estimate can yield `vergence <= 0`, or an azimuth outside
   `Fixation`'s `(-pi/2, pi/2)` domain (`geometry/oculomotor.py`,
   `require_forward_azimuth`). Raising kills the active loop on a single bad
   estimate; returning a refusal lets L6 pick another target. The choice is
   not local — it propagates into L6's policy, which has to know whether a
   target can be refused at all, so it cannot be deferred to the call site.

   b. **RESOLVED — documented, and pinned by a test that can fail** (linear
   pass-through across 8 decades; a docstring cannot fail). Original text:
   **the variance being propagated is the anti-calibrated one**
   (exp004, exp006). First-order propagation can be *correct* while its input
   is *wrong*, and downstream the two are indistinguishable. The
   `vergence_variance` docstring must say so explicitly, or step 8's
   `CyclopeanBelief` consumes it as trustworthy — which is exactly the
   compounding ADR-0013 flagged and exp008 exists to measure. A correct
   derivative of a miscalibrated quantity is still miscalibrated.

   c. **PARTLY ARRIVED — and the original framing had the direction wrong.**
   An earlier revision of this sub-block said "it did not arrive"; that
   contradicted step 2's block, which records that it did. Three separate things
   were being run together:

   1. *Output direction — did not arrive.* Constructed `Fixation`s are canonical
      (`arcsin` and `atan2` ranges), so nothing step 5 **produces** is ever
      wrapped. The original argument was sound — for this direction only.
   2. *Input direction — arrived, and is resolved at step 5.* `current` is an
      **input**: it can be hand-written or loaded from a config, so a wrapped
      elevation is reachable. Hence `is_forward_gaze` is the geometry test
      `cos(az)·cos(el) > 0` rather than `abs(el) < pi/2`, and
      `target_to_fixation` is 2π-invariant in `current.elevation_down`, tested.
      **Step 9 must not re-litigate this half**; see step 2's block, which is
      split accordingly.
   3. *The elevation **domain** hole — a third thing entirely*, neither wrapping
      nor equality: `Fixation(0.1, 2.0, 0.064)` is admitted and points backward.
      Closed additively by `is_forward_gaze`. Do not merge it into the wrapping
      category — it is a different failure and took a different fix.

   Original text, retained for the trace: **Step 2's declared open question may
   arrive here, not at step 9+.** Step 5 is the first place `Fixation`s are
   *constructed* rather than hand-written, so it is the first place a wrapped or
   out-of-domain angle can be produced by code rather than by a test author.
   ~~Step 2's block still reads "resolve when step 9 lands" and is left as
   written~~ — no longer true: that block was split at step 5, and its input-side
   half is resolved there.
6. **`geometry/rectify.py`.** Exact per-eye rotation homographies
   `H_e = K R_rectᵀ R_e K⁻¹` (raw eye → rectified) + ADR-0002-masked bilinear
   warp (masks warp nearest-neighbour, validity masked before mixing).
   Round-trip tests.

   ⚠ *This formula was corrected at step 5.* It previously read
   `K R_rect R_eᵀ K⁻¹`, which is wrong in **factor order** — measured 2.7e+04 px
   eye→rect and 2.7e+02 px rect→eye, i.e. incorrect in both directions under
   either reading of `R_rect`. `R_rect` itself was an **undefined symbol** here
   until step 5 defined it ([ADR-0017](../decisions/0017-rectification-rotation-member.md),
   rect → head). **A round-trip test cannot catch this class of error** —
   projecting and unprojecting with the same matrix is exact under any
   invertible convention — so this step needs an independent-projection check,
   not only the round trips listed above. Full record:
   [step-5 notebook entry](../lab-notebook/2026-08-25-step-5-target-to-fixation.md).

   Also from step 5: `R_rect` is `k`-independent but `H_e` is not, and the
   residual vertical disparity measures **assumed-vs-actual `k` mismatch**,
   which is identically zero when the imaging and rectifying `k` agree — as they
   do in the current pipeline. It is *not* a free measurement of ADR-0016's open
   question. Report the mean and the mean-removed rms **separately**: the
   residual is dominated by a common mode (+2.55 px of 2.73 px rms).

   🔒 **REQUIRED — the static path must warp by the identity.** `rig.vergence
   != 0` ⇔ static off-axis capture ⇔ the pair is **already rectified** ⇔ the
   correct warp is the **identity**. Enforce it so the wrong thing cannot be
   constructed, in the shape of step 7's `render_at` raising on a converged rig —
   not documented as a caution. Applying `H_e` to an already-parallel pair
   assumes a toed-in capture that never happened, destroys row-wise
   correspondence and biases depth, and does both silently; `exp001`–`exp007` are
   the baseline it would corrupt. Measurements:
   [step-6 preamble](../lab-notebook/2026-08-25-step-6-preamble.md) §1.

   *Declared open questions (step-6 preamble, 2026-08-25).* Settle these **in the
   step-6 plan**, not while implementing — same discipline as step 5's block, and
   for the same reason: otherwise whoever reaches one first decides it, and it is
   recorded nowhere. Numbers live in the notebook entry, not here.

   a. **Rectification converts vertical disparity from a measurement into an
   assumption.** `d_v` is identically zero in the rectified pair — exactly, every
   point, every `k` — so ADR-0013's Consequences assigning it to L4 as a
   viewing-distance cue, with the MiddEval3 `dyavg`/`dymax` hook
   (`scenes/middeval3.py:72-77`), has **no input** under rectify-by-default. What
   survives is the residual when assumed and actual geometry disagree: a
   **fixation-error signal, an L5 quantity**, not an L4 distance cue.

   *This is a second question and ADR-0013 merges them.* ADR-0013:153-158 frames
   the fork as **matching** — 2D vs 1D search, ×(2V+1), every `DisparityMatcher`.
   Whether the cue is *available* is a different axis, and is not mentioned there.

   *Tension, recorded not resolved:* ADR-0013's Consequences say the biological
   claim "strengthens again", and human vertical disparity is a cue **precisely
   because eyes do not rectify**.

   *The cue is lost from the PIPELINE, not the CODEBASE* — `toed_in_disparity`
   (`projection.py:187`) still returns `(d_h, d_v)` on the raw pair. Said here so
   Phase C does not spend a session on archaeology.

   *What would resolve it:* ADR-0013's own deciding experiment — rectified-vs-2D
   matching on toed-in stimuli at high eccentricity and vergence — extended to ask
   whether the residual carries distance information, not only whether matching
   degrades.

   b. **The static-path guard is not an open question.** See the 🔒 requirement
   above; it has a specified fix and must not be reopened as a choice.

   c. **Validity gains a source — principle settled, mechanism open.** After the
   warp each eye has three kinds of invalid: scene occlusion; behind-the-eye
   geometry (eye-indexed, `projection.py:94-113`); and **pixels sourced outside
   the raw image**.

   *Settled, not to be relitigated:* warp-invalid is **its own mask**. ADR-0011
   ("Missing ground truth is a fourth mask, not a value of the other three") and
   CLAUDE.md §3's mask-before-mixing rule fix this between them. Collapsing
   warp-invalid into occlusion-invalid makes half-occlusion statistics wrong at
   the border, and half-occlusions are exp008's hypothesis — but that is the
   *consequence* of the settled principle, not an argument still to be had.

   *Open — the mechanism only:* does the warp **return** the mask separately, or
   write `nan` into the warped image and let consumers recover it with
   `np.isfinite`? Both honour the principle; they differ in whether a consumer can
   distinguish warp-invalid from occlusion-invalid *after the fact*, which is
   exactly what exp008's counting needs.

   *What would resolve it:* a decision at step 6 taken with exp008's counting in
   view, rather than after it.

   d. **Resampling changes effective sample independence, and the sign of the
   variance error depends on the estimator** — count-based underestimates,
   curvature- and spread-based inflate, SGBM's constant is blind. A Phase C input
   (`docs/roadmap.md:22`), not a defect. Filed as **#44**, marked derived from
   reasoning rather than measured — nobody has run it.

   e. **Does rectification consume the commanded fixation or L5's estimate?**
   Every step-6 unit test images and rectifies at the *same* fixation, so `H_e` is
   exact and the residual is identically zero. **That may also be true of the
   closed loop**: the renderer renders at the *commanded* fixation, so if
   rectification uses the same one, the residual is zero **by construction** —
   there is no plant-noise model. A fixation-error tolerance binds only if
   rectification consumes the *estimate*.

   **Coupled to (a).** Rectifying at the estimate is what makes the
   fixation-error residual observable; rectifying at the command is what makes it
   vanish. One answer decides both.

   *The tolerance is deliberately NOT measured yet.* Three rounds went into it
   before this was noticed. *Measure before repair* (roadmap) has as its
   corollary: **do not measure what may be structurally zero.** A step-11
   acceptance criterion on it would be the exp001 exactly-0.0-foveal-MAE shape
   this plan already flags at step 4.

   *Two results from those rounds are kept, because they are about method rather
   than the number.* **The support rule:** a residual must be measured
   **in-bounds after the warp, both eyes** — a pixel that warps out of frame is
   not available to the matcher, so including it measures a residual no matcher
   can see. **And the `el = 0` rule attaches here:** at sagittal gaze the foveal
   residual is zero *by symmetry*, so a step-11 criterion evaluated there cannot
   fail. Step 5's standing rule applies — every geometric test uses `el != 0`
   **and** `az != 0`. Third occurrence of that hole.

   *What would resolve it:* deciding commanded-vs-estimate. The tolerance becomes
   a real quantity only on the estimate branch.
7. **`scenes/base.py`: `RefixableScene` Protocol** with the
   `rig.vergence == 0` contract, plus `StereoStimulus.fixation:
   Fixation | None = None` (`None` = static off-axis capture; every existing
   constructor call is unchanged). Tests: Middlebury / Blender / legacy RDS
   are **not** instances; the loop driver's static degradation path is taken
   (`Fixation.forward(rig.vergence)`, never a raise); `render_at` on a
   converged rig raises `ValueError`.

   ⚠ *Check whether step 6's static-path guard is still reachable.* Step 6
   enforces "`rig.vergence != 0` ⇒ warp by the identity" as a **runtime** check.
   This step puts `rig.vergence == 0` in the **type system**, so if rectification
   only ever applies to refixable scenes, that check becomes **unreachable** — a
   dead guard, and 003's `160.0 > 100.0` row is what that looks like when nobody
   notices. Either promote it to structural and delete the runtime check, or keep
   the check and record why it is still reachable. Do not leave it untested and
   assumed live.
8. **`scaling/belief.py`: `CyclopeanBelief(weight_fn=...)`.** Inverse depth
   on a fixed angular grid in the cyclopean head frame; recursive
   reprojection + fusion; `weight_fn` defaults to `fuse_mle` precision
   weighting and is a constructor parameter (ADR-0013: the anti-calibrated
   variance channel compounds under recursion; exp008 will measure it, and
   the parameter keeps the fix a one-argument change). Tests: default
   reproduces `fuse_mle`; custom `weight_fn` honoured; frame invariance under
   refixation.
9. **`scripts/demo_active_stereo.py`, part 1: remove the oracle.** Pass the
   L3 `disparity` estimate into `active_loop` in place of
   `Estimate(stim.disparity, 0.25)` — honest measurement on the static path.
   No tests cover scripts; still green.
10. **Refixable RDS synthesis** (`scenes/rds.py` or a sibling
    `scenes/rds_world.py`). World-frame surface (the depth function
    reinterpreted over a cyclopean-frame grid); surface-attached
    deterministic texture — dot values keyed by `(seed, quantised world
    coordinate)` through a counter-based hash, so the same world point yields
    the same dot at every fixation (seed still injected explicitly; the
    no-global-rng rule holds); backward-warp synthesis **directly into each
    eye's rectified geometry**, avoiding the interpolation monocular cue.
    Implements `RefixableScene`; requires `rig.vergence == 0`. Unit tests:
    same world point → same dot value across fixations; occlusion structure
    consistent with the surface; `autostereogram_check` passes.
11. **End-to-end closed-loop test** (`tests/integration/`). Two fixations on
    the same refixable-RDS world: (i) the belief is frame-invariant across
    the saccade; (ii) the disparity estimate at the second fixation's fovea
    improves over the first view's estimate at that location. This is the
    acceptance test for the whole change — it composes `render_at` → rectify
    → L3 → L4 → belief → `target_to_fixation`, and catches wiring errors no
    per-component analytic test can. Demo part 2 lands here: per-iteration
    re-render, re-match, belief update, and saliency recomputed from the
    belief whenever the scene is refixable.
12. **Blender + docs.** `render_stereo.py --convergence-mode {OFFAXIS,TOE}`
    (default `OFFAXIS`); `write_rig` records the actual mode (today it
    hardcodes `"OFFAXIS"`) plus a fixation block under `TOE`;
    `rig_from_blender` / `BlenderRenderScene` branch on the recorded mode.
    `docs/architecture.md` horopter caveat rewritten; `horopter.py` docstring
    flipped ("this IS the model's horopter under Fixation-driven geometry");
    (The `docs/decisions/README.md` index clause that used to sit here is
    struck: the index is maintained continuously — 0013–0017 are present and
    0007 already reads "Superseded by 0013" — so it described work already
    done and would have sent someone hunting stale rows that no longer exist.
    An index is not a decision; the append-only rule protects decisions, not
    the table of contents, so it is updated in the step that adds an ADR.)

    **`CHANGELOG.md`: the whole fixation migration goes in here, at this step.**
    It has not been touched since the exp003 era and steps 3, 4 and 5 each
    skipped it. That is a standing omission, not step-5 drift — recorded as an
    explicit line so it is written once, deliberately, rather than accumulating
    silently.

## Deliberately out of scope

Gaze-contingent Blender rendering (Blender's native `TOE` is
yaw-only/zero-torsion — correct only for symmetric horizontal fixation;
eccentric renders need explicit per-eye extrinsics exported from
`eye_rotations`); 2D matching on the raw pair (the rectification fork,
ADR-0013's declared open question); removing `StereoRig.vergence`; exp008
(weighting calibration under recursive fusion).

## Invalidation audit

Nothing beyond ADR-0007 is invalidated. `test_zero_disparity_on_the_horopter`
pins the retained off-axis capture model and is kept as-is (its docstring
becomes model-scoped in step 4). ADR-0003's linearisation bound stands as
recorded but must be re-derived before quantitative peripheral claims under
toed-in geometry. exp001–exp007 findings stand: the exp003/exp004 renders are
`OFFAXIS`, recorded as such in `rig.json`, static, and never re-fixated.
