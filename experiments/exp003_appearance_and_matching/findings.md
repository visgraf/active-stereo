# exp003 — Does specularity break stereo differently from texture loss?

**Issue:** [#4](https://github.com/visgraf/active-stereo/issues/4)
**Status:** run once — **both hypotheses falsified**, and the interesting result is
not the one either was about

## Hypotheses

**H1 (texture loss removes evidence).** As ground-truth albedo texture contrast
falls, coverage falls monotonically while median depth error on *answered*
pixels stays approximately flat — the matchers decline rather than guess.

**H2 (specularity supplies false evidence).** At **matched** albedo texture
contrast, glossy patches yield higher median depth error than matte at
**comparable or higher** coverage. This is the qualitatively worse failure: a
textureless region withholds evidence, a highlight fabricates it, and
`BlockMatcher`'s raw SSD cost — which assumes brightness constancy
unconditionally — has no way to tell the difference.

H2 is the novel claim. H1 mostly re-establishes a known effect on a new stimulus
class, which is what makes it a useful control: if H1 fails, the stimulus or the
pipeline is wrong, not the theory.

## What would falsify them

- **H1a** — coverage not monotonically non-increasing across
  dense > mid > coarse > constant, pooled over lighting and permutation.
- **H1b** — median absolute depth error on answered matched pixels rises by
  ≥ 2× from the dense to the constant-albedo condition.
- **H2a** — the glossy-minus-matte median error difference, at equal texture
  level, does not exceed the permutation-to-permutation spread of that difference.
- **H2b** — coverage on glossy is *lower* than on matte at equal texture level,
  which would make gloss behave like texture loss rather than like a constancy
  violation.

## Acceptance criteria

Both matchers (`block`, `sgbm`), 3 lighting rigs × 4 permutations = 12 renders,
scored on `matched` pixels only, aggregated by material index. Statistics are
medians over the 12 renders; the permutation spread is the noise floor every
claim is measured against.

## Stimulus

`--scene material-chart` (`scripts/render_stereo.py`): eight **coplanar** patches
at 1.05 m against a backdrop at 1.6 m, a 4×2 factorial of albedo texture
(dense/mid/coarse/constant) × reflectance (matte 1.0 / glossy 0.15 roughness),
under three procedural lighting rigs.

Geometry is bit-identical across every condition, so ground-truth depth,
disparity and half-occlusion are identical too and any difference between patches
is attributable to appearance alone. Material-to-position assignment is
cyclically permuted across 4 permutations so texture level is not confounded with
eccentricity — the variable ADR-0003 makes the pipeline sensitive to.

Measured on the committed chart (`key` lighting, permutation 0):

| material | albedo contrast | specular mismatch |
|---|---|---|
| dense_matte | 0.1920 | 0.0033 |
| mid_matte | 0.1748 | 0.0034 |
| coarse_matte | 0.0716 | 0.0029 |
| none_matte | 0.0000 | 0.0034 |
| dense_glossy | 0.1874 | 0.0392 |
| mid_glossy | 0.1709 | 0.0443 |
| coarse_glossy | 0.0698 | 0.3442 |
| none_glossy | 0.0000 | 0.0485 |

The matte and glossy rows are **matched in albedo contrast** (0.192 vs 0.187,
0.175 vs 0.171, 0.072 vs 0.070, 0.000 vs 0.000), which is what makes the H2
comparison a comparison of reflectance rather than of texture.

Appearance ground truth is read from render passes, never from the beauty image,
which conflates albedo texture with shading gradient: `Diffuse Color` → albedo,
`Glossy Direct` → specular energy, `Material Index` → condition label.

## Runs

| Run ID | SHA | Conditions | Result |
|---|---|---|---|
| `exp003-20260816T131125-3fe9985` | `3fe9985` | 12 (3 lighting × 4 permutations), 512 spp | H1 falsified, H2 falsified |

Block matcher (`d48_w7`), medians over the 12 renders:

| material | albedo sd | spec mismatch | coverage | err (m) | err spread |
|---|---|---|---|---|---|
| dense_matte | 0.1926 | 0.0037 | 0.9951 | 0.00060 | 0.00001 |
| dense_glossy | 0.1876 | 0.0620 | 0.9953 | 0.00060 | 0.00003 |
| mid_matte | 0.1747 | 0.0037 | 0.9929 | 0.00082 | 0.00003 |
| mid_glossy | 0.1702 | 0.0615 | 0.9928 | 0.00083 | 0.00004 |
| coarse_matte | 0.0718 | 0.0038 | 0.9905 | 0.00176 | 0.00012 |
| coarse_glossy | 0.0700 | 0.0368 | 0.9869 | 0.00171 | 0.00155 |
| **none_matte** | 0.0000 | 0.0037 | **0.7132** | **0.06023** | 0.12668 |
| **none_glossy** | 0.0000 | 0.0571 | **0.7047** | **0.08512** | 0.12151 |

SGBM is uniformly better on the textured rungs (error 0.00008 m, coverage
≈0.998, flat across all three) and shows the same collapse on constant albedo
(coverage 0.719/0.761, error 0.038/0.029 m).

## Findings

### The headline is neither hypothesis: matchers do not decline on textureless surfaces

On constant-albedo patches both matchers **answer roughly 71–76% of pixels and
get them wrong by ~95×** the textured error (block: 0.00060 m → 0.06023 m at
1.05 m, i.e. 0.06% → 5.7% depth error). Coverage falls only from 0.995 to 0.713.

That is not declining. It looked at first like the exp001 hallucination result
reappearing in a second place — exp001 found block matching returns confident
depth for 79.6% of ground-truth *half-occlusions*, and here it answers 71% of
*textureless* pixels. But that reading was wrong, and checking it produced the
better finding below.

### Correction: the two failure modes differ in whether the matcher knows

I initially wrote that the curvature-derived variance "has no idea they are
wrong". That was asserted, not measured. Measuring it inverts the conclusion.

Median reported disparity variance, block matcher, pooled over 12 renders:

| region | variance (px²) | vs textured |
|---|---|---|
| textured, matched | 90.0 | 1× |
| **textureless, matched** | **57,340** | **637×** |
| **half-occluded** | **425.8** | **5×** |

**On textureless surfaces the matcher does know it does not know.** Variance
inflates 637× while error inflates ~100×, so L4's inverse-variance fusion would
discount these pixels by more than enough. The uncertainty machinery
(ADR-0005) works here: the answers are wrong, but they arrive correctly labelled
as nearly worthless.

**In half-occlusions it does not.** Variance rises only 5×, which is nowhere near
enough to discount a measurement that is simply fabricated. That corroborates
exp001's claim on a completely different stimulus class — an RDS there, a
rendered Blender scene here — and it is the genuinely dangerous case.

So the operational ranking is not "textureless is as bad as occlusion". It is:

> half-occlusion is worse than texture loss, because only one of them is
> reported honestly.

The framework's real exposure is a matcher that is confidently wrong *and*
confident, which is occlusion, not texture loss. That sharpens where a fix is
worth building — and it is the opposite of what this experiment set out to test.

### The render-noise threat was checked, and it does not hold

This was flagged before the run as "the big one": a constant-albedo patch is not
blank in a Monte Carlo render, and independently-drawn per-eye sampling noise
would supply fake structure for which no true correspondence exists. If that
were driving the 71% coverage, the result would be about Cycles, not stereo.

Re-rendered `key_p0` at **4096 spp against the 512 spp original**, an 8× increase
that should shrink sampling noise by √8 ≈ 2.8×:

| spp | beauty local sd | L/R residual corr | coverage | err (m) |
|---|---|---|---|---|
| 512 | 0.00301 | 0.457 | 0.7261 | 0.05605 |
| 4096 | 0.00298 | 0.466 | 0.7369 | 0.05550 |

Nothing moved. The residual ~0.3%-amplitude structure on a "textureless" patch is
**deterministic shading, not sampler noise** — irradiance falloff across a finite
area light, which survives a 3×3 high-pass. So the matchers are locking onto
real image structure three orders of magnitude below the textured case and
returning confidently wrong depth from it. The threat is refuted and the finding
is strengthened.

(The L/R correlation of ~0.46, against 0.99 for textured patches, is mostly an
artefact of the diagnostic: the warp resamples at integer disparity, which
decorrelates low-amplitude fine structure far more than high-amplitude texture.
The two eyes also genuinely see slightly different shading.)

### H1 — falsified

**H1b fails decisively.** Error on *answered* pixels rises by **100× (block)** and
**455× (sgbm)** from dense to constant albedo, against a falsifier of ≥2×. The
premise — that the matchers withhold answers rather than guess — is simply wrong.

**H1a passes for block, fails for sgbm**, but the sgbm failure is not meaningful:
its coverage runs 0.9978 / 0.9978 / 0.9989 / 0.7192, so the "violation" is
`coarse` exceeding `mid` by 0.0011. **Stating a monotonicity falsifier with no
noise floor was a design error on my part.** The honest reading is that coverage
is flat across all three textured rungs and collapses at zero, for both matchers.
I am reporting the verdict as the pre-registered criterion computes it rather
than rewriting the criterion after seeing the number; the criterion should have
read "monotonically non-increasing beyond the permutation spread".

### H2 — falsified as stated, and the statistic was the problem

Glossy-minus-matte error at matched texture contrast is ~0 on every textured
rung (−1.5e-07, +7.5e-06, −4.5e-05) against a permutation noise floor of 0.127 m.
Coverage is likewise unaffected. So H2a fails; H2b passes trivially because
nothing happens at all.

The design goal was met — albedo contrast **is** matched across the roughness
axis (0.193/0.175/0.072 matte vs 0.188/0.170/0.070 glossy), so this is a clean
comparison of reflectance. Specularity simply did not move the patch median.

**Post-hoc (exploratory, not a test of H2):** binning all 361,373 textured-glossy
pixels by measured specular mismatch shows the effect is real but confined to the
tail:

| specular mismatch | n | median err (m) | p90 err (m) |
|---|---|---|---|
| 0–50% (0.000–0.061) | 180,687 | 0.00098 | 0.00503 |
| 50–80% (0.061–0.147) | 108,412 | 0.00085 | 0.00350 |
| 80–95% (0.147–0.377) | 54,206 | 0.00091 | 0.00550 |
| 95–99% (0.377–0.672) | 14,455 | 0.00196 | 0.07250 |
| 99–100% (0.672–0.918) | 3,614 | 0.00305 | 0.06707 |

Overall Spearman(mismatch, error) = −0.004: no monotone relationship across the
range. But above mismatch ≈0.38 — the top 5% of pixels — median error rises 2–3×
and **p90 error rises 14×** (0.005 → 0.07 m). Specularity does damage stereo, in
the tail of the error distribution, on a small minority of pixels. Testing it
with a patch median was the wrong instrument, and the 0.15 roughness produces
highlights too small to shift one.

This is hypothesis-generating, not confirmatory. It should be pre-registered and
re-tested, not cited as support for H2.

### Added after the fact: a large lighting interaction this analysis missed

The runner pools over lighting, because lighting was a nuisance variable to
average out rather than a factor to test. Breaking it out while preparing the
slide deck (`slides/exp003_appearance_and_matching/`) found the largest effect in
the whole experiment. Blank-wall patches, matte, medians over 4 permutations:

| lighting | answered | depth error | trusted | variance (px²) |
|---|---|---|---|---|
| flat ambient | 60.8% | **291.88 mm** | 3.9% | 33,398 |
| directional key | 71.3% | 60.23 mm | 4.3% | 68,166 |
| **raking grazing** | **98.8%** | **2.68 mm** | 7.1% | 230,156 |

**A raking light rescues a textureless surface.** Error drops from 292 mm to
2.68 mm — comparable to a genuinely textured patch — because the shading gradient
across the uniform albedo *is* matchable structure. Well-textured patches are
indifferent to lighting (0.60–0.61 mm in all three rigs), so this is specific to
the case with no albedo texture to fall back on.

That also reframes the earlier claim that a uniform surface is "wrong by ~95×".
It is wrong by ~95× *under the lighting we happened to average over*. The
honest statement is that a textureless surface has no intrinsic matchability:
whether it can be recovered at all is a property of the illumination, not of the
surface.

**And trust does not follow accuracy.** Compare the first and last rows: 3.9% vs
7.1% trusted — nearly the same — for errors differing by **109×**. Under raking
light the matcher is accurate and does not believe itself; under flat light it is
wrong and equally disbelieving. So the reported variance is tracking **image
contrast, not correctness**, which is exactly what a cost-curvature proxy would
be expected to do.

That completes the calibration picture, and it is more nuanced than the
two-regime version above:

| regime | answer | trust | consequence |
|---|---|---|---|
| textured | right | trusted | works |
| blank wall, flat light | wrong | distrusted | safe |
| blank wall, raking light | **right** | **distrusted** | safe but wasteful |
| half-occluded | fabricated | **trusted** | poisons fusion |

Two caveats on this section, since it was not pre-registered. It is a breakdown
of the same 12 renders by a factor the design deliberately balanced, so the
permutation control still applies and it is not a fishing expedition — but it
carries no falsifier and was found while looking for something to put on a slide.
A confirmatory version should sweep lamp elevation continuously rather than
compare three hand-placed rigs.

### The texture ladder is effectively two-level, not four

dense (0.193), mid (0.175) and coarse (0.072) are statistically
indistinguishable — coverage 0.995/0.993/0.990, error 0.0006/0.0008/0.0018 —
while constant albedo (0.000) collapses. Everything from 0.07 upward is "plenty
of texture"; the entire transition lives between 0.00 and 0.07, where there are
no samples. Three of the four rungs bought nothing. A follow-up should place the
ladder geometrically inside [0, 0.07].

## What this changes

1. **Occlusion detection is the higher-value fix, not a texture gate.** The
   variance table above says texture loss is already reported honestly (637×
   inflation) while half-occlusion is not (5×). Building a local-contrast gate in
   L3 would harden the case the framework already survives. A left-right
   consistency check, which is what SGBM effectively buys and what exp001 found
   it winning on, addresses the case that actually propagates.
2. **NCC/census would not fix either case.** They address brightness constancy,
   which this experiment shows is not the binding constraint at the median.
3. **A textureless refusal gate is still worth having,** but for a different
   reason than assumed: not because the estimates poison fusion — they do not —
   but because 71% coverage at 5.7% depth error wastes L6 fixations on regions
   that cannot be resolved, which is the ADR-0002 hang in a milder form.
4. **Reported variance is a contrast meter, not a reliability estimate.** The
   lighting breakdown makes this precise: 3.9% vs 7.1% trusted for errors
   differing by 109×. ADR-0005 requires estimators to return a variance; it does
   not require that variance to be *calibrated*, and nothing in the repo has ever
   checked. Any downstream weighting inherits the miscalibration in both
   directions — fabricated matches pass, correct ones are discarded.
5. **A textureless surface has no fixed difficulty.** Whether it can be matched at
   all is a property of the illumination. Reporting a single number for
   "performance on low-texture surfaces" is not meaningful without stating the
   lighting, which has implications for how any XR robustness claim is phrased.
6. **exp004 candidates,** in the order the evidence now supports: (a) why
   occlusion variance stays low, and whether a cheap left-right consistency term
   fixes it — this is where the exposure is; (b) variance calibration measured
   directly, sweeping lamp elevation continuously, since the three hand-placed
   rigs here only sample it; (c) specularity re-tested on the p90 with sharper,
   larger highlights; (d) the `GaborEnergyEncoder`'s validated gain invariance
   (exp002) against differential interocular shading, once L3 can consume a
   response volume.

**Nothing was retuned after seeing a failing number.** The material scales, light
energies, sample count and both falsifier thresholds were fixed before the run;
the two design defects found (an unbounded monotonicity criterion, and a
four-rung ladder spanning the wrong range) are recorded above rather than
corrected in place.

## Threats to validity

Written before the first run, while nobody has a stake in the outcome.

- **Render noise is uncorrelated between the eyes.** The big one. A
  constant-albedo patch is not blank in a Monte Carlo render: it carries per-eye
  sampling noise drawn *independently*. That is worse than featureless, because
  it supplies fake local structure for which no true correspondence exists. A
  "textureless" result may therefore be measuring Cycles' sampler rather than the
  absence of texture. Denoising is disabled and recorded in `rig.json` precisely
  so this cannot be papered over — a denoiser would invent the spatial structure
  whose absence is the independent variable.
- **Sample count interacts with the axis above**, since specular renders are
  noisier. Fixed at 512 across all conditions and recorded.
- **A chart is not a scene.** Attribution is bought at the cost of ecological
  validity. Results transfer to real imagery only insofar as real surfaces
  resemble these patches.
- **`cross_check_occlusion` (1 px tolerance)** is ground truth only for opaque
  surfaces — which is why no metallic or transmissive materials appear.
- **Renders are the least-verified thing in the repository** (ADR-0009: nothing
  inside Blender can be covered by the test suite). Any number here deserves more
  suspicion than the equivalent from an RDS.
- **`confine_to_fovea` is deliberately not applied.** It inflates variance with
  eccentricity, and eccentricity is exactly the confound the permutation sweep
  exists to average out; applying it would reintroduce as a modelling term what
  the design spends 12 renders removing.

## Notes for whoever runs this next

Stimuli live in `results/stimuli/chart/` (git-ignored) rather than `data/`, which
holds pointers and never blobs. Regenerate with:

```bash
python scripts/render_chart_sweep.py --out results/stimuli/chart
```
