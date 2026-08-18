# ADR-0012: Middlebury 2014 is the real-data corpus, and `doffs` is our vergence

- **Status:** Accepted
- **Date:** 2026-08-18
- **Context of discovery:** design; Stage 0 verification against `Adirondack-perfect`

## Context

Every quantitative result in this repository comes from a stimulus we authored.
exp001 used random-dot stereograms, exp002 synthetic gain manipulations, exp003
Blender renders of a material chart. All three bought *attribution* — we
controlled the generative process, so a failure had an identifiable cause — and
the briefing for exp003 books the debt that created explicitly: "A test chart is
not a scene. Attribution was bought at the cost of realism; these results
transfer to real imagery only insofar as real surfaces resemble flat painted
patches."

There is a second, sharper problem. ADR-0006 separates `scenes` from `geometry`
precisely so that the stimulus is not produced by the code path the estimator
inverts. That separation is structural, but it is not *independent*: both sides
were still written by us, against the same understanding of the same physics. A
shared misconception would be invisible to it.

## Decision

Adopt the **Middlebury 2014** datasets as the corpus for real-data evaluation,
loaded by `scenes.middlebury.MiddleburyScene`.

**The calibration maps onto `StereoRig` exactly.** Middlebury write
`Z = baseline * f / (d + doffs)`; L1 writes `d = f b (1/Z - 1/Zf)`. Equating them
gives `doffs = f b / Zf`, hence:

| `calib.txt` | `StereoRig` |
|---|---|
| `f` (from `cam0`) | `focal_px`, pixels, unchanged |
| `baseline` | `baseline / 1000` — **mm to m**, at the I/O boundary |
| `cy`, `cx` | `principal_point = (row, col)`, not `(x, y)` |
| `doffs` | `vergence = 2 arctan(doffs / 2f)` |

`doffs` is the x-offset between the two principal points — a *shifted frustum*.
This is a genuine external endorsement of ADR-0007: a calibrated physical rig,
built by people with no stake in our modelling choices, is described by the
off-axis model we chose, not by the toed-in one. Sign convention agrees with no
negation anywhere, since Middlebury's `d = x0 - x1` is positive for near surfaces
and so is ours.

**But that identity buys less than it appears to.** The two expressions are the
same expression, so a test showing `disparity_to_depth` reproduces
`b f / (d + doffs)` validates `rig_from_calib` and says nothing about physics.
`depth_from_disparity` is therefore written longhand from Middlebury's own
formula, keeping ADR-0006's separation intact.

**Scope:** `-perfect` variants only, at full resolution, downsampled by us.
Default factor 3.

## What Stage 0 verification changed

Three assumptions in the approved plan were wrong, and two of them were arguments
*for* the move. Recorded because the reasoning is what a future reader needs.

**`mask0nocc.png` is not distributed.** Not in the `scenes2014` zips, not in
`MiddEval3-data/GT0/GT1/GTy`. It is generated locally by
`MiddEval3-SDK-1.6/code/computemask.cpp`, which is a left-right cross-check at
1.0 px — the algorithm this repo already had. So:

- deriving `matched` ourselves reproduces their mask rather than approximating
  it, and `cross_check_disparity` now matches `computemask.cpp` **exactly** over
  2.88M verified pixels;
- the plan's claim that this corpus would give `cross_check_occlusion` its first
  independent test is **retracted**. There is no independent occlusion ground
  truth here. Agreement proves the implementation and nothing about whether 1.0 px
  is the right threshold.

Reproducing it exactly required fixing two deviations that are invisible on
continuous data and constant on quantised data: we rounded the *disparity* and
subtracted, where Middlebury subtract and round the *target coordinate* (on a
tie these differ by the parity of the column index, which is not a property of
the scene); and `np.rint` is half-to-even where C's `round` is half-away-from-zero.
Rounding the target is independently the more defensible operation, since it is
the coordinate actually used to index.

Their generator also leaves an out-of-bounds correspondent labelled *occluded*,
pooling a sensor limit with a fact about the scene. We keep `in_frame` separate,
per `scenes/base.py`. On `Adirondack` this moves ~14% of what Middlebury call
occlusion out of the occlusion statistic.

