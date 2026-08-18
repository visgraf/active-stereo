# Architecture

## The loop

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

The outer loop is what makes this *active* inference: L6 chooses the next
fixation, which changes the rig's vergence state, which changes the generative
geometry at L1, which changes everything downstream. Perception and action are
not separable here.

## Layer responsibilities

| Layer | Package | Input | Output | Key abstraction |
|---|---|---|---|---|
| L1 | `geometry` | scene, rig | disparity field (px) | `depth_to_disparity` |
| L2 | `encoding` | stereo pair | response volume (K,H,W) | `DisparityEncoder` |
| L3 | `inference` | stereo pair / responses | `Estimate` (px) | `DisparityMatcher` |
| L4 | `scaling` | `Estimate` (px), rig | `Estimate` (m) | `scale_to_depth`, `fuse_mle` |
| L5 | `control` | `Estimate`, state | vergence command | `VergenceKalman` |
| L6 | `policy` | `Estimate` | next fixation | `next_fixation` |

## Stimuli

`scenes` sits beside L1 rather than inside it (ADR-0006). L1 is the generative
model the framework *reasons with*; `scenes` is the ground truth it is *evaluated
against*.

| Kind | Module | Carries depth in | Use when |
|---|---|---|---|
| Random-dot stereogram | `scenes.rds` | disparity only | Proving a depth estimate came from matching |
| Rendered | `scenes.blender` + `scripts/render_stereo.py` | all cues | Photometric realism, XR-relevant failure modes |
| Measured | `scenes.middlebury` + `scripts/fetch_middlebury.py` | all cues | Transfer to real imagery; ground truth we did not author |

`scenes.from_config(cfg)` builds any of them from a `scene:` block, returning a
**list** — a corpus is many scenes, an RDS is one, and no caller should branch on
which. Blobs for the measured corpus live outside the repository at
`$ACTIVESTEREO_DATA_ROOT` (ADR-0012).

A `StereoStimulus` carries three boolean masks plus an optional fourth,
deliberately separate: `matched` (has a right-image correspondent), `in_frame`
(the correspondent lands inside the sensor), and `known` (ground truth exists at
all — `None` for a synthesised stimulus, which knows every pixel).
`occluded = in_frame & ~matched & known` is the geometric quantity;
`out_of_frame` is a rig limit; `~known` is a gap in our knowledge, not a fact
about the scene (ADR-0011). Pooling any of them makes a smooth, unoccluded
surface look occluded. The categories therefore do **not** partition the frame;
`unknown_fraction` reports what is left over.

**Only L1–L4 are exercised by the measured corpus.** L5 changes vergence and L6
changes fixation; both need a new view, and a photograph has one. That is a
limit of the stimulus, not an oversight — see ADR-0012.

**Caveat on the horopter (ADR-0007).** L1's projection is a shifted-frustum
(off-axis) model whose zero-disparity locus is a fronto-parallel plane. The
Vieth–Müller circle in `geometry/horopter.py` is the toed-in, biological horopter.
They agree near the fixation axis and diverge with eccentricity. Renders use
off-axis so stimulus and model agree; closing the gap is open work.

## The three closures

**Scaling closure.** Disparity is dimensionless until L4. No module below L4 may
return metres. This is what keeps the metric ambiguity of stereo explicit rather
than smuggling a baseline into the matcher.

**Control-regime closure.** L5 consumes L3/L4 estimates *with their uncertainty*
and returns a command; it never re-derives depth. When the estimate is a refusal
(`nan`, `inf`), the controller coasts. See ADR-0001.

**Reference-frame closure.** Every public quantity documents its frame and unit.
The canonical set is in CLAUDE.md §3. Conversions happen only at `io` boundaries.

## Import direction

```
utils, types  ←  everything
geometry  ←  encoding  ←  inference  ←  scaling  ←  control  ←  policy
experiments  →  src        (never the reverse)
```

Cross-layer imports that skip a level are permitted where the framework itself
skips (L6 reads L4 estimates directly). Backward imports are not.

## Extension points

Adding a matcher: implement `DisparityMatcher`, add it to `configs/matcher/`,
and add a case to the matcher-comparison experiment. Nothing else changes — this
is the property the Protocol boundary buys.

Adding a cue: return an `Estimate` in metres and pass it to `fuse_mle`. The
fusion is agnostic to where a cue came from.
