# 2026-08-25 — Step 6 preamble: the static-path hazard, and a tolerance not worth measuring yet

Branch `docs/step-6-preamble`, written before any of step 6 exists
([plan](../plans/fixation-migration.md), step 6). Fourth entry of this date; the
others are [the plane-of-regard optimum](2026-08-25-plane-of-regard-optimum.md),
[toed-in projection](2026-08-25-toed-in-projection-and-item-4.md) and
[step 5](2026-08-25-step-5-target-to-fixation.md).

This carries the numbers behind step 6's open-questions block. The plan file
holds the decisions; this holds the measurements and their harnesses
(ADR-0016's split).

**Disclosure (CLAUDE.md §5).** Every figure here is **derived from assumed rig
parameters** and **nothing is measured from a stimulus file**. No demo or render
was run. The assumed inputs, used throughout unless stated:

| input | value | status |
|---|---|---|
| baseline `b` | 0.065 m | **assumed** |
| focal length `f` | 800 px | **assumed** |
| principal point | (240, 320) | **assumed** |
| vergence | 0.064 rad | **assumed** |
| Listing coefficient `k` | 0.25 | **assumed** (ADR-0016 has it PROVISIONAL) |

Everything below is computed from `activestereo` at this branch's parent
(`8fefb45`). Two figures arriving from Chat needed correction and one of my own
did; all three are recorded rather than quietly fixed.

## 1. The static-path hazard — why the warp must be the identity on a converged rig

ADR-0013 runs static stimuli at `Fixation.forward(rig.vergence)`. At `el = 0` the
rectifier `R_rect` is the identity, but `rig.vergence > 0` makes `R_e != I`, so
`H_e != I`. Meanwhile the stimulus was captured **off-axis with parallel axes** —
it is *already* a rectified pair. Warping it assumes a toed-in capture that never
happened.

### The displacement is `f·tan(mu/2)`, and depends on neither `b` nor `k`

The principal pixel of a raw eye image maps to that eye's optical axis, which is
toed in by `mu/2`. So

    d_col = f · tan(mu/2) = 800 · tan(0.032) = 25.6087 px

per eye, **opposite signs**, with `d_row = 0` exactly at the principal pixel.
Measured **+25.6087** (left) and **−25.6087** (right).

Both independences verified rather than asserted — the baseline cancels because
`(b/2)/D = tan(mu/2)`, and the optical axis is `k`-invariant because
`R_e ẑ = g_e`:

| swept | values | `d_col` |
|---|---|---|
| `b` | 0.055, 0.064, 0.065, 0.075 | 25.6087 px in all four |
| `k` | 0.0, 0.25, 0.5 | 25.6087 px in all three |

So the assumed `b = 0.065` **does not enter this figure at all**; it rests on `f`
and `vergence` alone. Worth stating because it removes one assumed input from the
result.

### Severity: row-wise correspondence is destroyed, and depth is biased

Harness, stated because the first version of this measurement was not
reproducible (§5 below): 640×480 grid **centred on the principal point**,
fronto-parallel plane at head-frame `Z`, both eyes warped by their own `H_e`,
`d_v` taken between **corresponding points** of the already-rectified pair.

| `Z` | true `d` (parallel capture) | max &#124;d_v&#124; after warp | rms | `d_h` bias |
|---|---|---|---|---|
| 0.5 m | 104.0 px | 7.180 px | 2.140 | +54.52 px |
| 1.0 m | 52.0 px | 6.664 px | 2.075 | +54.12 px |
| 2.0 m | 26.0 px | 6.407 px | 2.058 | +54.01 px |

Before the warp `max abs(d_v)` is **exactly 0.00e+00** — it is a rectified pair by
construction. After it, 6.4–7.2 px. **Scanline search is broken and the depth is
biased, both silently.** `exp001`–`exp007` are the baseline this would corrupt if
step 6 warps static stimuli.

The discriminator is already typed: ADR-0013:76-81 requires `rig.vergence == 0`
on refixable scenes, so `rig.vergence != 0` ⇔ static capture ⇔ already rectified ⇔
the correct warp is the identity. Make it unconstructible, not documented.

### The ratio correction — and why no single ratio works

The incoming severity claim was "+54 px = **+104 %** of true disparity at
`Z = 1 m`". That used `f·b/Z = 52 px`, the **parallel-rig absolute** disparity.
This repo's convention is signed relative to fixation (CLAUDE.md §3;
`depth_to_disparity`, `projection.py:35-60`), under which
`rig.fixation_distance = 1.015278 m` and the signal at `Z = 1 m` is **0.7825 px**
— making the bias **69.2×** the signal, not 104 % of it.

