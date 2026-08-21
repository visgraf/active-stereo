# exp007 — MiddEval3 training-set placement: a long way from the leaderboard, and exactly where the photometric pairs said we'd be

**Run:** `exp007-20260821T230639-65476a0` · **SHA:** `65476a0` · **Issue:** [#18](https://github.com/visgraf/active-stereo/issues/18)
**Scoring:** the benchmark's own evaluator (`MiddEval3/code/evaldisp` via `runeval`), 15 trainingQ pairs, thresholds in Q pixels (t=0.5 ≈ official full-resolution bad2.0 per the SDK README). A measurement, not a hypothesis test; expectations E1–E4 were registered on #18 before the first evaluation of our results.

## The placement

Dense convention (refusals filled or charged in full), unweighted mean over 15 pairs, local ruler, t=0.5:

| method | bad% | avgerr (Q px) |
|---|---|---|
| published SOTA (test, official) | ~5–7 | — |
| SGM (benchmark's own results, local ruler) | 24.2 | 1.51 |
| Census (same) | 28.9 | 2.00 |
| **ASsgbm** (ours) | **33.7** | 3.32 |
| **ASnrg** (energy pathway) | **52.9** | 10.64 |
| **ASblk** (block reference) | **58.0** | 6.99 |

Sparse convention (raw output; errors among answered pixels + refusal rate separately):

| method | bad% valid | invalid% |
|---|---|---|
| SGM_s | 15.2 | 11.7 |
| CENS_s | 16.8 | 17.7 |
| ASsgbm_s | 20.5 | 16.8 |
| ASnrg_s | 42.7 | 12.4 |
| ASblk_s | 42.9 | 16.6 |

Ruler transfer: our local scoring of the benchmark's own SGM results reads 24.2 against its published test-set 20.8 (different split, unweighted vs weighted, Q-size GT), so treat local numbers as ~3 points pessimistic when glancing at the online table. Every comparison *within* the tables above shares masks, ground truth and thresholds exactly.

## Expectation verdicts — one held, three did not

**E1 — block lands 30–45% dense bad2.0: FAILED (58.0%).** The prediction, not the matcher, was miscalibrated. exp004's bad-2.0 of 0.330 used a 2 px threshold at downsample 3, which is ≈ bad-6.0 in official full-resolution terms; official bad2.0 is 0.5 px at Q — a 4× stricter bar than the number the extrapolation leaned on. At t=1.0 (≈ official bad4.0) block reads 48.9%, still above the band. Sub-pixel precision, not gross failure, is what the strict thresholds are charging: block answers 0.33 px median on Motorcycle, and a 0.5 px bar takes a large bite out of exactly that distribution.

**E2 — energy dense bad2.0 worse than block: FAILED, and the failure is informative (52.9 vs 58.0, energy *better*).** On the 13 matched-photometry pairs the two are statistically tied — 53.8 vs 53.4 dense, 43.1 vs 43.4 sparse — so the registered reasoning (threshold metrics charge energy's gross-outlier tail) and the countervailing fact (block's near-threshold scatter is charged just as hard at 0.5 px) cancel almost exactly. The aggregate gap comes entirely from MotorcycleE and PianoL, where block collapses and energy does not. The 2014-corpus intuition "energy has heavier tails than block at equal medians" survives contact with the benchmark, but at strict thresholds it stops mattering: both matchers' error mass is above the bar.

**E3 — energy beats block on the photometric pairs: HELD, decisively.**

| scene (dense, t=0.5) | ASblk | ASnrg | ASsgbm | SGM |
|---|---|---|---|---|
| MotorcycleE (exposure) | 89.2 | **36.9** | 23.4 | 13.1 |
| PianoL (lighting) | 86.9 | **58.0** | 56.6 | 36.6 |

Block refuses half the image (53% / 47%) and is wrong about most of the rest; the gain-invariant pathway barely notices the exposure change (Motorcycle 39.0 → MotorcycleE 36.9 — *no degradation at all*, consistent with exp006's H3a/H3b) and degrades gracefully under moved lighting. This is the registered prediction from exp002's algebra holding up on pairs the benchmark itself designated as first-class datasets.

**E4 — energy's refusal gap larger than block's: FAILED as stated (12.4% vs 16.6% overall).** On matched-photometry pairs the direction holds trivially (12.8 vs 11.4); the aggregate inverts because block's refusals explode on the photometric pairs. The expectation was written from the 2014 corpus, which has no photometric variation inside the scored set.

## What this places on the record

1. **The gap to the state of the art is a factor of ~8–10**, and the gap to classic SGM a factor of ~2 (ASsgbm) to ~2.4 (energy). No number here is competitive, and none was expected to be: block is a deliberately simple reference, SGBM is OpenCV's off-the-shelf implementation, and the energy pathway is two experiments old. What the benchmark adds is an external, method-independent ruler — and the project's first numbers on data with *imperfect rectification* (dyavg up to ~0.5 px at Q, recorded per pair in the summary), which every matcher in `inference/` ignores by construction.
2. **Photometric robustness is the energy pathway's one leaderboard-visible virtue.** It is the only one of our three matchers whose MotorcycleE score matches its Motorcycle score. Nothing else we have measured — and neither of the benchmark's own SGM/Census reference results, both of which drop 0.9–14 points on the E/L pairs — has that property.
3. **The strict thresholds reframe what "block-level accuracy" (exp006) means.** At 2 px on the 2014 corpus, energy ≈ block. At 0.5 px both are ~43% wrong among answered pixels — sub-pixel precision is now the binding constraint for the whole pre-L3 stack, ahead of the occlusion problem in the error budget of this benchmark (though not in the *danger* budget exp004/exp006 established, which is about variance, a thing this benchmark does not score at all).
4. **The benchmark does not see uncertainty.** No column reads variance; a confident wrong answer and a calibrated refusal are the same "bad" pixel in the dense table (the fill turned 12–17% refusals into answers at no aggregate cost — compare bad% dense against totbad% sparse: 58.0 vs 59.5 for block, 52.9 vs 55.1 for energy). The project's central results are invisible to this ruler; that is a fact about the ruler, and it is why the anti-calibration findings needed their own experiments.

## What a public test-set submission would claim

Deferred by design. If made, the honest entry is ASsgbm or ASnrg at Q; the honest description says the energy pathway's contribution is exposure invariance and calibrated refusal, neither of which the default table displays. Given placement ~2× behind 2005-era SGM, the leaderboard argument for spending the once-per-method submission is weak; the paper can cite these training-set numbers with the same SDK provenance.

## Threats to validity

- **Local ruler at Q-size GT.** t=0.5 approximates official bad2.0; the SDK itself warns the numbers differ slightly from full-resolution evaluation. Anchored by scoring the benchmark's own SGM/CENS results identically (SGM: 24.2 local vs 20.8 published test).
- **Unweighted 15-pair means** vs the website's weighted averages. All within-table comparisons share the convention.
- **The background fill is ours** (scanline min-neighbour). A better fill would improve dense numbers for all three matchers; sparse columns are fill-free.
- **One run, no seeds.** All three matchers are deterministic given the pair; times are single wall-clock measurements on this machine (energy ~2.6–7.5 s per pair, block ~0.5 s, SGBM ~0.03 s).
- **exp006's constants were selected on 2014-corpus dev scenes** that overlap this training set (Adirondack appears in both). Nothing was tuned against MiddEval3 feedback — the config was closed before the first evaluation (#18) — but Adirondack's row should not be read as held-out for the energy pathway.

## Conventions

Disparities in Q-resolution pixels, left-referenced, positive = crossed, INFINITY = refusal (the framework's `nan` converted at the PFM boundary by `write_pfm`). Dense variants carry the declared fill; `_s` variants are raw. All disp/time files live in the MiddEval3 tree outside the repository; the run's `summary.json` pins every number quoted here.

## Reproducing

```bash
python scripts/fetch_middeval3.py                # data + GT + SDK + anchors
cd ~/datasets/middeval3/MiddEval3/code/imageLib && make CPPFLAGS="-g -O3 -W -Wall -I/opt/homebrew/include"
cd .. && make CPPFLAGS="-g -O3 -W -Wall -IimageLib -I/opt/homebrew/include" \
    LDLIBS="-LimageLib -lImg.$(arch)-g -L/opt/homebrew/lib -lpng -lz"      # needs brew libpng
python -m experiments.exp007_middeval3_training.run \
    --config experiments/exp007_middeval3_training/config.yaml
```
