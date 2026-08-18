# ADR-0011: Missing ground truth is a fourth mask, not a value of the other three

- **Status:** Accepted
- **Date:** 2026-08-18
- **Context of discovery:** design, forced by adopting Middlebury 2014 (ADR-0012)

## Context

Every stimulus this framework had seen was synthesised by us. An RDS knows the
disparity of every pixel because it placed the dots; a Blender render knows the
depth of every pixel because it traced the ray. Ground truth was total, and
`StereoStimulus` was built on that assumption without anyone deciding it.

Measured ground truth is not total. Middlebury's structured-light scanner leaves
holes wherever it got no usable return — dark surfaces, grazing angles, thin
structure — and encodes them as `inf` in the PFM. On `Adirondack-perfect` that is
0.60% of the frame; on scenes with dark or specular material it is larger.

`StereoStimulus` carried two boolean masks, `matched` and `in_frame`, deliberately
separated (`scenes/base.py`) because pooling them puts a band of border pixels
into every occlusion statistic. A scanner hole fits neither, and both available
homes were actively harmful:

- **As `~in_frame`** it becomes a field-of-view statistic — a claim that the rig
  could not see the correspondent, when in fact the rig saw it fine and the
  *scanner* failed.
- **As `in_frame & ~matched`** it becomes **half-occlusion**. That is the
  quantity exp001's headline result is stated in (79.6% of ground-truth
  half-occlusions filled confidently by block matching, against 9.0% for SGBM)
  and the quantity exp003 found the framework's uncertainty is *badly calibrated
  for*. Charging scanner holes to it would inflate the single number this project
  has argued from most, silently, and in the direction that flatters the finding.

The distinction is not a technicality. `matched` and `in_frame` are assertions
about **the scene**. "We do not know" is an assertion about **our knowledge of
it**. Those are different kinds of claim, and the existing two masks were split
apart for precisely this species of reason.

## Decision

`StereoStimulus` gains a fourth mask:

```python
known: NDArray[np.bool_] | None = None      # None means "everywhere"
```

`None` is the correct answer for a synthesised stimulus and keeps every existing
construction site untouched. Three derived properties become `known`-aware:

- `scorable` — was `matched`, is now `matched & known`. Scoring a matcher against
  a pixel whose true disparity nobody knows measures the scanner, not the matcher.
- `occluded` — `in_frame & ~matched & known`.
- `out_of_frame` — `~in_frame & known`.

`unknown_fraction` is added alongside `occlusion_fraction`.

Consequently **the three scene categories no longer partition the frame.** What
is left over is `~known`, and it is reported rather than absorbed. That is the
point: the alternative to an unpartitioned frame is a partition that lies.

## Alternatives considered

- **Sidecar on the scene object**, as `AppearanceGroundTruth` does for exp003
  (`scenes/blender.py`). Keeps the frozen shared dataclass untouched, which is
  what exp003 deliberately chose. Rejected here because appearance is optional
  enrichment that only one experiment reads, whereas `known` changes the meaning
  of `scorable` for *every* consumer. A sidecar makes correctness opt-in, and the
  failure mode of forgetting it is a plausible-looking number, not an error.
- **Mask unknown pixels to `nan` at load time and drop them.** Simplest, no
  contract change. Rejected: it discards the distinction between "the matcher
  declined" and "we cannot grade this", and it makes coverage — a headline metric
  in exp001 and exp003 — non-comparable across stimulus families, because the
  denominator would quietly differ.
- **A three-valued mask** (`known` / `occluded` / `matched` as an enum). Rejected:
  it forces the partition that this ADR exists to refuse, and reintroduces the
  `matched` / `in_frame` conflation that `scenes/base.py` already rejected once.

## Consequences

**Easier.** Any measured corpus can now be loaded honestly. Existing scorers
inherit the correct narrowing for free through `scorable`, without knowing this
happened, and without any change to exp001/exp002/exp003, whose published
run-ids stay valid because `known=None` reproduces the previous behaviour exactly.

**Harder.** Anyone reading `occluded`, `out_of_frame` and `matched` as a
partition is now wrong. That was already an unsafe reading, but it was true by
accident and is no longer.

**Forecloses.** Nothing, but it sets a precedent: masks in this dataclass
describe one thing each, and "we don't know" is its own thing.

## Verification

`tests/unit/test_scenes.py`:

- `known=None` reproduces the pre-ADR value of `scorable`, `occluded` and
  `out_of_frame` bit-for-bit on an RDS.
- supplying `known` narrows all three, and `unknown_fraction` matches.
- a `known` of the wrong shape raises from `__post_init__`.
- scanner holes appear in **neither** `occluded` nor `out_of_frame` — the
  regression this ADR exists to prevent.
