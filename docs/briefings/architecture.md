# The architecture: six layers, three closures, and one honest map of what is wired

**Reference:** [`docs/architecture.md`](../architecture.md) is the specification.
This is the account you would give out loud — what the structure is *for*, which
parts are load-bearing, and which parts do not yet exist.

---

## The one-sentence version

Stereo depth is treated as **active Bayesian inference**: the system does not
merely estimate depth from a fixed pair of images, it chooses where to look next,
and looking changes the geometry that produced the images. Perception and action
are not separable, so the code is not allowed to separate them either.

```
                    ┌──────────────────────────────────────────┐
                    │                                          │
   scene ──▶ L1 geometry ──▶ L2 encoding ──▶ L3 inference ──┐  │
             (generative)     (energy model)   (disparity)  │  │
                                                            ▼  │
                                                     L4 scaling │
                                                   (metric +    │
                                                    cue fusion) │
                                                            │   │
                                          ┌─────────────────┘   │
                                          ▼                     │
                                    L5 control ──▶ L6 policy ───┘
                                    (vergence)     (where next)
```

The outer arrow is the whole point. L6 picks the next fixation, which changes the
rig's vergence, which changes the generative geometry at L1, which changes
everything downstream.

## Why the layers are the directory names

The six layers are the top-level modules ([ADR-0004](../decisions/0004-layer-module-boundaries.md)),
which sounds like bookkeeping and is not. It means **a layer boundary is a place
where you can substitute an implementation without touching anything else**.

Each boundary is a `Protocol` — a declared contract, not a base class:

| Protocol | Layer | Contract |
|---|---|---|
| `Scene` | stimulus | produce a stereo pair *with ground truth* |
| `DisparityEncoder` | L2 | stereo pair → response volume `(K, H, W)` |
| `DisparityMatcher` | L3 | stereo pair → `Estimate` in **pixels** |

The payoff is concrete: adding a matcher means implementing `DisparityMatcher` and
adding a line to a config. Nothing else changes. Four experiments have now been
run across three stimulus families by exactly this substitution.

## The three closures

These are the rules that make the layering mean something rather than just being
folders.

### Scaling closure — disparity is dimensionless until L4

No module below L4 may return metres. Disparity in pixels is what a matcher can
actually know; converting it to a distance requires the baseline and the vergence
state, which are properties of the *rig*, not of the images.

This keeps stereo's metric ambiguity **explicit** instead of smuggling a baseline
into the matcher, where it would silently become an assumption. The conversion
lives in one function, `scaling.scale_to_depth`, together with the uncertainty
propagation that goes with it:

```
Z = 1 / (d/(f·b) + 1/Zf)        var(Z) = (Z² / (f·b))² · var(d)
```

The `Z²` is not a detail. It is why far depth is badly constrained by stereo
alone, and therefore why L4 exists to fuse other cues at all.

### Control-regime closure — L5 consumes uncertainty, never re-derives depth

The controller takes an estimate *with its variance* and returns a command. It
never recomputes depth from images. When the estimate is a refusal — `nan` — the
controller **coasts** rather than guessing ([ADR-0001](../decisions/0001-windowed-median-vergence.md)).

That ADR exists because the obvious implementation is wrong: reading vergence
error from the single pixel at the fovea is one sample of a noisy field, taken at
exactly the point where matching is hardest, because a fixation target is often
a texture-poor object boundary. A windowed median is what makes the loop stable.

### Reference-frame closure — every quantity states its units and frame

Disparity in pixels, left-image convention, positive = crossed. Depth in metres,
cyclopean, `+Z` forward. Angles in radians internally; degrees appear only at I/O
boundaries. Image coordinates `(row, col)`, never `(x, y)` without saying so.

Conversions happen at boundaries and nowhere else. When Middlebury's calibration
arrived in millimetres, exactly one line converted it
([ADR-0012](../decisions/0012-middlebury-real-data-corpus.md)).

## Two conventions that have each cost a real bug

**Invalid means `nan`, never `0` or `-1`.** A sentinel disparity of `-1` becomes a
plausible depth downstream and is never seen again. `nan` propagates loudly.

**Mask before you mix.** Any operation that spatially combines pixels — blur,
filter, downsample — must exclude invalid ones first
([ADR-0002](../decisions/0002-saliency-validity-masking.md)). That ADR was written
after the gaze policy looped forever on an occlusion band: blurring a saliency map
that still contained invalid pixels made the occlusion read as maximally
uncertain, therefore maximally attractive, therefore the thing to fixate — and no
fixation could resolve it, because the occlusion is geometric.

## Uncertainty is the currency

[ADR-0005](../decisions/0005-uncertainty-first-class.md): every estimator returns
`Estimate(value, variance)`. Never a bare number.

