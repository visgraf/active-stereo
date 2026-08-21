# Synthetic → rendered → real: which of our results were about stereo, and which were about our stimuli?

**A synthesis, not an experiment.** No hypotheses, no falsifiers, nothing
pre-registered. It re-scores three experiments' stimuli through one implementation
so their numbers can be compared, and says plainly which of its observations are
new and therefore untested.

**Records of record:**
[exp001](../../experiments/exp001_matcher_baseline/findings.md) ·
[exp003](../../experiments/exp003_appearance_and_matching/findings.md) ·
[exp004](../../experiments/exp004_real_data_transfer/findings.md)
· **Deck:** [`slides/comparative_stimulus_families/`](../../slides/comparative_stimulus_families/slides.md)

---

## Why bother

Three experiments, three stimuli, deliberately increasing in realism:

- **exp001** — random-dot stereograms. Depth exists *only* in the disparity, so a
  correct answer proves binocular matching rather than some monocular shortcut.
- **exp003** — rendered charts. Geometry held bit-identical while the paint
  changes, so a failure can be attributed to appearance and nothing else.
- **exp004** — photographs with structured-light ground truth. The first stimulus
  family we did not author.

Each was right for its own question. But together they can answer one that none of
them asked: **how much of what we learned is about stereo vision, and how much is
about the stimuli we happened to build?**

## The problem that had to be solved first

The three experiments do not measure the same things. exp001 reports an occlusion
hallucination rate and no variance ratio. exp003 reports variance ratios and never
measured hallucination. exp004 reports both, plus a contrast stratification neither
of the others attempted. Each computed its statistics inline, in its own way.

Putting the published numbers side by side would have put three different
definitions in one table and called it a trend.

So everything here is **re-scored from the original stimuli** through one shared
implementation. And because a shared implementation is only worth anything if it
agrees with the records it unifies, the script reproduces each experiment's
published headline *before it draws anything*, and refuses to plot if one
disagrees. It refused once — see "the aggregation trap" below.

## What transferred

**Confident filling of half-occlusions is real, and it is not about the stimulus.**

| matcher | random dots | rendered chart | photographs |
|---|---|---|---|
| block matching | 80.3% | 85.9% | 82.6% |

Three families with nothing in common — synthetic binary noise, ray-traced painted
patches, photographs of a motorcycle — and block matching fills roughly four out of
five genuine half-occlusions with a confident answer in all of them. That is a
property of winner-take-all SSD matching, full stop.

## What did not

**SGBM's advantage was mostly an advantage on random dots.**

| matcher | random dots | rendered chart | photographs |
|---|---|---|---|
| **SGBM** | **9.0%** | **38.5%** | **53.6%** |

exp001's practical conclusion was to prefer SGBM because it *declines* where block
matching guesses — 9% against 80%, almost an order of magnitude, and the paper's
most quotable operational result. It degrades **four-fold** on the first
non-synthetic stimulus and **six-fold** on photographs.

