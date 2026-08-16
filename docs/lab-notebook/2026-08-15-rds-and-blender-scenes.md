# 2026-08-15 — RDS and Blender stimulus migration

**Status:** `scenes` package landed, 63 tests green, exp001 producing real results

## What happened

Ported the prototype's two demo families into the repo as a first-class `scenes`
package (ADR-0006): random-dot stereograms in `scenes/rds.py`, Blender rendering
in `scripts/render_stereo.py` with a loader in `scenes/blender.py`.

RDS synthesis is a forward warp with a z-buffer rather than a region shift, so
half-occlusion comes out with the correct geometry and becomes *ground truth*
instead of something a matcher has to be graded on guessing.

## Three things found along the way

**1. A latent inconsistency inside L1 (→ ADR-0007).** Configuring the Blender
stereo camera forced a choice between off-axis and toe-in convergence, and that
exposed the fact that `geometry/projection.py` implements a shifted-frustum rig
(planar zero-disparity locus) while `geometry/horopter.py` computes the
Vieth–Müller circle (toed-in). These are different rigs. They agree near the
fixation axis and diverge with eccentricity — which is precisely the variable
ADR-0003 makes everything sensitive to. Neither half was wrong on its own; they
had simply never been used together. This has a paper consequence and must not be
left for a reviewer to find.

**2. Out-of-frame is not occlusion.** The first `matched` mask conflated "a nearer
surface hid the partner" with "the partner fell off the sensor". The result: a
smooth slanted plane, which has no occlusion at all, reported a border band of
false occlusion, and the adjacency test failed. Split into `matched` and
`in_frame`, with `occluded = in_frame & ~matched`. Same shape of error as
nan-vs-sentinel: two different facts sharing one representation.

**3. The fixation plane must not touch the scene.** The first demo run recovered
only 13% of matched pixels. Cause: the background sat at exactly the fixation
distance, hence disparity 0, hence the *endpoint* of the search range — which the
matcher correctly rejects, since index 0 has no left neighbour for the parabolic
fit. Moved the default fixation to 2.5 m, behind everything. This is a stimulus
design constraint, now documented in `scenes/depthmaps.py`.

## Wrong predictions I made (worth recording)

I wrote an integration test asserting that a smooth surface would be recovered
*more completely* than a stepped one. It failed: coverage on matched pixels was
97.5% vs 98.5%, i.e. marginally the other way. The premise was wrong — excluding
occluded pixels from the denominator removes exactly the effect I predicted, and
what remains is the frontoparallel bias, which penalises the *gradient*. Replaced
with the correct claim: p90 disparity error is ~4× higher on the slanted plane.

## exp001

Now runs on a real stimulus and meets both acceptance criteria. The headline is
not depth error (~1 mm difference) but hallucination in occlusions: block 80%,
SGBM 9%. SGBM's advantage is that it *declines* better, not that it matches
better. SGBM's exactly-zero foveal error across five seeds is flagged as
suspicious in `findings.md` — the disk stimulus is piecewise-constant and too easy.

## Blender path, first working render (Blender 5.2 LTS, Cycles)

Six rounds. Worth recording what the failures actually were, because only two of
them were Blender's fault:

| Symptom | Cause |
|---|---|
| `Scene.node_tree` AttributeError | Blender 5.0 API change (ADR-0009) |
| `base_path` AttributeError | Blender 5.0 API change |
| `enum "PNG" not found` | `format.media_type` defaults to MULTI_LAYER_IMAGE |
| File Output wrote nothing | Unresolved. Abandoned the compositor (ADR-0010) |
| "Cycles not available" | **Mine.** Static RNA omits add-on engines |
| Dark, untextured render | **Mine.** Inverted colour ramp; no world |
| Depth pass "missing" | **Mine.** Reader stopped at EXR part 0 |
| Beauty pass wrong | **Mine.** Cycles' Noisy Image averaged into Combined |

The last two are the instructive ones. Both would have produced *plausible*
output -- a photograph-like image, smoothly varying depth -- while being wrong.
Neither would have been caught by anything downstream. Both are now covered by
tests against synthetic EXRs in the exact layouts Cycles emits.

First good render: Combined median 0.478, Depth min 0.773 m (front of the nearer
sphere: centre at 1.0 m, radius 0.25) and median 3.0 m (backdrop). Geometry
confirmed by two independent numbers.

## Next

- Rerun exp001 across all four depth maps; report per-stimulus.
- Calibrate the ADR-0003 coefficient with a sweep.
- ADR-0007 item 4: derive a toed-in L1 projection and quantify the divergence.
- Verify the Blender depth-pass convention on the actual Blender version with
  `infer_depth_convention`, and record it in `rig.json`.