But 69.2× alone is also a premature reduction, because the denominator has a
**zero crossing**:

| `Z` | repo-convention `d` | bias / `d` |
|---|---|---|
| 0.50 m | +52.78 px | 1.0× |
| 1.00 m | +0.78 px | 69.2× |
| **1.015278 m** | **≈ 0 (horopter)** | **diverges** |
| 2.00 m | −25.22 px | −2.1× |
| 5.00 m | −40.82 px | −1.3× |

**Record the bias in pixels (≈54, near-invariant) and the ratio as a curve with
its singularity named.** Any single ratio annihilates the horopter crossing —
including the corrected one.

## 2. What step 6's tests cannot see, and why the tolerance is deferred

Every step-6 unit test images and rectifies at the *same* fixation, so `H_e` is
exact and the residual is identically zero. The obvious next question — how much
fixation error can rectification absorb before row-wise search breaks — turns out
**not to be worth measuring yet**, and the reason is more useful than the number.

If rectification consumes the **commanded** fixation, and the renderer renders at
the commanded fixation, then `H_e` is exact at every fixation and the residual is
zero **by construction**: there is no plant-noise model in the loop. The tolerance
binds only if rectification consumes L5's **estimate**. Nothing has decided which.
The roadmap's rule is *measure before repair*; the corollary is **do not measure
what may be structurally zero**. Deferred, and recorded in the plan as an open
question rather than an answered one.

Three rounds of measurement went into the number before that was noticed. What
those rounds *did* produce is worth keeping, and it is all about method.

### The support rule — the durable output

Two harnesses bisecting the same tolerance disagreed. The cause was
**out-of-bounds handling, and both had it wrong**: neither cropped. A pixel whose
warped coordinates leave the frame **is not available to the matcher**, so
including it measures a residual no matcher can see.

Rule adopted: **in-bounds after the warp, both eyes.**

| support | az | el | vergence |
|---|---|---|---|
| keep out-of-frame — harness A | 1.791° | 5.025° | 0.277° |
| keep out-of-frame — harness B | 1.791° | 5.592° | 0.298° |
| **in-bounds — harness A** | **1.823°** | **6.076°** | **0.323°** |
| **in-bounds — harness B** | **1.821°** | **6.086°** | **0.329°** |

(`max abs(d_v) < 0.5 px`, bisected; sagittal `Fixation(0, 0, 0.064)`;
fronto-parallel plane at head-frame `Z = 1.0`; 640×480 centred; both `R_rect` and
`R_e` built from the **assumed** fixation, so they move together — a harness
holding `R_rect` at truth models a different failure than the loop produces.)

**Why cropping *erased* the gap instead of preserving it.** If the crop were
merely one more difference among several, applying it would have left the others
intact. It did not: an 11 % elevation gap collapsed to 0.2 %. So the uncropped max
was attained at an extreme out-of-frame point whose identity depended on
incidental sampling, and the two harnesses were maximising over effectively
different point sets. **The uncropped statistic had no stable *where*, which is
why it had no stable *value*.**

That is 003's "`max` annihilates *where*" with the causality made explicit, and it
retro-explains step 5's random-cloud episode by the same mechanism — making those
two incidents one rather than two.

### False agreement, and the field divergence beneath it

