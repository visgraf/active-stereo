# ADR-0009: Branch on the Blender API rather than pin a version

- **Status:** Accepted
- **Date:** 2026-08-15
- **Context of discovery:** First real run of `render_stereo.py` on Blender 5.2 LTS

## Context

The render script was written against the Blender 4.x compositor API and failed
immediately on 5.2:

    AttributeError: 'Scene' object has no attribute 'node_tree'

Blender 5.0 made the compositing node tree its own datablock, reached via
`Scene.compositing_node_group`; `Scene.node_tree` is gone, `use_nodes` is
deprecated (always True, setting it does nothing, removal in 6.0), the Composite
node was removed in favour of a Group Output, and several compositor nodes were
replaced by Shader counterparts.

This will happen again. Blender's Python API is not stable across major versions,
and a research codebase that must still run in five years cannot assume it is.

## Decision

Detect the API shape at runtime and branch, rather than pin a Blender version:

```python
if hasattr(scene, "compositing_node_group"):   # 5.0+
    tree = bpy.data.node_groups.new("active_stereo_comp", "CompositorNodeTree")
    scene.compositing_node_group = tree
else:                                           # <= 4.x
    scene.use_nodes = True
    tree = scene.node_tree
```

The File Output node moved in the same release: `base_path`, `file_slots`, and
`layer_slots` were replaced by `directory`, `file_name`, and `file_output_items`.
Same treatment -- `hasattr(node, "directory")` selects the branch.

The same principle applied three more times: engine identifiers are read from
`RenderSettings.bl_rna` instead of hardcoded (EEVEE has been renamed twice);
per-eye filename suffixes are read from `scene.render.views[*].file_suffix`
instead of assumed to be `_L`/`_R`; and `Material.use_nodes` is only set when
`node_tree` is actually absent, which silences the 5.x deprecation warning.

Added an `--inspect` flag that dumps exactly the API surface the script depends
on -- including the *property names* of the File Output node and its format
settings, not just whether the node exists. When Blender next moves something,
that output identifies it in one run rather than one run per broken attribute.
Both breaks so far cost a full render-crash-edit cycle each; this is the fix for
the cycle, not just for the breaks.

## Alternatives considered

- **Pin Blender 4.x in the dev container.** Rejected: it freezes the renderer for
  the life of the project and guarantees a painful migration later, at a moment
  chosen by circumstance rather than by us.
- **Require 5.0+ and drop the legacy path.** Tempting, and the branch costs about
  fifteen lines. Rejected because collaborators and cluster images lag, and a
  script that runs on one machine is not a reproducible pipeline.
- **Abandon the compositor; use multilayer OpenEXR.** Genuinely attractive —
  `OPEN_EXR_MULTILAYER` with `use_pass_z` writes every pass with no compositor at
  all, sidestepping the API entirely. Rejected for now because OpenCV cannot read
  named EXR layers, so it would force OpenImageIO or the `OpenEXR` bindings into
  the dependency list. Revisit if the compositor breaks again; the trade is a
  dependency for a much smaller API surface.

## A third lesson: discovery must search the right object

The File Output node's mode enum is not on the node. It is
`node.format.media_type`, defaulting to `MULTI_LAYER_IMAGE`, which restricts
`file_format` to exactly one value. The first RNA-discovery attempt scanned only
`node.bl_rna.properties`, found nothing, and **returned silently** -- so the
failure surfaced one layer downstream as a confusing enum error.

Two corrections. Discovery now walks the node *and* its `format`. And a
discovery function that finds nothing must say so: silent `(None, None)` turned a
precise diagnosis into a guess.

## A fourth lesson: the dump found a bug nobody was looking for

Printing every settable property to diagnose the mode enum also revealed
`save_as_render` on the File Output node. Left on, Blender applies the scene view
transform (AgX/Filmic) when writing -- which would have tone-mapped the **depth
pass**, silently turning metres into nonsense while producing a
perfectly plausible-looking EXR.

Nothing in the pipeline would have caught this. `load_render` would have returned
finite, smoothly varying depth; disparities would have been wrong by a nonlinear
function of depth. It is exactly the class of error the repo's invariants exist to
prevent, in the one component the invariants cannot reach.

The beauty pass keeps `save_as_render = True`; the depth pass gets `False` plus
`color_management = "OVERRIDE"`.

## A fifth lesson: introspection can be confidently wrong

`RenderSettings.bl_rna.properties["engine"].enum_items` reports only the
**static** enum. Render engines registered by add-ons -- Cycles among them --
appear only in the context-resolved enum. The script therefore announced

    engine 'CYCLES' not available in this build (offers ['BLENDER_EEVEE'])

on a machine where Cycles was plainly available in the GUI, and quietly rendered
everything in EEVEE for several rounds.

This is worse than the API breaks: those failed loudly, this one produced a
confident false statement and carried on. Availability is now tested by
*attempting the assignment*, which succeeds exactly when the engine is
registered. Where a capability can be exercised, exercise it rather than asking a
registry whether it exists.

## A second lesson: silent fallbacks

`--engine CYCLES` fell back to EEVEE on a build where the Cycles add-on was not
enabled, and `--samples` was silently ignored because EEVEE spells it
`eevee.taa_render_samples`. The render succeeded and looked fine. A render
campaign that straddles two engines and two sample counts without saying so is
exactly the sort of thing that surfaces months later as unexplained variance.

The script now tries to enable the Cycles add-on, reports the substitution on
stderr, and sets whichever samples property the active engine actually uses.
`--engine` also lost its argparse `choices` list, which would have rejected the
valid identifier this build offers.

## Consequences

- The script runs on 4.x and 5.x, and reports clearly when it cannot.
- `--inspect` makes the next break diagnosable in one run instead of a cycle of
  render-crash-edit.
- Runtime branching cannot be type-checked or covered by the test suite, since
  `bpy` exists only inside Blender. This script remains **the least-verified code
  in the repository**, and results derived from renders should be treated with
  correspondingly more suspicion than results from RDS stimuli, which are fully
  tested.

## Verification

None automated — see above. Verified by hand on Blender 5.2 LTS. Record the
version, the depth-pass convention, and the convergence distance in
`docs/lab-notebook/` for every render campaign.