There is a plausible reason. Random dots give every pixel a locally unique
signature, which is precisely what SGBM's uniqueness and consistency constraints
are built to exploit. Real scenes have smooth walls and repeated structure, and the
advantage thins. That is a hypothesis, not a finding — it is filed as
[#10](https://github.com/visgraf/active-stereo/issues/10) and needs its own test.

It is also the clearest case this project has of a **synthetic stimulus flattering
one method**, which is worth remembering the next time a matcher comparison is run
on something convenient.

## The complication we had to be honest about

The natural headline would have been a monotone slide: uncertainty gets worse as
stimuli get more real, 1.92× → 0.81× → 0.32×, crossing below 1.0 somewhere in the
middle. It would have been wrong.

The rendered chart's 0.81× is an **artefact of that chart's design**. exp003
deliberately included textureless patches whose reported variance is 637× the
textured level. Pool those into the "matched" baseline and it swamps everything.
Under exp003's own textured baseline the chart reads **4.73×** — correctly
directioned, merely too small, exactly as exp003 reported.

So the honest picture is not a gradient:

| family | occluded / matched |
|---|---|
| random dots | 1.92× |
| rendered chart (exp003's baseline) | 4.73× |
| **photographs** | **0.32×** |

Only on photographs does the confidence ordering actually invert. Both numbers for
the chart are on the slide, with the reason, because plotting only the tidy one
would have manufactured a trend from a stimulus's design choice.

### The aggregation trap, for the third time

exp003 summarises as a *ratio of medians*; exp004 as a *median of per-scene
ratios*. On identical pixels those give 4.73 and 4.05.

Neither is wrong. They are different summaries, and each record is written in its
own. The synthesis reproduces each in the convention that record used, rather than
imposing one and quietly disagreeing with both. This is the third time this
project has been bitten by aggregation order — exp003's slide script hit it (730×
against a recorded 637×), exp004's did (0.225 against 0.324), and the cross-check
here caught it by refusing to draw.

## The observation worth an experiment

exp004's decisive control was splitting half-occlusions by local image contrast:
the danger is not occlusion in general but occlusion *at a strong edge*, where the
cost minimum is sharp and curvature reads sharpness as precision.

Nobody had applied that split to the earlier data. Doing it now:

| family | occluded, low contrast | occluded, HIGH contrast |
|---|---|---|
| random dots | 2.00× | **1.85×** |
| rendered chart | 1.11× | **0.37×** |
| photographs | 2.95× | **0.12×** |

**The anti-calibration is already in exp003's data.** 0.37× on the rendered chart —
well below 1.0 — in measurements taken in August and analysed without ever looking
at that cell. exp003 concluded the chart's occlusion variance was "under-inflated
at 5×". In its high-contrast half it was already inverted.

And on random dots it simply does not happen: 1.85×, the right side of 1.0.

That fits the mechanism exactly. **Random dots have no edges** — no coherent object
boundaries, only high-frequency noise — so a half-occlusion beside a strong
boundary is a configuration the stimulus cannot produce. The moment the stimulus
contains rendered objects, it can, and does.

> The failure needs *structure* to exist. Random dots cannot exhibit it. Renders
> can, and did, and we did not look. Photographs make it worse.

**This is exploratory.** Post-hoc, no falsifier, computed on data whose results
are already known, by someone who knew what he was looking for. If it survives a
proper pre-registered test it revises exp003's stated conclusion — and that test
does not exist yet.

## Postscript: a second matcher family crossed the ladder, and confirmed the worst of it

*(Added 2026-08-20. Unlike the rest of this synthesis, the numbers here are not
re-scored — they are registered results from
[exp006's findings](../../experiments/exp006_multiscale_energy/findings.md),
which used the same `metrics` module this synthesis is built on, under a
pre-registered falsifier with a validity gate. See the
[energy-pathway briefing](exp005-exp006-energy-pathway.md).)*

When this synthesis was written, every number in it came from one matcher
family: winner-take-all cost minimisation, with confidence read from cost
curvature. That left a live hypothesis — perhaps the anti-calibration was a
defect of *that readout*, and a population-profile variance would escape it.

The energy pathway then crossed the same ladder. On random dots it is now the
most precise matcher we have (0.0074 px, 10× better than block). On photographs
it reaches block matching's league. And in the high-contrast occluded cell —
the cell this synthesis flagged as the dangerous one — its profile-shape
variance came back **0.25×**, inverted in seven of eight scenes, in its own
convention and matcher but with the same sign and the same low/high asymmetry
(low-contrast occlusions stay safe at 1.28×).

Two consequences for the table above:

- **The anti-calibration row is no longer about curvature.** Two genuinely
  different confidence mechanisms invert in the same cell; the sharp-wrong
  evidence at an edge-adjacent half-occlusion is sharp for *any* per-pixel
  statistic computed from it. The remedy list in the next section — structural,
  not a better formula — is strengthened, not changed.
- **Hallucination is not bounded by matcher quality.** The multi-scale bank
  answers 91% of half-occlusions, *more* than block matching's 80–86%, because
  the coarse-scale pooling that makes it accurate also carries support across
  occlusion boundaries. Accuracy and occlusion honesty are not the same axis,
  and improving one bought us nothing on the other.

1. **Some results are about the algorithm.** Confident filling of half-occlusions
   held at 80–86% across every stimulus we have.
2. **Some are about the stimulus.** SGBM's honesty was 9% on random dots and 54% on
   photographs. Any matcher comparison run only on synthetic data may be ranking
   methods by how well they exploit synthetic statistics.
3. **Some failures are invisible until the stimulus is rich enough to contain
   them.** The anti-calibration needed edges. The project's founding stimulus, by
   design, has none.
4. **The remedies do not depend on which family you believe.** Left-right
   consistency at L3 ([#7](https://github.com/visgraf/active-stereo/issues/7)) and a
   variance proxy that can express "no correspondent exists"
   ([#8](https://github.com/visgraf/active-stereo/issues/8)) are indicated by all
   three.

The uncomfortable one is 3. exp003 had the data to find the contrast effect and did
not, because it was asking about texture and the relevant cell was in a different
table. That is not a failure of rigour — it is what happens when an experiment
answers the question it registered — but it is a reason to re-examine old data with
new controls before assuming a finding is new.

## Caveats

- **Difficulty is not held constant.** The matcher window is fixed at 7 px; the
  disparity range follows each scene, from 48 to 247. A wider search range is more
  chances to find a spurious minimum, and this comparison cannot remove that.
- **Absolute errors are not comparable** across families — different rigs, depth
  ranges and image sizes. Only rates and ratios travel.
- **The chart has the least occlusion** (12 863 pixels against 32 953 for
  photographs); coplanar patches against one backdrop barely occlude anything.
- **exp001 never published a variance ratio.** The 1.92× is new, computed here with
  the same code as the others.
- **SGBM's variance ratio is 1.000 everywhere by construction** — it returns a
  constant ([#9](https://github.com/visgraf/active-stereo/issues/9)). That is not a
  result about SGBM's calibration; it is the absence of one.
- **Three stimulus families is not a survey.** Nothing here is outdoor, moving,
  specular-dominated or wide-baseline.
