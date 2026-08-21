# exp005 — the energy decoder: three falsifiers dead, one vacuous survivor

- **Runs:** Stage A `exp005a-20260820T225706-5f407bd` · Stage B
  `exp005b-20260820T225844-83d48ab` · clean tree both
- **Issue:** [#12](https://github.com/visgraf/active-stereo/issues/12)
  · gate comment posted before any Middlebury access, unlock committed as
  `83d48ab`
- **Decoder:** `inference.EnergyDecoder`, readout constants `flatness=0.05`,
  `centroid_halfwidth=2`, encoder at exp002's frozen parameters

## Verdicts

| | outcome |
|---|---|
| **H1a** — RDS precision vs block | **falsified twice over**: 14× error (bar: 2×), coverage 0.847 (bar: 0.90) |
| **H1b** — readout beats raw argmax | **falsified**: 0.444 within ±1 px (bar: > 0.58) |
| **H2** — not anti-calibrated in occlusions | **falsified**: hallucination 0.801, hi-contrast ratio 0.903 < 1.0 in all 8 scenes |
| **H3** — photometric immunity on `im1E` | survives — **vacuously** (see below) |

The headline is not any single verdict. It is that **the single-scale energy
decoder does not transfer to photographs at all**: its Middlebury errors sit at
the uniform-guess floor, and every downstream number has to be read in that
light.

## Stage A (RDS, 5 seeds)

| | energy | block |
|---|---|---|
| median \|Δd\| | **1.001 px** | 0.071 px |
| coverage | 0.847 | 0.993 |
| hallucination | **0.855** | 0.803 |
| bad-2.0 | 0.266 | 0.004 |
| occluded/matched variance ratio | **0.957** | 1.923 |

H1b's 0.444 is *below* exp002's raw-argmax 0.50–0.58: the centroid readout does
not rescue the per-pixel scatter, it converts forgiving discrete bins into
unforgiving continuous spread. For issue **#1** this is evidence **against
option (a)** — the population statistic is centred (the readout is unbiased to
+0.006 px on pixels where the true peak won), but per-pixel precision is a real
limitation of the single-scale encoder, pointing at **(b)** wider pooling or
**(c)** genuine single-scale limits.

**The contamination mechanism** (diagnosed at the unit-test stage, before any
falsifier ran; sweeps in the gate comment): answered pixels are a mixture of
peak-won pixels (unbiased) and noise-won pixels whose argmax is roughly uniform
over the bank. The pull toward the bank centre scales with bank width (+1 px at
33 channels, +3 px at 65) and neither readout constant can separate the classes
— flatness refusal removes coverage without removing bias. This is the
encoder's per-pixel discriminability, not the readout: pinned as a
characterised regression in `tests/unit/test_energy_decoder.py`.

## Stage B (Middlebury): at the chance floor

| scene | ndisp | median \|Δd\| | uniform-guess floor | bad-2.0 | coverage |
|---|---|---|---|---|---|
| Motorcycle | 90 | 21.0 px | 23.0 px | 0.889 | 0.706 |
| Shelves | 80 | 18.4 px | 19.1 px | 0.907 | 0.513 |
| Vintage | 247 | 53.7 px | 64.7 px | 0.968 | 0.689 |

(All eight held-out scenes look like these three; block matching on the same
scenes: 0.521 px. Full table in `summary.json`.)

Decoder error is **91–96% of what uniform random guessing over the bank
achieves**. The Gabor passband (σ=6 px, ~24 px period — exp002's frozen
parameters) carries essentially no matchable structure on these photographs at
downsample 3, so nearly the entire answered population is the noise-won
contamination class from Stage A. Stage A predicted the direction; Stage B
measured the extent.

### H2 — falsified as stated, and mostly uninterpretable anyway

The falsifier triggers on its letter: hallucination 0.801 ≥ 0.40 **and**
median per-scene high-contrast occluded/matched variance ratio 0.903 < 1.0 —
below 1.0 in **all eight** scenes (0.725–0.954).

Two honesty notes, in opposite directions:

- 0.90 is *near-flat*, not hard-inverted like curvature's 0.12. If one squinted,
  "milder than block matching" is true.
- Squinting would be wrong, because at the chance floor the profiles are
  noise-dominated everywhere, so the variance is nearly the same large value in
  every region — matched, occluded, high-contrast, low-contrast (all ratios
  0.76–0.99). A variance that discriminates nothing is not "better calibrated";
  it is uninformative. The hypothesis that profile shape escapes the
  anti-calibration is **untested in the regime that matters** — a decoder that
  cannot match cannot tell us how its confidence behaves when matching fails,
  because matching never succeeds.

### H3 — survives vacuously, and the vacuity is a falsifier-design error

Median error multiplier on `im1E`: **×0.995**. Median coverage drop: **0.001**.
Against the pre-registered bars (×4, 25 points) H3 survives by two orders of
magnitude — and it means almost nothing, because **you cannot photometrically
degrade chance performance**. Block matching's ×44.1 started from 0.521 px;
the decoder starts from ~21 px, which exposure change cannot make worse.

The falsifier failed to condition on baseline validity. This is the **third
instance of the same design flaw in this project**: exp004's H1 variance test
was unfalsifiable for SGBM (constant variance), its H1b was unfailable in the
other direction, and now H3 here. The pattern each time: a falsifier states a
threshold without asking whether the estimator is in a regime where the
threshold can bind. Future falsifiers should carry an explicit validity
precondition (here: baseline error at least, say, 5× below the chance floor).

What *is* true, and rests on other evidence: the end-to-end gain invariance of
value, variance and the refusal decision is exact — proven algebraically in the
module docstring and pinned **bit-exactly** for power-of-two gains in the unit
suite, on stimuli where the decoder does work. A non-vacuous H3 needs a regime
above the floor: a gain-swept RDS, or a multi-scale encoder on photographs.

## What survives this experiment

1. **The L2→L3 bridge exists and is mechanically sound.** `EnergyDecoder`
   satisfies `DisparityMatcher`; 16 unit tests pin exact off-centre recovery,
   endpoint rejection, the variance floor, multimodal inflation, and bit-exact
   gain invariance. L2 is no longer an island — it is a layer whose current
   occupant is not competitive.
2. **Issue #1's decision is materially informed**: against (a); the scatter is
   real and the readout cannot remove it. (b) or (c), and on this evidence the
   single scale looks like the binding constraint — the same encoder that is
   near-exact on its own passband (exp002's 0.031 px gain drift) is at chance
   on photographs.
3. **A multi-scale bank is now the identified next step**, not an option among
   many: the failure is localised to the front-end passband, the readout above
   it is unbiased where evidence exists, and the machinery to score any new
   encoder end-to-end now exists and costs one constructor argument. Needs its
   own issue and falsifiers — including validity preconditions.
4. **The gate worked.** Constants and Stage A numbers were on #12 before any
   Middlebury read; the Stage A warning (variance ratio 0.957 on RDS) predicted
   Stage B's H2 direction, and is on the record as prediction rather than
   hindsight.

## Threats and limits

- **Peak RSS 8.7 GB** (reported per #12; estimate was ~1.3 GB). The K-channel
  volume is ~1.3 GB on Vintage, but `match()` materialises a second full volume
  for the argmax (`np.where(isfinite(E), E, -inf)`) and allocator retention
  across three variants compounds it. An avoidable doubling if anyone needs
  this at scale; irrelevant to the verdicts.
- **The encoder's edge band**: any pixel whose *widest* bank channel runs off
  the frame is invalid in every band, costing a bank-width column band beyond
  `out_of_frame` — part of why coverage trails block everywhere. A contract
  property (ADR-0009-era design), not a bug; changing it would silently alter
  exp002's valid-pixel sets.
- **Chance-floor comparison is approximate**: uniform guessing over
  `[2, ndisp−2]` vs the scene's true disparity distribution, one draw. It
  brackets the decoder's error within ~10%, which is all the argument needs.
- Encoder parameters were frozen at exp002's values by design; nothing here
  says a *tuned* single-scale encoder would fail — only that this one, the one
  exp002 validated, does not transfer.

## Reproducing

```bash
python -m experiments.exp005_energy_decoder.run --stage a \
    --config experiments/exp005_energy_decoder/config.yaml
# gate: constants + Stage A posted to #12, stage_b_unlocked flipped in 83d48ab
python -m experiments.exp005_energy_decoder.run --stage b \
    --config experiments/exp005_energy_decoder/config.yaml
```