This is forced by the framework being Bayesian at all. L4 fuses by inverse
variance, L5 gates on it, L6 maximises information against it. Recovering
uncertainty after the fact is impossible — the information that produced it (cost
curvature, filter innovation) is local to the estimator and gone by the time a
caller asks.

**And it has a hole, which four experiments took to find.** ADR-0005 requires a
variance; it never required that variance to be *informative*, or *correct*.
`SGBMMatcher` returns a constant. And the block matcher's curvature-derived
variance turns out to be [anti-calibrated in half-occlusions](exp004-real-data-transfer.md) —
most confident exactly where it has no correspondent at all. Both are open issues
([#8](https://github.com/visgraf/active-stereo/issues/8),
[#9](https://github.com/visgraf/active-stereo/issues/9)); neither is a bug in the
ADR so much as a demonstration that a contract can be satisfied vacuously.

## The stimulus ladder

`scenes` sits *beside* L1, not inside it ([ADR-0006](../decisions/0006-scenes-as-a-separate-package.md)).
L1 is the generative model the framework reasons *with*; `scenes` is the ground
truth it is evaluated *against*. If the stimulus came out of the code path the
estimator inverts, a perfect score would prove nothing.

| Kind | Ground truth | Buys | Costs |
|---|---|---|---|
| Random-dot stereogram | placed by us | depth can *only* come from matching | no photometry, no edges |
| Blender render | traced by us | photometric realism, controlled appearance | still ours; a chart is not a scene |
| Middlebury photographs | measured by a scanner | realism, external calibration | no appearance ground truth, holes |

A `StereoStimulus` carries four masks, deliberately separate: `matched`,
`in_frame`, and `known` — plus `occluded = in_frame & ~matched & known` derived
from them. Pooling any two makes a smooth surface look occluded, or charges a
scanner hole to geometry ([ADR-0011](../decisions/0011-ground-truth-known-mask.md)).
They do **not** partition the frame, and `unknown_fraction` reports the remainder
rather than absorbing it.

The [synthesis across all three families](synthetic-to-rendered-to-real.md) is
what the ladder was built for: it separates results that are about stereo
matching from results that were about the stimuli we happened to build.

## What is actually wired — the honest map

This is the part a specification will not tell you.

| Path | Status |
|---|---|
| L1 → L3 → L4 | **exercised by every experiment** (exp001, exp003, exp004) |
| L4 → L5 → L6 → L1 | closes in `scripts/demo_active_stereo.py`, and in the integration tests |
| **L2 → L3** | **does not exist** |
| L4 cue fusion with >1 cue | never run outside unit tests |

**L2 is an island.** Outside its own unit tests, `GaborEnergyEncoder` is consumed
by exactly one thing: exp002's own runner. Nothing in `inference/` reads a
response volume.
The energy model is validated in isolation and is not part of the pipeline,
because connecting it needs a decoder — something that turns `(K, H, W)` of
population response into an `Estimate` with a variance — and that does not exist
yet. Until it does, exp002's result is a statement about a component, not about
the system.

**`fuse_mle` has only ever had one cue.** The MLE fusion at L4 is implemented,
tested and correct, and outside the test suite nothing calls it at all — no
experiment has a second cue to give it. Its value
so far is structural: it is what makes "return a variance" load-bearing rather
than decorative, and it is the mechanism through which an over-confident occluded
estimate does damage.

Neither gap is a defect. Both are places where the architecture is currently a
promise rather than a demonstration, and saying which is which is the point of
this section.

## Where the findings have landed

Four experiments, and the through-line is not about accuracy:

1. **Declining matters more than matching.** A matcher that returns `nan` where
   there is no correspondent is telling the truth; one that returns a number
   injects a fabricated measurement into inverse-variance fusion.
   ([exp001](exp001-matchers-and-the-baseline.md))
2. **The energy model's gain invariance is exact**, and its per-pixel precision is
   not. ([exp002](exp002-energy-models.md))
3. **Missing evidence is reported honestly; fabricated evidence is not.**
   ([exp003](exp003-appearance-and-matching.md))
4. **On photographs it is worse than that** — the confidence ordering inverts.
   ([exp004](exp004-real-data-transfer.md))

Every one of those is a statement about **uncertainty**, not about depth error.
That is the architecture doing its job: because `Estimate` forced variance to be
first-class from the start, the interesting failures were visible as calibration
failures rather than as unexplained error.

## How to read this codebase

1. `CLAUDE.md` — the constitution. Units, frames, invariants.
2. `docs/decisions/` — the accumulated *why*. Start at 0001–0005.
3. `docs/architecture.md` — the specification this briefing narrates.
4. The module you are about to touch, and its tests.

`docs/briefings/` is the intuitive layer over `experiments/*/findings.md`, which
stay the records of record — pinned to a run-id and a git SHA. Where a briefing
and a `findings.md` disagree, the briefing is stale.
