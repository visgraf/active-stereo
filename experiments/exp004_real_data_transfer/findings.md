# exp004 — the uncertainty-calibration finding on real photographs

- **Run:** `exp004-20260818T201224-8b067fc` · SHA `8b067fc` · clean tree
- **Issue:** [#6](https://github.com/visgraf/active-stereo/issues/6)
- **Corpus:** Middlebury 2014, `-perfect`, downsample 3 (ADR-0012)
- **Layers:** L1–L4. L5/L6 are not exercised by a static stimulus.

## Verdicts

| | block | sgbm |
|---|---|---|
| **H1** — calibration asymmetry transfers | **survives** | survives, but vacuously |
| **H1b** — variance is *lower* in occlusion | **survives** | vacuously falsified |
| **H2** — photometric mismatch fabricates evidence | **falsified** | **falsified** |

## Held-out medians (8 scenes, `im1`)

Adirondack and Jadeplant are excluded — both were seen before the confirmatory
run, and both peeks are declared on issue #6 with timestamps preceding it.

| matcher | coverage | bad-2.0 | median \|Δd\| | median \|ΔZ\| | hallucination | var ratio |
|---|---|---|---|---|---|---|
| block | 0.922 | 0.330 | 0.521 px | 13.4 mm | **0.826** | **0.324** |
| sgbm | 0.876 | 0.087 | 0.240 px | 6.2 mm | **0.536** | 1.000 † |

† constant by construction — see "the vacuous cells" below.

Median errors sit 7–15× above the ground-truth noise floor (0.031–0.067 px per
scene, from `disp0-sd.pfm`), so these are matcher errors and not scanner noise.
SGBM's 8.7% bad-2.0 is believable for a classical method at reduced resolution;
block matching's 33% is expected for naive winner-take-all SSD and is not the
finding.

## H1 — the asymmetry transfers, and so does the number

Block matching fills **82.6%** of ground-truth half-occlusions with a confident
answer. exp001 measured **79.6%** on random-dot stereograms. Two stimulus
families with nothing in common — synthetic binary noise against photographs of
real objects — and the rate is within three points.

Reported variance flags none of it: the median occluded/matched variance ratio is
**0.324**, nowhere near the 20× that would have falsified H1.

### The result that was not predicted: SGBM's advantage does not transfer

exp001's operationally important conclusion was that SGBM declines where block
matching guesses — 9.0% against 79.6%, almost an order of magnitude.

| matcher | RDS (exp001) | Middlebury (exp004) |
|---|---|---|
| block | 79.6% | 82.6% |
| sgbm | **9.0%** | **53.6%** |

Block matching transfers within three points. **SGBM degrades six-fold.** The one
matcher this project could point to as behaving honestly in half-occlusions does
so largely on random dots; on photographs it fills more than half of them.

This was not a pre-registered hypothesis and is reported as an observation, not a
result — but it is the single most consequential number in the run, because
exp001's recommendation rests on the value that moved.

## H1b — worse than exp003 found, and in the other direction

exp003 concluded that half-occlusions inflate reported variance only 5×, against
637× for texture loss — enough to call the uncertainty badly calibrated. On real
photographs it is not merely under-inflated. It is **inverted**: variance in
half-occlusions is about **three times lower** than in genuinely matched regions.

Per-scene ratios, held-out only: 0.219, 0.468, 1.119, 0.428, 0.610, 0.081, 0.209,
0.059. One of eight reaches 1.0; the falsifier needed three.

So the framework does not merely fail to notice that it is fabricating. **It
reports fabricated estimates as its most confident ones.** `fuse_mle` weights by
inverse variance, so these are precisely the measurements that dominate fusion.

### The control that could have killed this, and did the opposite

The pre-registered worry: Middlebury's occluded regions might simply be
low-contrast — shadowed, behind foreground objects — making this exp003's
*texture* effect wearing occlusion's clothing. Splitting occluded pixels at the
median local contrast of matched pixels (block, `im1`, held-out scenes):

| scene | occluded, high contrast | occluded, low contrast | matched | n high |
|---|---|---|---|---|
| Motorcycle | **226.6** | 3 953.9 | 1 899.0 | 30 729 |
| Piano | **714.5** | 18 395.8 | 5 848.0 | 14 857 |
| Pipes | **359.5** | 4 497.3 | 941.7 | 30 836 |
| Playroom | **429.6** | 3 927.4 | 1 611.5 | 19 474 |
| Playtable | **165.5** | 2 359.3 | 800.7 | 18 653 |
| Recycle | **682.1** | 18 439.9 | 17 425.2 | 16 576 |
| Shelves | **1 158.7** | 77 642.7 | 15 606.5 | 13 151 |
| Vintage | **301.4** | 30 737.1 | 10 406.6 | 17 288 |

The confound is not merely absent, it is reversed. **Low**-contrast occlusions
behave exactly as exp003 predicts — variance inflates (median 2.95× the matched
level) and those answers are discounted safely. The danger is in the
**high**-contrast occlusions, where variance runs *below* the matched median in
all eight scenes: **8.3× lower on the median scene, and up to 34.5× lower**
(Vintage: 301.4 against 10 406.6). The smallest gap is 2.6× (Pipes).

> Corrected after first writing. This paragraph originally said "up to 12×
> (Motorcycle: 226.6 against 1 899.0)". Motorcycle is 8.4×, not 12×, and it is not
> the extreme — Vintage is. The error understated the effect and pointed at the
> wrong scene; it was caught while building the figure that plots all eight.
> Per-scene factors: Pipes 2.6, Playroom 3.8, Playtable 4.8, Piano 8.2,
> Motorcycle 8.4, Shelves 13.5, Recycle 25.6, Vintage 34.5.

Which makes mechanical sense, and is the sharpest way to state the finding: a
half-occluded pixel beside a strong edge produces a **sharp, unambiguous cost
minimum at the wrong disparity**. Curvature-based variance reads that sharpness
as precision. The estimate is confidently, precisely wrong, and nothing in a
single cost curve could distinguish it from a correct match.

Tens of thousands of pixels per scene sit in that cell. It is not a corner case —
and high contrast is exactly what a saliency-driven gaze policy (L6) selects for.

## H2 — falsified, and the failure is more informative than the prediction

Carried over from exp003: replacing the right image with a different exposure
(`im1E`) or lighting (`im1L`) should *fabricate* evidence, so error rises while
coverage stays flat.

Error rose. Coverage did not stay flat — it collapsed.

| matcher | variant | coverage drop | error multiplier | verdict |
|---|---|---|---|---|
| block | `im1E` | **−47.6 pts** | ×44.1 | falsified |
| block | `im1L` | **−31.0 pts** | ×28.2 | falsified |
| sgbm | `im1E` | **−19.8 pts** | ×1.4 | falsified |
| sgbm | `im1L` | **−27.5 pts** | ×2.0 | falsified |

Compared as paired per-scene differences: `im1`, `im1E` and `im1L` share geometry
and ground truth exactly, so each scene is its own control.

The prediction was wrong, and wrong in the direction that favours safety. Under
photometric mismatch the matchers **decline** — uniqueness and consistency tests
fail and coverage falls off a cliff. That is the withheld-evidence signature, not
the fabricated-evidence one.

The two matchers fail differently, and the split is worth keeping:

- **SGBM mostly declines.** Coverage drops 20–27 points while error on surviving
  answers rises only 1.4–2.0×. It is largely doing the right thing.
- **Block matching declines *and* degrades.** Coverage more than halves on `im1E`
  *and* the surviving answers are 44× worse. Fabrication is present; it is
  accompanied by mass abstention rather than replaced by it.

So the signature is **mixed**, and the pre-registered prediction of a clean
fabrication signature does not hold. Reported as falsified rather than
reinterpreted, on the same terms exp003's H2b was.

## The vacuous cells

`SGBMMatcher` returns a **constant** variance (`base_variance = 0.25`) wherever it
answers, and `nan` elsewhere (`inference/sgbm.py`). Two consequences, both flagged
in the run output rather than left to a reader:

- Its H1 variance ratio is exactly 1.0 in every scene **by construction**. It
  "passed" a test it could not fail (`H1_variance_test_is_vacuous: true`).
- Its H1b is recorded as falsified — 8 of 8 scenes at ≥ 1.0 — the same artefact
  with the sign flipped. **This is not evidence that SGBM's uncertainty behaves
  well in occlusion.** It is evidence that SGBM has no per-pixel uncertainty.

That is a finding about the framework, not the corpus. ADR-0005 requires every
estimator to return a variance; it never required that variance to carry
information, and nothing had checked. One of the two matchers compared across
four experiments satisfies the letter of that ADR with a constant — and, given
the section above, it is also the matcher whose headline advantage did not
transfer.

## Controls

**Cross-check tolerance.** The occlusion fraction barely moves across 0.5 / 1.0 /
2.0 px — Adirondack 6.40% → 6.08% → 5.98%, Motorcycle 8.17% → 7.72% → 7.58%. The
occlusion numbers are robust to a threshold inherited from Middlebury's generator
rather than chosen.

**Unknown ground truth.** 0.6%–10.7% per scene (Shelves worst), excluded from every
statistic via `known` (ADR-0011). Charged to occlusion, as Middlebury's own mask
would, Shelves' occlusion rate would have risen from 3.7% to 14.4% — nearly
quadrupled — and its hallucination denominator with it.

**bad-2.0.** Order-of-magnitude only: we downsample and Middlebury do not, so this
checks the loader rather than placing us on a leaderboard.

## Threats and limits

- **Two declared peeks.** Adirondack (loader validation) and Jadeplant (runner
  smoke test), both disclosed on issue #6 before the confirmatory run and both
  excluded from every pooled number. Their values (hallucination 0.759 and 0.662
  against a held-out median of 0.826) give no sign the peeks mattered — an
  observation, not a guarantee.
- **H1b was generated by the first peek** and is confirmatory only on the eight
  held-out scenes. It does not carry the weight of a prediction made in advance.
- **Downsampling by 3 is ours, not Middlebury's**, and it is a low-pass filter that
  removes exactly the fine texture exp003 found decisive.
- **Contrast is measured on the image**, because a photograph has no albedo pass.
  exp003 showed that conflates albedo texture with shading gradient, so the
  control-4 split is coarser than exp003's equivalent.
- **Ten scenes of indoor, static, diffuse-dominated tabletop imagery** is not XR
  content, and eight held-out scenes is a small n. Per-scene numbers are reported
  in full so the spread is visible.
- **Block matching is a reference implementation**, not a competitive one.
- **No independent occlusion ground truth exists in this corpus** (ADR-0012); our
  `matched` reproduces Middlebury's own generator, which validates the
  implementation and not the 1.0 px threshold.

## What this changes

Each of these is now filed with its own hypothesis and falsifiers: [#7](https://github.com/visgraf/active-stereo/issues/7)
(left-right consistency at L3), [#8](https://github.com/visgraf/active-stereo/issues/8)
(a variance proxy that can express "no correspondent"), [#9](https://github.com/visgraf/active-stereo/issues/9)
(SGBM's constant variance), [#10](https://github.com/visgraf/active-stereo/issues/10)
(whether SGBM's occlusion advantage is stimulus-dependent).

1. **Occlusion detection is now the highest-value thing to build**, and exp003's
   conclusion needs strengthening rather than repeating. Occluded estimates are
   not insufficiently distrusted; they are *actively trusted more than correct
   ones*, and the effect concentrates where contrast is high — the pixels L6 will
   preferentially fixate.
2. **A left-right consistency check at L3 is the obvious remedy**, and the corpus
   to test it now exists. `cross_check_disparity` already implements the operator;
   applying it to *estimated* rather than ground-truth disparity is a small change
   and deserves its own pre-registered experiment.
3. **Curvature is the wrong variance proxy.** A sharp cost minimum means a
   well-localised match *given that a match exists*. It cannot express "there is
   no correspondent here", and in exactly that case it reports maximum confidence.
   A structural limitation of `_subpixel_and_variance`, not a tuning issue.
4. **`SGBMMatcher` should not report a constant variance.** It satisfies ADR-0005
   textually while contributing a flat weight to every fusion it enters.
5. **exp001's matcher recommendation needs revisiting.** Its case for SGBM rested
   on a 9.0% occlusion hallucination rate that becomes 53.6% on photographs.
6. **For the paper:** the claim gets sharper and worse. Not "uncertainty is well
   calibrated for missing evidence and poorly calibrated for fabricated evidence"
   but *"…and **anti**-calibrated for fabricated evidence"* — the confidence
   ordering is inverted precisely where it costs most.

## Reproducing

```bash
python scripts/fetch_middlebury.py
python -m experiments.exp004_real_data_transfer.run \
    --config experiments/exp004_real_data_transfer/config.yaml
```

Deterministic: re-running on the same corpus reproduces `summary.json` exactly
(verified against the earlier dirty-tree run `exp004-20260818T195848`, byte-equal
in hypotheses, per-scene and held-out sections).
