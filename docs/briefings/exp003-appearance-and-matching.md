# exp003 — When does a stereo matcher know that it doesn't know?

**Record of record:** [`experiments/exp003_appearance_and_matching/findings.md`](../../experiments/exp003_appearance_and_matching/findings.md)
· **Issue:** [#4](https://github.com/visgraf/active-stereo/issues/4)
· **Run:** `exp003-20260816T131125-3fe9985`

> **Partly superseded by [exp004](../../experiments/exp004_real_data_transfer/findings.md).**
> Everything below about *texture* still holds. The conclusion about
> *half-occlusion* was too kind. exp003 measured a 5× variance inflation there and
> called the uncertainty under-inflated; on real photographs it turns out to be
> **inverted** — occluded estimates are reported as *more* confident than correct
> ones. The affected passages are marked inline.

---

## The question

Everything this project had measured up to now used a random-dot stereogram: a
field of high-contrast noise, textured everywhere, matte, evenly lit. It is the
right stimulus for proving that a depth estimate came from binocular matching
rather than from some monocular cue. It is also nothing like a real scene.

Two things in real scenes break stereo matching, and neither can happen on a
random-dot pattern:

- **A blank wall.** No texture means no way to tell which pixel in the left image
  corresponds to which in the right. There is simply no evidence.
- **A shiny surface.** A specular highlight is a reflection, so it sits at a
  *different physical point* for each eye. It does not withhold evidence — it
  fabricates it.

We wanted to know which of the two is worse, and what the system does when it
meets them.

## How the stimulus was built

The obvious approach — render one beautiful realistic scene — cannot answer the
question. If matching fails on a shiny, untextured, curved object in shadow, you
cannot say which of those four things caused it.

So: **hold the geometry completely fixed and change only the paint.**

Eight flat patches, all at exactly the same distance (1.05 m), against a textured
backdrop (1.6 m). Every patch has identical shape, identical distance, identical
occlusion along its edges. Across renders, only two things vary:

| Axis | Levels |
|---|---|
| Albedo texture | dense → medium → coarse → **perfectly uniform** |
| Surface finish | matte → glossy |
| (and lighting) | flat ambient · directional key · raking grazing |

Because the geometry is bit-identical everywhere, the ground-truth depth map is
literally the same array in every condition. Any difference in performance is
caused by appearance and nothing else.

Two details that make the measurements trustworthy:

- **Texture is measured, not assumed.** We read Blender's *albedo* pass — surface
  colour with all lighting removed — rather than judging texture from the
  rendered image. Under a raking light, a perfectly uniform wall shows a strong
  brightness ramp that looks like texture to any statistic computed on the photo,
  but supports matching far more weakly.
- **Materials rotate between positions.** If the uniform patch always sat in the
  corner, "no texture" would be confounded with "far from the centre of the
  image" — which is exactly the variable this framework is most sensitive to. The
  material-to-position assignment is cycled across four permutations so that
  averages out.

## What we predicted

**Prediction 1 — texture loss.** As texture disappears the matcher runs out of
evidence, so it should *decline*: return "unknown" for more and more pixels,
while the answers it does give stay accurate.

**Prediction 2 — specularity.** At equal texture, shiny patches should produce
*more error at the same coverage*, because a highlight supplies false evidence
rather than removing true evidence.

Both were registered with numeric falsifiers before the experiment ran.

## What actually happened

**Both predictions were wrong.**

Prediction 1 failed decisively. On a perfectly uniform surface the matcher does
**not** decline. It still answers about 71% of pixels — and those answers are
wrong by roughly 95×:

| Surface | Answers given | Depth error |
|---|---|---|
| Dense texture | 99.5% | 0.6 mm |
| Medium texture | 99.3% | 0.8 mm |
| Coarse texture | 99.1% | 1.8 mm |
| **Perfectly uniform** | **71.3%** | **60.2 mm** |

Prediction 2 produced nothing at all. At matched texture, glossy and matte
patches were indistinguishable — the difference in error was smaller than a
millionth of a metre, against a noise floor of 127 mm.

## The correction — and the actual finding

Seeing 71% wrong answers, the natural conclusion is *hallucination*: the matcher
is confidently making things up, exactly as [exp001](../../experiments/exp001_matcher_baseline/findings.md)
found it doing in half-occluded regions. That is what was written down first.

**It was written down without being measured, and measuring it reversed the
conclusion.**

Every estimate in this framework carries a variance — the system's own statement
of how much it trusts itself. Asking what that variance says:

| Region | Reported variance | vs. textured |
|---|---|---|
| Textured, matched | 90 px² | 1× |
| **Uniform surface** | **57,340 px²** | **637×** |
| **Half-occluded** | **426 px²** | **5×** |

On a blank wall the matcher's answers are wrong, but it **shouts its
uncertainty** — a 637-fold inflation, against roughly 100-fold error inflation.
Downstream, depth cues are fused in inverse proportion to variance, so those
answers are discounted to near-nothing automatically. The machinery works.

In a half-occlusion the answers are equally fabricated and it stays **almost
calm** — 5×. Nowhere near enough to stop a made-up measurement from being fused
at close to full confidence.

> A wrong answer labelled *"I'm guessing"* is harmless.
> A wrong answer labelled *"I'm certain"* is the one that propagates.

So the ranking is the opposite of what the experiment set out to test. **Texture
loss is survivable; occlusion is not** — not because the errors differ in size,
but because only one of them is reported honestly. And this now holds across two
completely different stimulus families: random-dot patterns in exp001, rendered
Blender scenes here.

> **Superseded — it is worse than 5×.** On real photographs
> ([exp004](../../experiments/exp004_real_data_transfer/findings.md)) the
> half-occlusion variance is not *under*-inflated. It is **inverted**: about
> **three times lower** than in genuinely matched regions, in seven of eight
> scenes. The matcher's occluded estimates are not merely trusted too much, they
> are its **most confident answers of all**.
>
> And exp004 found *why*, by running the check this briefing's own confound guard
> was designed for. The effect concentrates in **high-contrast** occlusions —
> variance below the matched median in every scene: 8.3× lower on the median
> scene, up to 34.5× on the worst. A half-occluded
> pixel beside a strong edge produces a sharp, unambiguous cost minimum *at the
> wrong disparity*, and a curvature-based variance reads that sharpness as
> precision. Low-contrast occlusions behave exactly as this briefing describes and
> are discounted safely; the danger is the crisp, well-lit, obviously-textured
> ones. Which is to say: the pixels a gaze policy would choose to look at.

## The threat we checked, and cleared

Before running, the main worry was recorded: a "uniform" patch is not truly blank
in a ray-traced render. It carries per-eye sampling noise, drawn independently
for each eye. If the matcher were locking onto *that*, the result would be a fact
about Blender's sampler, not about stereo vision.

So the scene was re-rendered with **eight times the samples**, which should shrink
sampling noise by about 2.8×. Nothing moved:

| Samples | Local contrast | Answers given | Depth error |
|---|---|---|---|
| 512 | 0.00301 | 72.6% | 56.1 mm |
| 4096 | 0.00298 | 73.7% | 55.5 mm |

The faint structure the matcher is chasing is **real shading** — light falling off
across the patch — not noise. The threat is cleared and the finding is stronger
for it.

## The part we found afterwards: lighting decides everything

The experiment treated lighting as a nuisance variable and averaged over it.
Breaking it out — same geometry, same materials, only the lamp moves — produced
the largest effect in the whole study. On a blank wall:

| Lighting | Answers given | Depth error | Trusted |
|---|---|---|---|
| flat ambient | 60.8% | **291.9 mm** | 3.9% |
| directional key | 71.3% | 60.2 mm | 4.3% |
| **raking grazing** | **98.8%** | **2.7 mm** | 7.1% |

**A raking light rescues a blank wall.** The shading gradient across the uniform
paint *is* matchable structure, and error falls to 2.7 mm — as good as a genuinely
textured surface. Textured patches are indifferent to lighting (0.60–0.61 mm in
all three), so this matters only where there is no albedo texture to fall back on.

This softens the headline above. A uniform surface is not "wrong by 95×" — it is
wrong by 95× *under the lighting we happened to average over*. A textureless
surface has no intrinsic difficulty; whether it can be recovered is a property of
the illumination.

And it sharpens the calibration point. Compare the first and last rows: 3.9% vs
7.1% trusted, for errors differing by **109×**. Under raking light the matcher is
right and does not believe itself; under flat light it is wrong and equally
disbelieving. So what the variance measures is **image contrast, not
correctness** — precisely what a cost-curvature proxy would do.

| Regime | Answer | Trust | Consequence |
|---|---|---|---|
| Textured | right | trusted | works |
| Blank wall, flat light | wrong | distrusted | safe |
| Blank wall, raking light | **right** | **distrusted** | safe but wasteful |
| Half-occluded, low contrast | fabricated | distrusted | safe |
| Half-occluded, **high contrast** | fabricated | **trusted most of all** | poisons fusion |

The last two rows are exp004's refinement of what exp003 recorded as a single
"half-occluded / trusted" row. The split is the actionable part: occlusion is not
uniformly dangerous, it is dangerous exactly where the image looks easiest.

Not pre-registered: this is a breakdown of the same twelve renders along a factor
the design already balanced, so the permutation control still holds — but it
carries no falsifier and was found while assembling slides. A confirmatory test
should sweep lamp elevation continuously instead of comparing three hand-placed
rigs.

## What this changes

1. **Build occlusion detection before a texture gate.** The instinct after seeing
   71% wrong answers on blank walls is to add a "reject low-contrast regions"
   rule. The variance table says that would harden the case the system already
   survives. The exposure is occlusion.
2. **Contrast normalisation is not the fix either.** Techniques like NCC or census
   matching target brightness differences between eyes. This experiment shows
   that is not the binding constraint here.
3. **A texture gate is still worth having — for a different reason.** Not because
   the estimates poison depth fusion (they don't), but because spending gaze on
   regions that can never be resolved is wasted effort in the active-sampling
   loop.
4. **For the paper:** the honest claim is not "the system is robust to difficult
   surfaces". It is that the system's *uncertainty is well calibrated for missing
   evidence and poorly calibrated for fabricated evidence* — which is a sharper
   and more interesting statement.

   **exp004 sharpens this again, and the wording matters.** On real photographs
   the second half is not "poorly calibrated" but ***anti*-calibrated**: the
   confidence ordering is inverted exactly where being wrong costs most. "Poorly
   calibrated" suggests a number that needs rescaling. It does not — it needs a
   different quantity, because cost curvature can express "this match is well
   localised" and structurally cannot express "there is no correspondent here".

## What we would do differently

- **The texture ladder was effectively two rungs, not four.** Contrast levels
  0.193, 0.175 and 0.072 performed identically; only 0.000 collapsed. The entire
  interesting transition happens between 0.00 and 0.07, where we took no
  measurements.
- **Specularity was tested with the wrong instrument.** Looking again at where
  highlights actually are, the effect *is* real — in the top 5% most
  specular pixels the 90th-percentile error rises **14-fold**. It simply never
  reached the patch average. (This is an after-the-fact observation and needs its
  own pre-registered test before it counts as a result.)
- **One falsifier had no noise floor**, so it technically "failed" on a coverage
  difference of 0.001. Meaningless, and reported as-stated rather than quietly
  rewritten.

## Caveats

- A test chart is not a scene. Attribution was bought at the cost of realism;
  these results transfer to real imagery only insofar as real surfaces resemble
  flat painted patches.
- No glass or metal. Blender's depth pass at a refractive surface records the
  glass, not what is behind it, which would silently corrupt the occlusion ground
  truth.
- Rendering is the least-verified part of this codebase — nothing inside Blender
  can be covered by the test suite ([ADR-0009](../decisions/0009-blender-api-version-adaptive.md)).
  Any number here deserves more suspicion than the equivalent from a random-dot
  stereogram.

## Reproducing

```bash
python scripts/render_chart_sweep.py --out results/stimuli/chart
python -m experiments.exp003_appearance_and_matching.run \
    --config experiments/exp003_appearance_and_matching/config.yaml
```

Four regression tests in
[`tests/regression/test_exp003_textureless_hallucination.py`](../../tests/regression/test_exp003_textureless_hallucination.py)
pin the result. Two of them are written to **fail when the defect is fixed**,
with instructions to invert rather than weaken them.
