# exp001 — What a matcher is, and why "how often is it right?" was the wrong question

**Record of record:** [`experiments/exp001_matcher_baseline/findings.md`](../../experiments/exp001_matcher_baseline/findings.md)
· **Issue:** [#1](https://github.com/visgraf/active-stereo/issues/1)
· **Run:** `exp001-20260815T211624`

> **The specific recommendation here has been revised by [exp004](exp004-real-data-transfer.md).**
> The finding — that declining matters more than matching — held on every
> stimulus family since. The *ranking* it produced did not: SGBM's advantage is
> largely a property of random dots. Marked inline where it matters.

---

## What a matcher is, in this framework

A matcher (L3, `inference/`) does one thing: given a rectified stereo pair, say
for each left pixel **how far to the left its partner sits in the right image**.
That horizontal shift is *disparity*, measured in pixels.

It is not asked for depth. That conversion needs the baseline and the vergence
state, which are properties of the rig rather than the images, and it happens one
layer up ([the scaling closure](architecture.md)). A matcher that returned metres
would be hiding an assumption inside itself.

The contract is short and two clauses of it do most of the work:

```python
class DisparityMatcher(Protocol):
    def match(self, left, right) -> Estimate: ...
```

- It returns an `Estimate` — a value **and a variance**. Not a bare number
  ([ADR-0005](../decisions/0005-uncertainty-first-class.md)).
- Unmatched, occluded or out-of-range pixels are `nan` in *both* arrays. Never
  `0`, never `-1`. **Declining is a legal, expected answer.**

That second clause is the whole subject of this experiment.

### The two matchers

**Block matching** is the textbook method, kept deliberately simple because it is
the reference the others are checked against. For every candidate disparity it
slides the right image across, squares the difference, sums over a 7×7 window, and
picks the shift with the lowest cost. The variance comes from the *curvature* of
that cost curve at its minimum — a sharp minimum means a well-localised match, a
flat one means the pixel could be anywhere.

**SGBM** (semi-global block matching) does the same local costing, then adds a
smoothness penalty aggregated along many directions across the image, so a pixel's
answer is influenced by its neighbours' answers. It also runs its own left-right
consistency check and refuses pixels that fail it. It is OpenCV's, wrapped so that
nothing downstream ever sees an OpenCV convention.

Theory says SGBM should win: the aggregation regularises exactly the ambiguity a
7×7 window cannot resolve on its own.

## The question, and a term that had to exist first

**Hypothesis:** with foveal confinement active, SGBM achieves lower foveal depth
error than block matching, and hallucinates less in half-occluded regions.

The "with foveal confinement active" is not decoration. Depth is recovered by
linearising the disparity-to-depth inversion about the current fixation, and that
linearisation is only locally valid. Without a term accounting for it, the
pipeline reports equally confident depth across the entire field, peripheral
estimates are trusted as much as foveal ones — and **the theoretically expected
ordering of the matchers inverts**. [ADR-0003](../decisions/0003-foveal-confinement-linearization-error.md)
adds an eccentricity-dependent penalty, quadratic in distance from the fovea, that
only ever *increases* variance and so can never manufacture confidence.

The stimulus was a random-dot stereogram: a field of high-contrast noise where
depth exists *only* in the disparity between the two eyes. Nothing about a single
image hints at the shape. That is the point — a correct answer proves binocular
matching rather than a monocular shortcut ([ADR-0006](../decisions/0006-scenes-as-a-separate-package.md)).

## What happened

Both acceptance criteria were met. And the number that mattered was not the one
the hypothesis was about.

| Matcher | Foveal depth error | Coverage | **Hallucination** |
|---|---|---|---|
| block matching | 1.27 mm | 0.993 | **79.6%** |
| SGBM | 0.0 | 0.877 | **9.0%** |

Depth error separated them by about a millimetre at a metre — real, and almost
uninteresting. The last column separated them by nearly an order of magnitude.

**Hallucination** here means: of the pixels that are *genuinely half-occluded* —
visible to the left eye, hidden from the right by a nearer surface, so no
correspondent exists at all — what fraction did the matcher answer anyway?

Block matching answered four out of five. It has nothing to match against; it
returns the best of a set of uniformly bad options and reports it with a variance
derived from how sharp that bad minimum happened to be.

> A matcher that returns `nan` in a half-occlusion is telling the truth.
> A matcher that returns a number is injecting a confident false measurement
> into the fusion at L4.

Notice what that does to the coverage column. Block matching answers 99.3% of
pixels, SGBM only 87.7%. Read as a scoreboard, block matching wins. Read
correctly, **the high coverage is the symptom** — it is answering the questions it
should have declined.

So the case for SGBM was never mainly that it matches better. It is that it
*declines* better.

## What later work did to this

This is where the briefing has to be careful, because the reframing above has held
up and the recommendation has not.

[exp004](exp004-real-data-transfer.md) measured the same quantity on photographs:

| matcher | random dots (exp001) | photographs (exp004) |
|---|---|---|
| block matching | 79.6% | 82.6% |
| **SGBM** | **9.0%** | **53.6%** |

Block matching transfers within three points — filling half-occlusions is a
property of winner-take-all matching, not of any stimulus. **SGBM's advantage does
not.** On photographs it fills more than half of them.

The [synthesis](synthetic-to-rendered-to-real.md) suggests why: random dots give
every pixel a locally unique signature, which is exactly what SGBM's uniqueness
and consistency constraints are built to exploit. Real scenes have smooth walls
and repeated structure. That is a hypothesis, not a result — it is filed as
[#10](https://github.com/visgraf/active-stereo/issues/10).

None of this makes exp001 wrong. It measured what it said it measured, correctly.
What it shows is that **a matcher comparison run on a synthetic stimulus can rank
methods by how well they exploit synthetic statistics** — which is worth knowing
before the next comparison, not after.

## The threats this experiment wrote down about itself

exp001's own `findings.md` is unusually hard on its result, and the caveats have
aged well.

- **"SGBM's foveal error of exactly 0.0 across all five seeds is suspicious."**
  The `disk` stimulus is piecewise-constant in depth — two integer disparities, no
  gradient, no curvature. A number that is exactly zero usually means the test was
  too easy, not that the method is exact.
- **The `disk` stimulus flatters block matching.** A square window assumes constant
  disparity across itself, which `disk` satisfies almost everywhere. On a slanted
  plane its 90th-percentile error is roughly four times worse.
- **The ADR-0003 coefficient is uncalibrated** at `1e-4`, and the foveal comparison
  is directly sensitive to it. A sweep was owed and never reported.
- **SGBM's variance is a constant, not a posterior width.** So the two matchers are
  not equally honest about their own uncertainty — which is precisely what L4
  consumes. This one became its own issue three experiments later
  ([#9](https://github.com/visgraf/active-stereo/issues/9)) and made two of
  exp004's verdict cells vacuous.

That last item is the pattern worth noticing. It was written down as a caveat in
the first experiment, sat there through two more, and only became consequential
when something finally depended on it.

## What it set up

Everything since has been a variation on the question exp001 stumbled into.
exp003 asked whether *missing* evidence and *fabricated* evidence are reported
differently — they are. exp004 asked whether that survives real photographs — the
behaviour does, and the calibration is worse than anyone had measured.

The remedies now open — [left-right consistency at L3](https://github.com/visgraf/active-stereo/issues/7)
and [a variance proxy that can express "no correspondent exists"](https://github.com/visgraf/active-stereo/issues/8) —
are both attempts to give block matching the thing SGBM was doing implicitly and
partially: a way to decline.

## Reproducing

```bash
python -m experiments.exp001_matcher_baseline.run \
    --config experiments/exp001_matcher_baseline/config.yaml
```

The comparative re-scores this stimulus with the shared metrics, so exp001's
numbers can be compared with the later families directly:

```bash
python scripts/make_comparative_figures.py
```
