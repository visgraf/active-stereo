# exp005 + exp006 — The energy pathway: from island to layer, and what its confidence is worth

**Records of record:**
[`experiments/exp005_energy_decoder/findings.md`](../../experiments/exp005_energy_decoder/findings.md) ·
[`experiments/exp006_multiscale_energy/findings.md`](../../experiments/exp006_multiscale_energy/findings.md)
· **Issues:** [#12](https://github.com/visgraf/active-stereo/issues/12),
[#13](https://github.com/visgraf/active-stereo/issues/13)
· **Runs:** `exp005a…5f407bd` / `exp005b…83d48ab` ·
`exp006a…4ea8400` / `exp006b…fc34275`

One briefing for two experiments, because they are one argument: exp005 built
the missing bridge and discovered the thing on the far side of it did not work;
exp006 fixed *that*, which finally made the interesting question testable — and
the answer was no.

---

## The gap these experiments closed

For its first four experiments this project had a working stereo pipeline and,
beside it, a validated neural encoding model that **nothing consumed**. The
[architecture briefing](architecture.md) called L2 an island, and it was: no
matcher read a `(K, H, W)` response volume, so [exp002](exp002-energy-models.md)'s
result was a statement about a component in isolation, not about the system.

Closing the gap needed a **decoder** — something that turns a population
response into an `Estimate` with a variance, i.e. that satisfies the same
`DisparityMatcher` Protocol as block matching and SGBM. That is
`inference.EnergyDecoder`, and the design carries the scientific motivation in
its bones: the readout is **moments of the profile**, not curvature of a cost
curve. [exp004](exp004-real-data-transfer.md) had shown curvature-derived
variance is *anti-calibrated* at half-occlusions — a sharp minimum at the wrong
disparity reads as precision. A population profile can express something
curvature cannot: "the evidence is spread across many disparities." Whether
that escapes the anti-calibration was the hypothesis worth the whole effort —
registered as exp005's H2, and explicitly a hypothesis, not a premise.

The readout, per pixel: subtract the profile's baseline, **refuse** if what
remains is a negligible fraction of the total (a ratio, so the refusal decision
is as gain-invariant as the values), take a local centroid around the peak, and
report the full profile's second moment as variance. Declining is what the
readout does when there is no evidence — the property exp001 taught us to
demand — not a bolted-on test.

## exp005: the bridge works; the thing it connects does not

Mechanically, everything held. Sixteen unit tests pin exact off-centre
recovery, endpoint rejection, multimodal variance inflation, and gain
invariance that is **bit-exact** for power-of-two gains — value, variance and
the refusal mask all identical to the byte.

Empirically, nearly everything died:

- On random dots the decoder's error was **14×** block matching's, against a
  falsifier bar of 2×.
- The centroid readout scored *below* exp002's raw argmax — the population
  statistic converts forgiving discrete bins into unforgiving continuous
  scatter.
- On photographs, the number that reframes the rest: decoder error sat at
  **91–96% of the uniform-guess floor** — indistinguishable from chance.
  exp002's encoder, near-exact on its own passband, carries essentially no
  matchable structure at a single ~24 px-period scale on real images.

The diagnosis was in hand before Stage A ran, because a promised unit test
failed on first execution. Answered pixels are a **mixture**: where the true
peak wins, the readout is unbiased to +0.006 px; where broadband noise picks
the channel, the argmax is roughly uniform over the bank, dragging the
population toward the bank centre in proportion to bank width. No readout
constant separates the classes — the flatness knob removes coverage without
removing bias. The failure is the *encoder's* per-pixel discriminability. That
localisation is what made exp006 a design rather than a guess.

### The vacuous survivor, and the rule it bought

exp005's photometric-robustness falsifier (H3) "survived by two orders of
magnitude" — and meant nothing, because **you cannot photometrically degrade
chance performance**. It was the third falsifier in this project to state a
threshold without asking whether the estimator was in a regime where the
threshold could bind (exp004's two vacuous SGBM cells were the first two).

The fix became exp006's most consequential line: **V0, a validity
precondition** — held-out error must beat an explicit chance floor by 5× with
coverage ≥ 0.50, or the downstream hypotheses are reported **void**, not
survived. Cheap to state, and as it turned out, the difference between an
uninterpretable verdict and a citable one.

## exp006: coarse-to-fine, and why it had to work in vitro first

The fix is a population across **spatial scales** — the Fleet–Jepson
coarse-to-fine construction, and also the V1-faithful one: cortex holds banks
at many spatial frequencies; our encoder had one. The two pathologies get two
different mechanisms:

- a **coarse** scale's profile has no false peaks within its long quasi-period,
  so a spurious fine-scale candidate far from the truth finds no support —
  that attacks the contamination class;
- a **fine** scale localises the surviving peak to sub-pixel — that restores
  precision.

`encoding.MultiScaleEnergyEncoder` composes the existing single-scale encoders
and normalises each scale's profile to a ratio *before* combining, so the exact
gain invariance survives composition scale-by-scale. The decoder did not change
at all — the bridge exp005 built accepts any encoder, which is what a Protocol
boundary is for.

The claim was tested before the experiment was allowed to run: on a stimulus
periodic at 8 px, a single fine scale *must* alias (it did: >15% of answers
grossly wrong) and the multi-scale profile *must* resolve it (it did: <5%,
median error under 1 px). If that unit test had failed there would have been no
Stage A.

Selection of the bank configuration was **computed, not chosen**: a declared
12-config grid, scored only on dev stimuli (including the two photographs
already burned by exp004's disclosed peeks), ranked by a criterion stated in
the config file, posted to #13 with the full table *before any held-out scene
was read*. The margin ranking came out monotone in scale count and sharper for
product than sum — the mechanism showing through the grid, not a lucky cell.

## What happened on the held-out photographs

**V0 passed with a 5.8× margin.** Median error 0.72 px against chance floors of
19–65 px — **3.5%** of the floor, where exp005 sat at 91–96%. That is block
matching's league (0.521 px on the same eight scenes). On random dots the bank
is now 10× *better* than block (0.0074 px vs 0.0714 px). And the invariance
argument became measurable at last: error multiplier **exactly 1.0** across the
interocular gain sweep (block drifts 2–7%), ×1.04 under a real exposure change
(block in exp004: ×44).

Honest residue: Vintage — the corpus's hard scene for every matcher we have
run — improves but stays unsolved (31.7 px, the only per-scene V0 failure), and
a moved *light source* costs ×5.6, because gain invariance is not photometric
invariance and nothing principled says it should be.

**And then H2, the hypothesis all of this existed to test, was falsified —
validly this time.** In high-contrast half-occlusions the profile's variance is
*lower* than at genuinely matched pixels: median ratio **0.254**, inverted in
seven of eight scenes, as low as 0.087 — a fusion layer trusting it would
weight fabricated matches up to ~11× above honest ones. Low-contrast occlusions
stay on the safe side (1.28), exactly the asymmetric signature exp004 found in
cost curvature.

## The finding that outranks the rescue

Three confidence readouts have now been measured in the same cell on the same
photographs: SSD **cost curvature** (0.12×), and now a **population second
moment** from a completely different matcher family (0.25×), with SGBM's
constant abstaining ([#9](https://github.com/visgraf/active-stereo/issues/9)).
Two genuinely different mechanisms, same inversion.

That relocates the defect. It is not that curvature was a bad proxy and a
better readout would fix it — exp005/exp006 *built* the better readout, the one
that can express "evidence is spread everywhere", and it inverts the same way.
**The anti-calibration is a property of the evidence itself**: at a
half-occlusion beside a strong edge, the matching evidence really is sharp — it
just belongs to the occluding surface. No per-pixel statistic computed from
left-referenced evidence alone can distinguish "sharply supported and right"
from "sharply supported and wrong", because sharpness is the only thing either
one shows it.

The mechanism has two faces, and exp006 exhibits both at once: the coarse
scale that suppresses noise-won candidates (the V0 rescue) also pools support
from deep inside the occluder — so hallucination *rose*, 0.80 → 0.91, the
highest of any matcher we have measured. What rescued accuracy and what
manufactures confident occlusion answers are the same pooling, seen from two
sides.

Escaping it therefore needs information the profile does not carry:
**left-right consistency** ([#7](https://github.com/visgraf/active-stereo/issues/7))
or an explicit occlusion model — L3 structure, not a better L2. Three
experiments now point at the same door.

## What else this settles

- **Issue #1 is answered as option (c).** exp002's precision failure was a
  genuine limitation of a single-frequency encoder, not a criterion problem or
  a pooling-window problem. The same readout over a multi-scale bank resolves
  the scatter the single scale could not — and the fix is the one the
  biological argument recommended before any of this was measured.
- **A component validated in isolation can be at chance in the system.**
  exp002 measured 0.031 px gain drift; end-to-end the same encoder was
  indistinguishable from guessing. Both numbers are correct. Component
  validation bounds what a part *can* do, not what the system *does* do.
- **The two-stage gate now has three clean outings** — and exp006's mattered
  most, because a 12-config grid plus an auto-selection rule is exactly the
  kind of freedom that leaks into held-out results when it is not spent on the
  record first.

## Caveats

- The bank configuration was selected on two dev photographs. It generalised
  (the dev margin predicted the held-out median within 2×), and the grid table
  shows no conclusion hanging on the tiebreak — but a different dev pair could
  have picked the sibling 4-scale config.
- Chance floors are one seeded draw of uniform guessing per scene; at margins
  of 0.008–0.13 the approximation is nowhere near any verdict.
- exp006's H2 ratio (0.254) and exp004's (0.12) are each stated in their own
  record's convention and are not the same matcher, window of analysis, or
  aggregation; compare the *sign and asymmetry*, not the digits.
- Nothing here tests 2-D oriented banks or vertical disparity — one axis of
  novelty per experiment, and exp006's was scale.

## Reproducing

```bash
python -m experiments.exp005_energy_decoder.run --stage a --config experiments/exp005_energy_decoder/config.yaml
python -m experiments.exp005_energy_decoder.run --stage b --config experiments/exp005_energy_decoder/config.yaml
python -m experiments.exp006_multiscale_energy.run --stage a --config experiments/exp006_multiscale_energy/config.yaml
python -m experiments.exp006_multiscale_energy.run --stage b --config experiments/exp006_multiscale_energy/config.yaml
```

Stage B of each refuses to run unless its gate was passed on the tracking issue
first; the runners enforce their own locks.
