# exp006 — multi-scale energy: off the floor, and the anti-calibration is in the evidence

- **Runs:** Stage A `exp006a-20260820T233759-4ea8400` · Stage B
  `exp006b-20260821T001427-fc34275` · clean tree both
- **Issue:** [#13](https://github.com/visgraf/active-stereo/issues/13)
  · gate comment (`issuecomment-5363411475`) posted with the full grid table
  before any held-out scene was read; unlock committed as `fc34275`
- **Encoder:** `encoding.MultiScaleEnergyEncoder`, selected at the gate by the
  declared criterion: scales (4,2)(8,4)(16,8)(32,16)(48,24) px (period, σ),
  `combine=product`, `floor=0.001`. Readout constants unchanged from exp005
  (`flatness=0.05`, `centroid_halfwidth=2`).

## Verdicts

| | outcome |
|---|---|
| **V0** — validity precondition | **passes**: median error is **3.5%** of the chance floor (bar: ≤ 20%), coverage 0.884 (bar: ≥ 0.50) |
| **H1** — held-out accuracy | survives: median \|Δd\| 0.72 px (bar: ≤ 3 px) |
| **H2** — variance not anti-calibrated in occlusions | **falsified, validly this time**: hallucination 0.914 ≥ 0.40 and hi-contrast occluded/matched variance ratio 0.254 < 1.0 |
| **H3a** — RDS gain sweep | survives: energy error multiplier **1.0000** at every gain in {0.5, 0.75, 1.25, 1.5} (bar: ≤ 1.1); block drifts 1.02–1.07 |
| **H3b** — `im1E` on photographs | survives: error multiplier 1.044 (bar: < 2.0), coverage drop 0.0003 (bar: ≤ 15 pts) |

Two results, and the second is only meaningful because of the first:

1. **The multi-scale bank rescues the energy pathway on photographs.** exp005's
   single scale sat at 91–96% of the uniform-guess floor; the five-scale bank
   sits at **3.5%** of it — 0.72 px median error, in block matching's league
   (0.521 px on the same scenes) rather than 40× behind it.
2. **With validity finally established, the profile-variance hypothesis got its
   first real test — and failed.** High-contrast half-occlusions read as ~4×
   *more* precise than matched pixels (median ratio 0.254, below 1.0 in 7 of 8
   scenes, as low as 0.087). This is the same asymmetric signature exp004 found
   in curvature-derived variance, reproduced by a completely different readout
   on a completely different matcher. The anti-calibration is not a property of
   any readout; **it is a property of the evidence** — a sharp peak at the
   wrong disparity is genuinely sharp, and the profile's second moment honestly
   reports concentrated (wrong) evidence.

## Stage A (dev set): the mechanism showed before the held-out run

The declared 12-config grid, scored on the two burned photographs
(Adirondack, Jadeplant): every config cleared the chance floor (worst margin
1.84×), and the margin ranking was monotone in scale count (5 > 4 > 3) and
sharper for product than sum — the coarse-suppression mechanism, not a lucky
cell. Selected config: photo margin **17.98×**.

On RDS (5 seeds) the selected bank scores **0.0074 px** median error vs block's
0.0714 px (ratio 0.104) at coverage 0.879 — where exp005's single scale was
**14× worse** than block. The contamination class that produced that failure is
gone: coarse scales leave a spurious fine-scale candidate no support.

**H3a is the non-vacuous gain test exp005's H3 could not be** (valid regime:
energy at 0.104× block's error at gain 1.0). The measured multiplier is 1.0 to
1e-12 at all four gains — the bit-exact per-scale normalisation, visible
end-to-end — while block, which has no invariance argument, drifts 2–7%.

## Stage B (eight held-out scenes, `im1`)

| scene | ndisp | median \|Δd\| | floor | margin | coverage | halluc. | hi-contrast ratio |
|---|---|---|---|---|---|---|---|
| Motorcycle | 90 | 0.33 px | 23.0 px | 0.014 | 0.913 | 0.897 | 0.82 |
| Piano | 87 | 0.31 px | 21.0 px | 0.015 | 0.872 | 0.909 | 0.29 |
| Pipes | 100 | 0.20 px | 24.9 px | 0.008 | 0.921 | 0.880 | 1.84 |
| Playroom | 110 | 1.73 px | 27.6 px | 0.063 | 0.921 | 0.962 | 0.69 |
| Playtable | 97 | 0.56 px | 23.8 px | 0.024 | 0.896 | 0.931 | **0.089** |
| Recycle | 87 | 2.89 px | 21.5 px | 0.134 | 0.849 | 0.920 | **0.087** |
| Shelves | 80 | 0.87 px | 19.1 px | 0.046 | 0.851 | 0.962 | 0.14 |
| Vintage | 247 | 31.74 px | 64.7 px | 0.490 | 0.744 | 0.685 | 0.22 |

Vintage remains the corpus's hard scene for every matcher we have run
(exp004: SGBM and block both worst there; exp005: 53.7 px). The bank improves
it (0.83× → 0.49× floor) but does not solve it; it is the only scene that
would fail a per-scene V0. The registered criterion is the median over scenes,
which passes with a 5.8× margin.

### H2 — the falsification that finally means something

exp005's H2 also triggered, but at the chance floor the variance discriminated
nothing (all ratios 0.76–0.99); the verdict was uninterpretable. Here the
matcher works — V0 passes with margin — so the variance pattern is measured in
the regime the hypothesis is *about*:

- **High-contrast occlusions** (the dangerous cell): median ratio **0.254**,
  hard-inverted (≤ 0.29) in five scenes. A fusion layer trusting this variance
  would weight fabricated matches up to ~11× *above* honest ones.
- **Low-contrast occlusions** (the safe cell): median ratio 1.28, ≥ 1 in six
  scenes — inflated variance where evidence is genuinely absent, exactly as
  designed.
- **Hallucination 0.914** — higher than exp005's single scale (0.801) and
  higher than block (0.826) or SGBM (0.536) in exp004. This is the cost of the
  mechanism that passed V0: a 48 px-period Gabor pools support from deep
  inside the occluding surface, so the same coarse evidence that suppresses
  noise-won candidates also *manufactures* confident matches across occlusion
  boundaries.

The asymmetry (lo safe, hi dangerous) replicates exp004's curvature result and
exp003's retro-scored renders. Three readouts — SSD curvature, SGBM, and now a
population second moment — agree, which relocates the problem: no per-pixel
confidence read from the matching evidence alone can distinguish "sharply
supported and right" from "sharply supported and wrong", because at a
half-occlusion the evidence *is* sharp — it belongs to the occluder. Detecting
the condition seems to require information the profile does not carry:
left-right consistency (issue #7) or an occlusion model, i.e. L3 structure, not
a better L2/readout.

### H3b — gain invariance is real end-to-end; lighting is not gain

`im1E` (exposure change): ×1.044 error, coverage unchanged — against block's
×44.1 in exp004, and no longer vacuous (the baseline is 0.72 px, not 21 px).
`im1L` (illumination change, reported unbarred): ×5.6 median error multiplier
(1.07–50×, worst on the specular Pipes). Moving the *light source* changes
which physical structure is imaged, and no interocular normalisation can — or
should — be invariant to that.

## What survives this experiment

1. **L2 is a working layer, not an island.** Encoder → decoder → metrics, end
   to end on real photographs, at block-matching accuracy, with an exact gain
   invariance block matching lacks. Issue #1's question is answered as (c):
   the single scale was the binding constraint, and the fix was a population
   across scales — the V1-faithful choice, which is a satisfying alignment of
   the biological and engineering arguments.
2. **The anti-calibration is now a claim about evidence, not about readouts** —
   established by falsification under a passing validity gate, which is what
   makes it citable. The uncertainty the framework needs at occlusions cannot
   come from L2 profile shape; it needs L3-level structure (issue #7's
   left-right consistency is the obvious candidate).
3. **The validity-precondition discipline paid for itself immediately.** The
   identical falsifier text produced an uninterpretable verdict in exp005 and a
   meaningful one here, and the only difference V0 sees is the regime. Every
   future falsifier keeps one.
4. **The gate held again**, and mattered more this time: with 12 configs and an
   auto-selection criterion there were more degrees of freedom to leak, and all
   of them were spent on the record before any held-out read.

## Threats and limits

- **Config selection used two dev photographs.** It generalised: the dev
  margin (error at 1/17.98 ≈ 0.056 of the floor) predicted the held-out median
  (0.035) to within 2×, and 7/8 held-out scenes came in at ≤ 0.134. A
  different dev pair could still have picked the 4-scale product bank instead;
  the grid table shows the two within 2× of each other on every dev metric, so
  no conclusion hangs on that choice.
- **Peak RSS 7.24 GB** (vs ~2.6 GB estimated). The argmax fix removed exp005's
  extra volume, but five sequential encodes × three variants leave allocator
  retention; the accumulator design caps *simultaneous* volumes at 2, not the
  allocator's high-water mark. Irrelevant to verdicts; would matter for L6-scale
  sweeps.
- **Chance floors are one seeded draw** of uniform guessing over
  `[2, ndisp−2]` (seed 20260820, in-runner). At margins of 0.008–0.13 the
  ~10% approximation error is nowhere near the verdicts.
- **Hallucination and H2 are measured on scorable ∩ answered occluded pixels**
  with contrast split at the median scorable contrast of `im1`'s left image
  (window 7), conventions verbatim from exp004; ratios are median-of-per-scene
  ratios throughout.

## Reproducing

```bash
python -m experiments.exp006_multiscale_energy.run --stage a \
    --config experiments/exp006_multiscale_energy/config.yaml
# gate: grid table + selection posted to #13, stage_b_unlocked flipped in fc34275
python -m experiments.exp006_multiscale_energy.run --stage b \
    --config experiments/exp006_multiscale_energy/config.yaml
```
