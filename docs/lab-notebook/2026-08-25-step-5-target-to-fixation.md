# 2026-08-25 — Step 5: `target_to_fixation`, and three defects found on the way

Branch `feat/target-to-fixation`, migration step 5, PR #37
([plan](../plans/fixation-migration.md)). Registered items are filed as
issues #38-#42; see §8. Third entry of this date; the others
are [the plane-of-regard optimum](2026-08-25-plane-of-regard-optimum.md) and
[toed-in projection](2026-08-25-toed-in-projection-and-item-4.md).

Step 5 lands ADR-0013's single pixel→rotation boundary. Every figure below is
computed from `activestereo` at this branch's HEAD; harnesses are stated inline
because the most instructive finding of this step is what happens when they are
not (§7).

Scope grew by one function: `rectification_rotation`, recorded as
[ADR-0017](../decisions/0017-rectification-rotation-member.md). `R_rect` existed
only as an undefined symbol in step 6's formula, and `target_to_fixation` cannot
unproject a pixel without knowing the orientation of the frame the pixel is in.

## 1. Verification ledger

Six derivations arrived from Claude Chat as hypotheses with pointers (CLAUDE.md
§5). All six verified against the files; three needed correction.

| # | Claim | Result |
|---|---|---|
| 1 | `R_rect` depends only on elevation | Confirmed. Both gaze lines lie in the elevated plane, max `abs(n·ĝ)` = **1.1e-16** over 45 `(az, el, mu)`. |
| 2 | Common orientation + centres along image x ⇒ `d_v ≡ 0` | Confirmed **exactly** (`0.000e+00`, not small), 75 × 300 points. Caveat below. |
| 3 | `az = arcsin(u_x)`, `el = atan2(u_y, u_z)` round-trips | Confirmed to **2.2e-16**. Consequence sharper than stated, below. |
| 4 | `mu = arctan(b·D·cos az / (D² − b²/4))` inverts `fixation_distance` | Confirmed to **2.2e-16**, against both `fixation_distance` and `atan2(abs(g_L × g_R), g_L · g_R)`. Branch hazard below. |
| 5 | Elevation domain hole | **Confirmed.** |
| 6 | Unprojection uses the left optical centre | Confirmed, **17.07 px** at the image centre. |

**Corrections made.**

*Item 1 — the sign, and then the sign back.* The incoming derivation said
`R_rect = R_x(elevation_down)`. Read against a textbook right-handed `R_x` that
is a sign error, and it was first recorded as such. That "correction" was itself
wrong: `tests/unit/test_oculomotor.py`'s `helmholtz_rotation` already defines
`Rx(el)` as `[[1,0,0],[0,ce,se],[0,-se,ce]]` with *positive* `el`, and ADR-0016
uses the same naming. Introducing the textbook convention would have been a
second convention for the same quantity (CLAUDE.md §4). The matrix was right all
along; only its *name* was in question, and the repo had already answered it.
Recorded because the failure mode — importing an external convention into a
codebase that has its own — is not visible from the matrix, which is identical
either way.

*Item 2 — "identically zero for all points" holds for all **imageable** points.*
Where a point falls behind one eye `d_v` is `nan`, not `0` (5 of 300 at
`el = −0.6`). That is ADR-0002-correct and matches `BinocularProjection`'s
eye-indexed validity, but a test asserting `d_v == 0` must mask first or it
asserts over `nan`.

*Item 3 — the consequence is stronger than "the guard never fires."*
`arcsin`'s range **is** `require_forward_azimuth`'s domain, so the azimuth guard
cannot fire on any *constructed* `Fixation`. It is vacuous **at this boundary** —
not useless; it still fires on hand-written states, three times in
`test_oculomotor.py:224-232`. The practical consequence is that it offers zero
protection where step 5 needs protection, which is why the new guard is additive
rather than a tightening.

*Item 4 — a branch hazard, not just an identity.* Plain `arctan` takes the wrong
branch for `D < b/2`: at `D = 0.9·(b/2)` it returns `mu = −1.4656`, which then
hits `Fixation.__post_init__`'s `vergence < 0` raise. A too-near target would
have **escaped as a `ValueError`** where the error contract requires a refusal.
The `D > b/2` check therefore runs before `Fixation` is constructed.

