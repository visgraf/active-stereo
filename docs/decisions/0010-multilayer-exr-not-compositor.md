# ADR-0010: Render via multi-layer EXR, not the compositor

- **Status:** Accepted
- **Supersedes the render path chosen in:** ADR-0009 (which remains valid on
  version-adaptive API handling)
- **Date:** 2026-08-15
- **Context of discovery:** Six failed attempts to get File Output nodes working
  on Blender 5.2 LTS

## Context

`render_stereo.py` originally wrote its passes through compositor File Output
nodes. On Blender 5.2 that path failed four times in succession, each a different
API break:

1. `Scene.node_tree` removed in favour of `Scene.compositing_node_group`
2. `CompositorNodeOutputFile.base_path` / `.file_slots` replaced by
   `.directory` / `.file_name` / `.file_output_items`
3. `format.media_type` defaulting to `MULTI_LAYER_IMAGE`, which restricts
   `file_format` to a single legal value
4. After all three were fixed, the nodes wrote **nothing at all** — no exception,
   no warning, four nodes and three links present, `use_compositing` true

A control render through `scene.render.filepath` succeeded in the same run,
producing correct per-eye files. That is the decisive evidence: the render path
works; the compositor path does not.

Four breaks within one major version is not bad luck, it is a measurement. The
compositor's Python API is being actively reworked. `scene.render.filepath` with
`write_still=True` has been stable for a decade.

## Decision

Default to `--mode multilayer`: set `image_settings.file_format` to
`OPEN_EXR_MULTILAYER` with `use_pass_z`, and let the ordinary render output path
write one EXR per eye containing Combined and Depth as named layers. **No
compositor node tree at all.**

`activestereo.scenes.blender.read_multilayer_exr` extracts the layers, and
`load_render` detects the layout automatically, so the rest of the pipeline is
unchanged.

The compositor path is retained behind `--mode compositor` for older Blender,
where it is known to work.

## Alternatives considered

- **Keep debugging the compositor.** Rejected on evidence. Each round cost a
  full render-crash-edit cycle, the failure mode had degraded from a clear
  exception to a silent no-op, and the API is a moving target.
- **Pin Blender 4.x.** Rejected in ADR-0009 and still rejected: it freezes the
  renderer for the life of the project.
- **Read multi-layer EXR with OpenCV.** Not possible. OpenCV cannot address named
  layers; it silently returns whichever channels come first, which for a Blender
  multi-layer file is the beauty pass masquerading as depth. A silent wrong
  answer is the worst available outcome.
- **Two renders, beauty as PNG and depth as single-layer EXR.** Rejected:
  selecting *which* pass reaches the main output requires the compositor, which
  is the thing being avoided.

## Consequences

- One new optional dependency, `OpenImageIO`, in the `blender` extra. This is the
  cost of the decision and it is worth it: the compositor surface it replaces
  broke four times, and OpenImageIO is the reference EXR implementation.
- Fewer moving parts: no node tree, no node properties, no file-slot naming, no
  per-node colour management. Colour management is set once on
  `image_settings`, where `OVERRIDE` keeps the view transform off metric depth.
- Beauty and depth arrive in one file per eye, so they cannot desynchronise.
- `read_multilayer_exr` **is testable**, unlike everything inside Blender, and is
  covered by tests using synthetic EXRs with Blender's channel naming.

## The layout trap this exposed

Blender writes multi-layer EXR as a **multi-part** file: one EXR part per pass,
each with plain channel names (`R`, `G`, `B`, `A` / `Z`) and the layer identity in
the part's `name` attribute -- *not* one wide part with prefixed channel names.

A reader that stops at part 0 returns the beauty pass and reports no depth layer,
with nothing at all to indicate a layer was missed. That is the same failure
shape as OpenCV silently returning the wrong channels, and it is why the reader
walks every part and both file layouts are covered by tests.

A related trap in OpenImageIO itself: `ImageInput.read_image`'s first two
arguments are *subimage* and *miplevel*. Passing `0` while positioned on a later
part re-seeks to part 0 with a mismatched channel count and **segfaults** rather
than raising. Always pass the current part index.

## Verification

`tests/unit/test_blender_loader.py` — round-trips synthetic multi-layer EXRs
written with Blender's `<Layer>.<Pass>.<Channel>` convention through
`read_multilayer_exr` and `load_render`, including non-hit sentinels, both depth
channel spellings (`.Z` and `.V`), and occlusion recovery across two eyes.