The 0.1 / 0.2 / 1.8 % convergence above was agreement on a **reduced statistic**,
reached while the two harnesses still computed the **underlying field**
differently at a single fully specified pixel. Agreeing on a reduction while
disagreeing on what it reduces is **false agreement**. The convergence licensed
the support rule; it did not license the number.

The one other instance, **named rather than counted** (004's lesson; 003's
mis-numbering is why): step 5's `el = 0` result, where a correct `R_rect` and a
transposed one both project the fixation point to `row = 240.0000`. The shape
differs one level down — there it was one harness with two implementations, here
two harnesses with one implementation each. Same failure, different axis of
duplication, which is why counting them would flatten it.

### The field divergence, resolved: it was the sampler

One harness's `d_v` response was constant in `Z` to twelve digits; the other's
varied ~8–11 %. Both **exact**, so they were computing different functions rather
than one function noisily. Switching **only the sampling origin**, everything else
identical, over `Z ∈ {0.7, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0, 50.0}` fitted to
`A + B/Z`:

| axis / sampler | `A` | `B` | `B/A` | fit residual |
|---|---|---|---|---|
| elevation / cyclopean rays | 0.044789 | −0.000000 | −0.00 % | 4.3e-14 |
| elevation / left-eye rays | 0.044789 | 0.003639 | 8.12 % | 5.4e-14 |
| vergence / cyclopean rays | 0.837774 | −0.000238 | −0.03 % | 1.5e-08 |
| vergence / left-eye rays | 0.837779 | 0.067805 | 8.09 % | 5.5e-06 |

**Both harnesses were measuring the same geometry correctly.** The `A` terms are
identical across samplers to six digits — the two never disagreed about the rig
term. The whole divergence was `B`, and `B` is the sampler.

**Mechanism.** Sampling along the **left eye's** rays displaces the sampled world
points laterally by `b/2`, which displaces where they *image* by `f·b/(2Z)` =
26.0/Z px — 26 px at `Z = 1`, 2.6 px at `Z = 10`. That is a rigid `1/Z` shift of
the sampling window across a fixed field, so the max slides along the field's own
spatial gradient with depth. **`B` measures the field's gradient near the argmax,
not depth dependence in the geometry.**

Two diagnostics that looked open, both closed by this:

- The **5.4e-14** elevation fit residual was real and meant what it looked like: a
  rigid `1/Z` window shift across a smooth field produces *exactly* `A + B/Z`. The
  hypothesis that a two-parameter fit through two `Z` samples is zero by
  construction was checked and **excluded** — the fit used **8** `Z` values.
- **`B/A` = 8.1 % across two axes** agrees precisely *because it is a property of
  neither axis*: the same `f·b/(2Z)` window shift over each field's gradient scale.

What survives about the geometry itself: the `x·y/f` mechanism. An azimuth error
produces `d_v` through a coupling that scales with disparity and therefore depth,
while elevation and vergence errors rotate the row coordinate scene-independently.
Azimuth's `1/Z` scaling is the one thing both harnesses agreed on to 7 digits.

### `max` annihilates *where*, again

At the vergence perturbation that drives the whole-image max to 0.5 px, the
residual is an **edge** phenomenon:

| base | perturbation | max, and where | centre pixel | 15×15 foveal max |
|---|---|---|---|---|
| sagittal `(0, 0, 0.064)` | 0.323° | 0.500 px at (row 0, col 49) | +0.000090 px | 0.0017 px |
| eccentric `(0.30, 0.20, 0.064)` | 0.242° | 0.500 px at (row 479, col 46) | +0.0591 px | 0.0618 px |

So any tolerance depends on **which consumer's support** it is reduced over. The
matcher searches every row of the whole image, so the max is right for it. L5's
vergence estimator is a 15×15 windowed median at the target (ADR-0001), which sees
~300× (sagittal) or ~8× (eccentric) less. **Report the max with its location plus
a foveal value**; a bare max reads as "everywhere".