**Full resolution only.** `scenes2014` ships F alone; Q and H exist only in
MiddEval3, which drops the `im1E`/`im1L` lighting variants that motivated the
choice. We therefore downsample ourselves, which costs like-for-like leaderboard
comparability — bad-2.0 becomes an order-of-magnitude sanity check, not a
ranking.

**PFM is stored bottom-up**, verified rather than assumed: on `Adirondack` the
stored first row has median disparity 140 px against 55 px for the last, and the
near content is at frame bottom. Omitting the flip yields a vertically mirrored
ground truth with entirely plausible statistics.

## Alternatives considered

- **MiddEval3-Q as the corpus.** Smaller (~60 MB), pre-downsampled by Middlebury,
  directly leaderboard-comparable, and it carries `MotorcycleE` / `PianoL` /
  `PlaytableP` as separate scenes sharing ground truth with their base scenes.
  Rejected as the *primary* corpus because it drops `im1E`/`im1L` and with them
  most of the brightness-constancy axis. Held in reserve if our downsampler
  proves to be the weak link.
- **KITTI or ETH3D.** Larger and more ecologically varied, but LiDAR ground truth
  is sparse and semi-dense, which interacts badly with a framework whose central
  results are about *occlusion* and about declining to answer. Middlebury's dense
  ground truth with explicit unknowns is the better instrument for this question.
- **`-imperfect` variants.** They carry up to `dymax ≈ 1.5 px` of vertical
  disparity, which violates the rectified-rows assumption every matcher in
  `inference/` makes unconditionally. A good future stressor axis; a bad first
  move. `MiddleburyScene` raises on any scene with `dymax > 0`.
- **Downsampling ground truth by averaging**, matching the images. Rejected:
  averaging disparity across a depth discontinuity invents a surface at the mean
  depth that exists nowhere in the scene, and edges are where every occlusion
  statistic lives. Images get a box mean (a genuine antialiasing low-pass);
  disparity and masks get point-sampled at the block centre. The asymmetry is
  deliberate and documented in `_decimate`.

## Consequences

**Easier.** The transfer question becomes askable: do the exp001 and exp003
findings survive on photographs? Ground truth includes a measured noise floor
(`disp0-sd.pfm`, median 0.104 px on `Adirondack`), so a residual can be compared
against the scanner's own uncertainty instead of being assumed meaningful.

**Harder.** Rendering gave us every pixel's depth, albedo, gloss and material
index. Here we get disparity and nothing else — no appearance ground truth, so
exp003-style attribution by material is not available. Texture must be measured
from the image, which conflates albedo with shading exactly as exp003 warned.

**Forecloses, for now, the active loop.** L5 changes vergence and L6 changes
fixation; both require a new view, and a photograph has one. **This corpus
exercises L1–L4 only**, and that is a limit of the stimulus, not an oversight.
A vergence change is exactly a horizontal shift of the right image — deferred
deliberately, and worth its own plan.

**Data policy.** Blobs live outside the repository at `$ACTIVESTEREO_DATA_ROOT`
(default `~/datasets/middlebury2014`), fetched by `scripts/fetch_middlebury.py`
against a checksummed manifest in `configs/dataset/middlebury2014.yaml`. Nothing
is written to `data/`, per CLAUDE.md §2. The scene list is **pre-registered** in
that manifest and the fetch script refuses scenes outside it, because choosing a
subset after seeing results is post-hoc selection.

Middlebury's terms grant use and publication conditional on citation; the
required reference is recorded in the manifest.

## Verification

- `scripts/inspect_middlebury.py` reproduces every constant in this ADR from the
  files themselves.
- `tests/unit/test_middlebury.py` — synthetic PFM / PNG / calib fixtures, so the
  suite is green with no dataset present: the calibration mapping against
  hand-computed values, PFM endianness and row order, `inf` to `known`, the
  mm-to-metre conversion, `in_frame` at the frame edge, the rig-mismatch raise,
  the `-imperfect` refusal, and downsampling invariance of metric depth.
- `cross_check_disparity` reproduces `computemask.cpp` exactly on real
  `disp0`/`disp1` — the same algorithm, so anything short of exact is a bug here.
- `tests/regression/` — the tie-rounding case that made the two disagree.
