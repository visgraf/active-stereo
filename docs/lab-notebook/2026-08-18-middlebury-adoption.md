# 2026-08-18 — Middlebury 2014 as the real-data corpus

Branch `feat/middlebury-2014`. ADR-0011 (the `known` mask) and ADR-0012 (the
corpus and its calibration mapping) were written from what this session actually
established, not in advance.

## Provenance

- Source: `https://vision.middlebury.edu/stereo/data/scenes2014/zip/`
- Fetched so far: `Adirondack-perfect.zip`,
  sha256 `df1d9fdde1780dcba9b045898324226132405b33ad1d3fde399d2ce4b619c85a`
- Stored at `$ACTIVESTEREO_DATA_ROOT` = `~/datasets/middlebury2014`, outside the
  repository. Nothing written to `data/`.
- Manifest: `configs/dataset/middlebury2014.yaml`. Scene list pre-registered as
  the official 2014 training set (10 scenes); the fetch script refuses anything
  outside it.
- Citation required by Middlebury's terms: Scharstein et al., GCPR 2014.

## What the checkpoint overturned

The approved plan made three assumptions. All three were wrong, and two of them
were arguments *for* making the move at all. Verifying before writing loader code
is what caught them — the same discipline ADR-0009 came out of.

**`mask0nocc.png` is not distributed.** Not in `scenes2014`, not in any
`MiddEval3` bundle. It is generated locally by
`MiddEval3-SDK-1.6/code/computemask.cpp`, which turned out to be a left-right
cross-check at 1.0 px — the algorithm already in this repo.

So the plan's "free side-result — first independent test of
`cross_check_occlusion`" is **impossible**, and I deleted the claim rather than
restating it as something weaker. There is no independent occlusion ground truth
in this corpus. What replaces it is smaller and honest: our implementation
reproduces theirs exactly, which tests the implementation and says nothing about
whether 1.0 px is the right threshold.

Reading their source also settled the design call I was least sure of. Line 4 of
their loop leaves an out-of-bounds correspondent labelled `128 = occluded`, so
Middlebury pool a sensor limit with a fact about the scene — exactly what
`scenes/base.py` refuses to do. Re-deriving `in_frame` ourselves is load-bearing,
not fastidiousness: on `Adirondack` it moves ~14% of what they call occlusion out
of the occlusion statistic.

**Full resolution only.** `scenes2014` ships F alone; Q and H exist only in
MiddEval3, which drops the `im1E`/`im1L` variants the corpus was chosen for. We
downsample ourselves, which costs like-for-like leaderboard comparability.

**PFM is bottom-up**, verified rather than assumed: stored row 0 has median
disparity 140 px against 55 px for the last row, and the near content is at frame
bottom.

## The tie-rounding episode

Comparing our `matched` against a transcription of `computemask.cpp` on real
ground truth gave 99.9995% agreement — 6 pixels in 1.15M. That is precisely the
size of discrepancy that gets called noise and waved through, and it was not
noise. Every one of the six was an exact-half disparity, with two independent
causes:

1. We rounded the *disparity* and subtracted; they subtract and round the
   *target*. `x - rint(d)` is not `rint(x - d)` on a tie — with `d = 131.5` at
   `x = 2395` the first gives 2263 and the second 2264, and which wins depends on
   the parity of the column index, which is not a property of the scene.
2. `np.rint` breaks ties to even; C's `round` breaks them away from zero.

Neither is reachable from continuous ground truth, which is why three
experiments' worth of RDS and Blender work never touched it, and why the Blender
path is byte-identical after the fix (verified on four probes). A quantised
structured-light scanner produces ties constantly.

After the fix: exact agreement over 2.88M pixels in three separate bands.
Pinned in `tests/regression/test_adr0012_cross_check_tie_rounding.py` against the
invariant rather than a captured output, so a future rewrite is free to be faster
and not free to be differently wrong.

**Lesson, and it is the same one as exp003's variance episode:** the instinct on
seeing 6-in-a-million was to accept it. Measuring *why* is what turned a
plausible dismissal into two real defects.

## A prediction of mine that was wrong, and measured

I removed the `cost.copy()` in `BlockMatcher` and wrote in the source that it was
"the single largest allocation in this method". Measured: peak went 101.4 MB to
93.7 MB on a 200×300 pair at D = 95, not the ~46 MB the volume's size implies.
The binding allocation is `np.argmin(cost, axis=0)` — reducing over the *leading*
axis of a C-contiguous array is strided, and numpy buffers a full second volume.

Corrected the comment. Removing that too needs a streaming two-pass matcher
(2× compute for O(H·W) memory), which is not worth it while ~1 GB at downsample 3
is not binding.

## First real-data numbers — NOT findings

`Adirondack-perfect`, downsample 3 (662×960), `ndisp` 94, GT noise floor
0.0347 px. Scored on `scorable` = matched ∧ known.

| matcher | coverage | bad-2.0 | median \|Δd\| | median \|ΔZ\| | hallucination in occlusion |
|---|---|---|---|---|---|
| block | 70.9% | 52.44% | 2.634 px | 53.8 mm | 75.9% |
| sgbm | 87.8% | 4.77% | 0.226 px | 5.2 mm | 40.5% |

**One scene, no pre-registration, no falsifier.** This was a loader check and
nothing more. It is recorded because the loader either works or it does not, and
these numbers say it does: SGBM's bad-2.0 is in a believable range for a
classical method on one of the easier scenes, and block matching's 75.9%
occlusion hallucination sits close to exp001's 79.6% on random-dot stimuli.

Two things to look at properly in exp004, stated as questions rather than
results:

- Block matching's reported variance was **lower** in occluded regions than in
  matched ones (ratio 0.6×) on this scene. exp003 found 5× on renders. If that
  survives across the corpus it sharpens exp003's calibration finding
  considerably; on one scene it is an anecdote.
- SGBM reported a near-constant variance (0.250 px² in both regions). Worth
  checking whether its variance carries any information at all.

Both need the full ten scenes and a falsifier written down first.

## Integration wrinkle worth remembering

`SGBMMatcher` requires `max_disparity` divisible by 16; `MiddleburyScene.ndisp`
is whatever `calib.txt` says (94 here). Round **up** to the next multiple of 16 —
rounding down would silently truncate the search range below the scene's true
maximum disparity.

## State

164 tests passing, ruff and mypy clean. Nothing committed.

Not done, and deliberately: exp004 itself, which needs its tracking issue and
pre-registered falsifiers before a runner exists (`experiments/README.md`).