**And the sagittal case would make a step-11 test unfailable.** The foveal residual
there is 0.0017 px — zero by symmetry, not by margin — so any step-11 criterion on
foveal residual evaluated at sagittal gaze **cannot fail**. Third occurrence of the
`el = 0` hole in this project. Step 5's standing rule attaches: **every geometric
test uses `el != 0` AND `az != 0`**.

### A comparison deliberately not made

An earlier draft compared the tolerance against `VergenceKalman`'s default
`initial_var` (`kalman.py:31`). Dropped: `initial_var` is the `t = 0` prior,
uncertain by design, so "out of tolerance at loop start" is true of any filter and
carries no information. The live quantity is the **converged posterior**, which is
currently unobtainable because issue #41's px²/rad² bug sets the gain.

## 3. Resampling and variance — the claim rewritten before filing

The incoming claim was that bilinear resampling makes matcher variance
"systematically low — a second underestimate stacked on the exp004/exp006
anti-calibration". **That direction is not uniform.** Resampling changes effective
sample independence, and the **sign of the resulting variance error is a property
of the estimator**:

| estimator | variance model | resampling effect |
|---|---|---|
| `control/vergence.py:61-64` | `(pi/2)·mean_var/n_valid`, count-based | **under**estimates — effective `n` < nominal `n` |
| `inference/block.py` | `~1/(2a)`, parabolic curvature | **inflates** — smoothing lowers curvature |
| `inference/energy_decoder.py` | `m2 + step²/12`, profile second moment | **inflates** — smoothing broadens the profile |
| `inference/sgbm.py:59` | `base_variance`, a **constant** | **no effect** — structurally blind to the data |

Three directions across four estimators, one of them structurally blind. So this
is a **Phase C input** — `docs/roadmap.md:22` builds a `Confidence` Protocol with
three instantiations and scores them by sparsification-curve AUC, and this is a
property each instantiation has — rather than a defect report. SGBM's constant is
the fairness complaint Phase C already carries.

**Derived from reasoning, not measured.** Nobody has run this. Filed as **#44**.

## 4. Method

### A reduction not in 003's or 004's ledger

**A support choice can manufacture a dependence the quantity does not have — with
the opposite sign to the one it does.** The *cropped* statistic's `Z` dependence
for elevation and vergence runs opposite to the uncropped one's. A reader taking
either table as evidence about scene dependence would infer a sign that is not
there. The crop is still the right support for a matcher-visible tolerance; it is
simply not evidence about `Z`.

This is adjacent to 004's reproducibility row but distinct: there the reduction
destroyed whether a number could be obtained again, here the support **creates a
trend**.

### My own reproducibility failure, one day after writing the rule

The first severity figure in §1 was `max abs(d_v)` = **64.3 px** over a *random
point cloud* — an order of magnitude above the rig-fixed 6.4–7.2 px, and not
reproducible. 004 was written the previous day and its rule caught it immediately.
Recorded because a rule that catches its author is worth more evidence than one
that catches someone else.

### 004's rule run to completion

Report the discrepancy → state the analyst choices → **test the stated choice**.

The first two steps took three rounds. The third took a single command — because
the choice had finally been named concretely enough to be executable ("this
harness samples along the left eye's rays; yours samples along cyclopean rays").
**Naming the choice precisely is what converted an open divergence into a one-line
experiment.** The rule's expensive part is not the testing; it is getting the
description sharp enough to test.

## What the next entry should watch for

- Whether **commanded-vs-estimate** is settled at step 6 or drifts to step 11,
  where it decides whether the deferred tolerance is a real quantity at all.
- Whether the `rig.vergence != 0` guard survives step 7's `RefixableScene` as a
  reachable check, or becomes structurally dead — 003's `160.0 > 100.0` row.
- Whether the vertical-disparity cue (step 6's open question **a**) is ever
  reclaimed, or whether `toed_in_disparity`'s `d_v` return stays the only place it
  exists in the codebase.