**Item 5 in full, because it is the reason a new guard exists.**
`Fixation(0.1, 2.0, 0.064)` — elevation past `pi/2` — is admitted by
`types.py:114-123`, which validates finiteness and `vergence >= 0` only. Then:

    fixation_distance -> 0.9947 m                     # no raise
    fixation_point    -> [0.0993, 0.8999, -0.4119]    # P_z < 0, behind the head
    eye_rotations     -> no raise; det = 1.0, orthonormality error 1.1e-16

A well-formed rotation pointing backward. `test_backward_gaze_raises_antiparallel`
catches only *exact* antiparallel (`Fixation(0.0, np.pi, 0.0)`, which reaches
`_shortest_arc`'s `1 + c < 1e-9` raise via the zero-vergence branch); nothing
between `pi/2` and `pi` was caught. Closed by `is_forward_gaze`, additively —
tightening `Fixation` would have broken the migration's green-at-every-step
contract.

Reachability, closed form, exact to **1.1e-16** over 144 cases and independent of
depth, column and azimuth:

    el_new = current.elevation_down + atan((row − pp_row)/f)

**An identity on the principal branch only, and the guard is the geometry test
rather than the angle test because of it.** `abs(el) < pi/2` and
`cos(az)·cos(el) > 0` agree everywhere except at the boundary *and* on wrapped
elevations, where they disagree outright: at `el = 7.0` (which wraps to 0.7168,
plainly forward) the angle test says backward and the geometry test says
forward. `is_forward_gaze` implements the geometry test, which is the one that
is right on wrapped input; verified against a wrap-then-test reference over
`el ∈ {0.3, 1.5, 1.6, 2.0, 3.0, 6.5, ±7.0}`, agreeing in all cases while the
angle test diverges in three.

Constructed fixations cannot reach a wrapped elevation — `atan2` returns in
`(-pi, pi]` — but `current` can be hand-written or loaded from a config, so this
is reachable input. `target_to_fixation` is **2π-invariant in
`current.elevation_down`** to floating-point precision — `el_cur = 7.0` and
`el_cur = 0.7168…` return `el_new` agreeing to **3.3e-16**, with azimuth and
vergence likewise — because the rectifier depends on elevation only through
`cos`/`sin`. *Not* bitwise: `cos(7.0)` and `cos(0.71681…)` are not the same
float, so the last ulp differs (`0.8263742195943581` vs `…79`). Recorded because
the first version of this claim said "bit-identical", read off a six-decimal
printout, and the exact-equality test failed. The closed form
above then reads `7.0 + atan(88/800) = 7.109560`, which is `0.826374 + 2π` — the
identity holds modulo 2π, and the returned value is on the principal branch.

Incidentally this is a partial answer to step 2's declared wrapping question in
the one place step 5 touches it: wrapping in `current` is not observable in this
function's output.

For `f = 800` and 480 rows the ray half-cone is `atan(240/800) = 16.70°`, so a
backward proposal is reachable in one step once `abs(el_cur) > 73.30°`. The branch
is live, not defensive.

## 2. Defect 1 — step 6's homography, wrong in factor order

`docs/plans/fixation-migration.md:121` read `H_e = K R_rect R_eᵀ K⁻¹`. Warping
200 points between the raw-left and rectified-left frames at
`Fixation(0.5, 0.4, 0.064)`:

| homography | eye→rect | rect→eye |
|---|---|---|
| `K R_rectᵀ R_e K⁻¹` (correct, eye→rect) | **9.1e-13 px** | 8.7e+03 |
| `K R_rect R_eᵀ K⁻¹` — as written | 2.7e+04 | 2.7e+02 |
| `K R_eᵀ R_rect K⁻¹` (correct, rect→eye) | 2.5e+04 | **3.4e-13 px** |

Wrong in **factor order**, not merely transposed: incorrect in *both* directions,
under either reading of `R_rect`. Corrected in the plan file.

**The round-trip acceptance test cannot catch this class.** Projecting and
unprojecting with the same matrix is exact under any invertible convention. Only
warping against an *independent* projection discriminates. This is why step 5
ships the principal-row anchor as a separate test, and why the negative controls
inject faults into the implementation rather than into both sides of the harness.
That distinction was itself got wrong once here: an early transpose control
reported "undetectable" because the harness transposed both sides.

Recorded rather than silently fixed, per ADR-0016's Alternatives: an in-place
edit leaves no trace that the formula was ever wrong, or that a whole test class
is blind to it.

## 3. Defect 2 — CLAUDE.md §3 asserts a false invariant about depth

§3 says depth `Z` is "metres, cyclopean frame". L4 returns `z` in the
**rectified camera** frame: for a rectified pair `d = f·b/z`, and
`disparity_to_depth` with `rig.vergence == 0` recovers `z_rect` to **5.6e-16**.

The two coincide **only at `elevation_down == 0`** — every stimulus in the repo
today, which is why nothing has caught it. At `az = 0.9, el = 0.8` they differ by
43 % (`z_rect = 0.387` vs `Z_cyc = 0.270`), and feeding the wrong one returns
`mu = 0.0953` instead of `0.0640` while azimuth and elevation still look nearly
right — the error hides almost entirely in vergence.

The conversion is **row-dependent**, not a constant cosine (verified to 1e-12;
the `+` form, which is how it arrived, misses by up to 0.48 m at `el = 0.9`):

    Z_cyc = z_rect · (cos el − ((row − pp_row)/f)·sin el)

Two further properties make this larger than naming a frame:

- Rectified-camera `z` is **fixation-dependent**: the same world point has a
  different bare `Z` at different fixations. Ground-truth comparison
  (`metrics/`, Middlebury and Blender GT in the capture frame) needs a stated
  frame once `el != 0`.
- The argument for the rectified reading is conditioned on `rig.vergence == 0`,
  which ADR-0013:76-81 requires of refixable rigs — and **no runnable path is one
  today** (`middlebury.py:244` and `blender.py:65` both set it non-zero).
  `RefixableScene` arrives at step 7/10.

`target_to_fixation`'s docstring says in the code that it contradicts §3 and that
§3 is the one that is wrong. **Registered as #38: a §3 amendment or its own ADR, before
step 8.** Amending the constitution is the maintainer's call, not this branch's.
An additive one-line note on `scale_to_depth`'s docstring would stop the false
invariant propagating at its source — **#39**, deliberately separable and much
smaller.

What would actually *discriminate* the two readings is L4's real output on a
rendered refixable pair at `el != 0` against the renderer's known fixation —
**step 11**. Until then this is an argument from L4's algebra, not a measurement,
and the round-trip's 2e-16 is **not** evidence for it: that identity holds under
either convention.

## 4. Defect 3 — the demo passes px² where rad² is required

`scripts/demo_active_stereo.py:131` passes `d_var` (px², from
`estimate_vergence_disparity`) as `measurement_var` to `VergenceKalman.step`,
whose state is radians (`kalman.py:3,58-71`). Correct conversion
`var_mu = var_d / f²`.

The predicted symptom — "K ≈ 0, vergence frozen at its initial state" — is only
conditionally right, and the condition matters:

| `d_var` px² | K, first update (bug) | K, correct | after 8 updates |
|---|---|---|---|
| 1e-3 | 0.909 | 1.000000 | 2.4202° |
| 1e-2 | 0.500 | 0.999998 | 2.1803° |
| 1e+0 | 0.0099 | 0.999844 | 0.1825° |
| 1e+2 | 0.0001 | 0.984620 | 0.0020° |

(target 2.4408°, `P₀ = 1e-2 rad²`, constant measurement at `Z = 1.5 m`.) But
`estimate_vergence_disparity` returns `(pi/2)·mean_var/n_valid` (`vergence.py:61-64`),
and `n_valid` reaches 225 for a 15×15 window, so `d_var ≈ 0.00698 · mean_var`.
That is a **mapping, not a location** ((pi/2)/225 = 0.006981):

| `mean_var` px² | `d_var` px² | K, first update (bug) |
|---|---|---|
| 0.05 | 3.49e-04 | 0.966 |
| 0.25 | 1.75e-03 | 0.851 |
| 1.00 | 6.98e-03 | 0.589 |
| 4.00 | 2.79e-02 | 0.264 |

**Where real runs sit on this curve is unmeasured.** No demo run was made on
this branch, and the first version of this section asserted a landing point
(`d_var ~ 1.7e-3`) derived from a per-pixel variance of 0.25 px² that was never
measured — see §7.

What survives is the **monotone shape**, which follows from `K = P/(P+R)` alone:
K falls as `d_var` rises, so anything that raises the per-pixel variance or
shrinks `n_valid` (sparse texture, occlusion, a smaller window) moves L5 toward
coasting on its prediction, and anything that lowers them moves L5 toward
tracking correctly *despite* the unit error. The transition is somewhere inside
the tabulated range — K runs 0.966 to 0.264 across the two decades of `mean_var`
shown — but **which side of it a real run falls on is exactly what has not been
established**, and the earlier claim that this is "exp008's regime" was a
location claim resting on the fabricated figure.

With the correct conversion the result is flat at 2.4408–2.4421° across all five
decades; that insensitivity is the real tell, and unlike the severity it does not
depend on where runs land.

Instrumentation must therefore log the **`d_var` distribution**, not just K:
without it the severity cannot be read off a run at all. Not fixed on this
branch — **#41**.

## 5. The `k`-mismatch residual is zero by construction

The step-6 carry originally read: `R_rect` is `k`-independent but `H_e` is not,
so residual vertical disparity after rectification "measures `k` error". That
invited step 6 to chase a signal that does not exist.

Two different quantities were conflated. `d_v` in the pair *induced by* `R_rect`
never takes `k` as an input at all. `d_v` after warping the **raw** pair through
`H_e` does — and it measures **assumed-vs-actual `k` mismatch**, which is
identically zero when the two agree, *at any `k`* (`6.8e-13` px at `k = 0.25`,
`2.3e-13` at `k = 0.50`). The current pipeline images and rectifies with the same
`k`, so the residual is zero by construction: **a renderer using the constant
cannot inform the constant.** It is not a free measurement of ADR-0016's open
question.

Magnitude when the two disagree (0.25 ↔ 0.5). *Reproducibility spec — all three
elements are needed and none is derivable from the code:* `Fixation(0.5, 0.4,
0.064)`, `f = 800`, grid `(W, H) = (640, 480)` **centred on the principal point**
`(240, 320)`, every pixel unprojected to the fixation distance.

| statistic | value |
|---|---|
| max `abs(d_v)` | 4.38 px |
| rms | 2.73 px |
| mean | +2.55 px |
| mean-removed rms | 0.98 px |
| `k` agreeing | 5.7e-13 px |

If step 6 pursues it anyway, two facts it needs: the mismatch is a **pure torsion
about the optical axis** (the optical axis is `k`-invariant to 1.1e-16, forced by
`R_e ẑ = g_e`; the relative rotation's axis is `(0,0,−1)` with `abs(axis·ẑ) = 1.0`),
and that torsion is **0.003015 rad**, not `Δk·mu = 0.016` — off by **5.3×**, and
not by a fixed factor: the ratio runs 4.93 → 6.58 as azimuth goes 0.0 → 0.9 at
`el = 0.4`. The proportionality must be derived, not assumed.

**Step 6 should report the mean and the mean-removed rms separately.** The
residual is dominated by a common mode (+2.55 of 2.73), and a near-uniform row
offset is exactly what a rectification-residual test cannot distinguish from a
calibration offset — docs/method/003's "common mode" category. Reporting the raw
rms alone hides the split; reporting the mean-removed rms alone discards the
dominant component. The split *is* the finding.

## 6. Variance: what the first-order propagation does and does not say

`var_mu = J²·var_Z`, with `J = dmu/dZ` by the chain rule through **both** `D(Z)`
and `az(Z)` — the left-centre offset makes azimuth depth-dependent, so dropping
either branch is a silent factor error. Verified against central finite
differences to 1e-10 relative, and pinned by a test rather than a comment.

Linear pass-through is pinned across 8 decades (ratio `1.000000000000`), which
fails on any clip, floor, or quiet rescaling. A docstring cannot fail.

The propagated variance is the **exp004/exp006 anti-calibrated** one. First-order
propagation can be correct while its input is wrong, and downstream the two are
indistinguishable. A correct derivative of a miscalibrated quantity is still
miscalibrated; step 8's `CyclopeanBelief` compounds it under recursion.

**Depth versus inverse-depth.** They agree to first order *identically*. They
diverge in the second moment — and only under one parameterisation, which makes
the divergence a property of the **assumed distribution**, not of the geometry.
The docstring carries that sentence and points here; the numbers live here
because nothing regenerates a docstring table and no test pins one.

Harness: `rig(b = 0.064, f = 800, pp = (240,320))`, `current = Fixation(0.2, 0.3,
0.064)`, target at the principal pixel, `Z₀ = 1.5 m`, `abs(J) = 2.839e-02`,
200 000 draws, 40 000 evaluated, draws with `Z <= 0.05` discarded.

| σ/Z | Gaussian in `Z`: discarded | bias | sd / 1st-order | Gaussian in `1/Z`: bias | sd / 1st-order |
|---|---|---|---|---|---|
| 0.01 | 0.000 % | 0.01 % | 1.00 | 0.00 % | 1.00 |
| 0.10 | 0.000 % | 0.99 % | 1.04 | 0.02 % | 1.00 |
| 0.30 | 0.061 % | 13.62 % | 2.13 | 0.10 % | 1.00 |
| 0.50 | **2.648 %** | 41.83 % | 3.31 | 2.76 % | 0.94 |

Read the discarded column before the sd column: at σ/Z = 0.5 a Gaussian on `Z`
puts 2.6 % of its mass on `Z <= 0`, where `mu` is undefined, so **3.31 is partly
measuring truncation**. Under Gaussian-in-`1/Z` the linearisation is near-exact
by construction out to σ/Z = 0.3. Step 8 puts the belief on inverse depth, at
which point the left-hand columns stop describing anything real — which is the
argument for keeping them here and out of the code.

## 7. Method: a reduction docs/method/003 does not list, and a detection mechanism

This is the finding of the step, above any of the geometry.

*Not numbered.* Several things in this step could be read as instances of 003's
pattern — the rectification/vertical-disparity annihilation, the `el = 0`
sagittal hole, the self-consistent round trip, the random-cloud max, the
mean-removed rms — and whether those are one category or several is exactly the
judgement 003 records itself getting wrong (its own "second time in three days"
was a miscount, and it merged). Described, not counted.

**A variant not in 003's ledger.** 003 records reductions that annihilate sign,
location, common mode, eye index, and mechanism. Add: **max over a random point
cloud annihilates reproducibility.** It destroys nothing about the physics and
everything about whether a second analyst obtains the same number. Two unstated
analyst choices — seed and N — moved the `k`-mismatch maximum by 2.4× (5.93 to
14.28 px across six seeds, saturating in N above ~400). The maxima were driven by
grazing samples no camera images; the rig-fixed figure is 4.38.

**A detection mechanism not in 003 either.** Neither surface caught this by
reasoning. Both computed the same ill-posed statistic and got different numbers,
and **the disagreement was the detector**. 003 holds that what reaches premature
reduction is review by a surface with a *different* characteristic failure; here
both surfaces shared the failure and it was still caught, because a shared
ill-posed statistic produces divergent numbers rather than one plausible number.
Usable form:

> A statistic two independent harnesses compute differently is ill-posed until
> proven otherwise. Ask what the analyst chose; do not reconcile the numbers.

**The rule then fired a second time, on its own replacement.** The image-sampled
statistic was proposed as "extent fixed by the rig, nothing left to the analyst",
and the two surfaces still disagreed — 4.38/2.73 against 3.53/1.96. Cause: a grid
with `pp_col = 160` carried from an ADR-0016 snippet, off-centre, diluting the
rms. Both recomputed here rather than reconciled: `pp_col = 160` →
3.532/1.961/+1.697, `pp_col = 320` → 4.381/2.730/+2.547, which reproduces the
incoming pair exactly and identifies its cause.

The reason the choice was available to get wrong is structural: **`StereoRig`
carries no image dimensions** (`types.py:30-33`), so the extent *cannot* be
rig-fixed. A property of a type was asserted without checking the type. Both
firings belong in the record, because the second shows the pattern surviving the
first fix — a statistic proposed *as* the cure for an unstated analyst choice
still contained one.

**The 1.7e-3 figure, and how both surfaces ratified it.** The
`d_var ~ 1.7e-3` landing point in §4 was produced here from an *assumed*
per-pixel variance of 0.25 px² that was never measured, and then ratified
twice from the other side: the `n_valid` analysis was called "better than mine"
and a standing "L5 has been coasting" claim was withdrawn on its strength —
without either surface asking whether 0.25 px² had been measured. That is
003's Finding 5 exactly: one surface proposes, the other ratifies and
amplifies, neither checks.

**The asymmetry between the two catches in this thread is the important part.**
The random-cloud discrepancy was caught *structurally* — two harnesses computing
the same ill-posed statistic disagreed, and the disagreement did the work with
nobody looking for it. This one produced no disagreement at all, because both
surfaces accepted the same unchecked premise; it surfaced only when an audit was
**explicitly requested**. A failure mode that needs an audit to surface is weaker
evidence for the surfaces catching their own errors and stronger evidence for
writing the Code → Chat direction into CLAUDE.md §5, where the handoff contract
currently governs only the other direction.

**Provenance, which is the argument.** Both catches are the CLAUDE.md §5 handoff
contract operating in the **Code → Chat** direction — numbers originating in Code
and ratified by Chat — which 003 records as ungoverned by §5, since the rule as
written governs numbers arriving *from* Chat. They were caught by different
means, and the difference is the point:

- the random-cloud figure, because the discrepancy was **reported rather than
  adopted** — no one was looking for it, the two harnesses simply disagreed;
- the `1.7e-3` figure, only because an **audit was explicitly requested** — both
  surfaces had already agreed, so there was no disagreement to notice.

That is two occasions in this thread, alongside 003's own false premise, where
the absence of the rule in the reverse direction cost a merged contradiction. If
a fourth method note is written, that is its content and its argument: the
direction the contract does not cover has now produced one error the surfaces
caught unprompted and one they did not.

## 8. Registered, not fixed

- **#40 — `StereoRig` carries no image dimensions.** *One* item, **two
  independent bites in this step**, in unrelated registers: the out-of-bounds check (routed
  around by making `depth_at_target` field-shaped so the `Estimate` supplies
  `(H, W)`), and the residual statistic above (a 24 %/39 % two-surface
  disagreement). Two bites in one step is a stronger case for an ADR than either
  alone. Every consumer that needs the sensor extent currently reconstructs it
  from an array shape or invents it.
- **#38 — CLAUDE.md §3's depth-frame invariant.** §3 amendment or ADR, before
  step 8 (§3 above). **#39** is the separable `scale_to_depth` docstring note
  that stops it propagating at its source.
- **#42 — Phase B: the plant is unconstrained.** `abs(el) < pi/2` is 90°; human
  vertical gaze is ~±50°. Filed as a design issue, not an experiment: it is a
  *constraint on* exp008, and **the exp008 issue must cross-reference it** so the
  constraint is visible where it would contaminate a result. The reachability derivation has the policy able to walk to
  `el = 1.5` (86°) in ≥5 saccades. If it does that in exp008 the result reads as
  a finding about the policy when it is an artefact of an unconstrained plant.
- **#41 — `demo_active_stereo.py:131`**, the px²/rad² conversion (§4). The
  severity is variance-dependent and the operating point is unmeasured; the
  issue carries the mapping, not a location.
