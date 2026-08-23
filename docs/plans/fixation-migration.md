# Migration plan: fixation as oculomotor state

Companion to [ADR-0013](../decisions/0013-fixation-as-oculomotor-state.md) and
the [draft issue](../issues/fixation-as-oculomotor-state.md).
Branch `feat/fixation-state`.

**Contract: the suite is green at every step.** Each step is one commit;
`pytest -q` (209 tests at the time of writing, all passing), `ruff check src
tests`, and `mypy src` pass after each. Every step is additive — a new type,
new functions, an optional field with a default, a new Protocol — so **0 of
the 209 existing tests change**; each step ships its own new tests.

## Order

1. **Docs (done in this change).** ADR-0013, the draft issue, this plan.
   No code.
2. **`types.py`: `Fixation`.** Frozen dataclass — `azimuth`,
   `elevation_down`, `vergence` (all rad; head frame +X right, +Y down,
   +Z forward); validation `vergence >= 0` and all fields finite;
   `Fixation.forward(vergence)`. Unit tests: validation, frozen-ness,
   `forward()`.

   *Declared open question — angle wrapping and equality.* Two `Fixation`s
   differing by 2π are the same oculomotor state but unequal as frozen
   dataclasses. Equality stays structural for now (pinned by
   `test_fixation_equality_is_structural_not_angular`, which fails if
   wrapping is ever added casually). This first bites at step 9+, where
   L6's `visited` list and inhibition of return move from pixel targets to
   gaze space — and it likely dissolves there rather than here: inhibition
   of return is metric (a radius), so L6 needs an angular-distance
   function, not equality, and that function handles 2π by construction.
   Resolve when step 9 lands; candidate homes are an angular-distance
   helper in `geometry/oculomotor.py`, never a custom `__eq__`.
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
5. **`geometry/oculomotor.py`: `target_to_fixation`.** The single
   pixel→rotation boundary. Takes the belief `Estimate` at the target (never
   a bare float — ADR-0013), returns `(Fixation, vergence_variance)`. Tests
   include first-order variance propagation.
6. **`geometry/rectify.py`.** Exact per-eye rotation homographies
   `H_e = K R_rect R_eᵀ K⁻¹` + ADR-0002-masked bilinear warp (masks warp
   nearest-neighbour, validity masked before mixing). Round-trip tests.
7. **`scenes/base.py`: `RefixableScene` Protocol** with the
   `rig.vergence == 0` contract, plus `StereoStimulus.fixation:
   Fixation | None = None` (`None` = static off-axis capture; every existing
   constructor call is unchanged). Tests: Middlebury / Blender / legacy RDS
   are **not** instances; the loop driver's static degradation path is taken
   (`Fixation.forward(rig.vergence)`, never a raise); `render_at` on a
   converged rig raises `ValueError`.
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
    `docs/decisions/README.md` index updated — 0013 added, 0007 marked
    superseded, and the stale 0009–0012 rows backfilled (an index is not a
    decision; the append-only rule protects decisions, not the table of
    contents).

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
