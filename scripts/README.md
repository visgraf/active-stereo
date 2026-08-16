# Scripts

CLI entry points and Blender render scripts. Scripts orchestrate; they do not
implement. Anything reusable belongs in `src/activestereo/`.

## `demo_active_stereo.py`

The successor to the prototype's `active_stereo_demo.py`. Runs the full six-layer
loop on a random-dot stereogram or a Blender render and writes a manifest-pinned
summary to `results/`.

```bash
python scripts/demo_active_stereo.py --scene disk --matcher sgbm --plot
python scripts/demo_active_stereo.py --scene corrugated --noise 0.1
python scripts/demo_active_stereo.py --render data/scenes/office_01
```

Scenes: `disk`, `staircase`, `slanted_plane`, `corrugated`.

## `render_stereo.py` (Blender)

Runs inside Blender's bundled Python, which is **not** the project environment —
no NumPy, no PyYAML, no `activestereo`. Config is JSON for that reason.

```bash
blender --background --python scripts/render_stereo.py -- \
    --out data/scenes/testchart --procedural

blender --background scene.blend --python scripts/render_stereo.py -- \
    --out data/scenes/office_01 --config configs/scene/blender_procedural.json
```

The bare `--` separates Blender's arguments from the script's.

Writes `left.exr`, `right.exr` (multi-layer: Combined + Depth) and `rig.json`.
Both eyes get a depth pass because a single one cannot express half-occlusion,
and occlusion is the phenomenon several results turn on.

Needs the `blender` extra for reading: `pip install -e ".[blender]"`. OpenCV
cannot address named EXR layers -- it returns whichever channels come first,
silently. See ADR-0010.

`--mode compositor` selects the older File Output path. It works on Blender 4.x
and is broken on 5.2; the default `--mode multilayer` uses the render output
path, which has been stable for a decade.

Stereo mode is **off-axis**, matching L1 exactly. See ADR-0007 for why toe-in
would silently corrupt every foveal-confinement result.

### `inspect_exr.py`

Lists the channels and value ranges in a rendered EXR. First thing to run when
depth looks wrong -- it says what Blender actually wrote rather than leaving you
to infer it.

```bash
python scripts/inspect_exr.py /tmp/calib/left.exr
```

A healthy render shows a `...Depth.Z` (or `.V`) channel whose median is the scene
distance in metres, and `...Combined.*` channels well away from zero.

### Calibrate the depth pass once per Blender version

Blender's depth pass may be radial (distance along the ray) or planar (distance
along the view axis) depending on version and engine. Do not assume:

```bash
blender --background --python scripts/render_stereo.py -- --out /tmp/calib --procedural
python -c "
from activestereo.scenes.blender import load_render, infer_depth_convention
import cv2, os; os.environ['OPENCV_IO_ENABLE_OPENEXR']='1'
d = cv2.imread('/tmp/calib/depth_left.exr', cv2.IMREAD_UNCHANGED)[...,0]
print(infer_depth_convention(d))"
```

Render a fronto-parallel wall for this, record the answer in `rig.json`, and note
it in the lab notebook. An uncorrected radial pass looks like a peripheral depth
error of a few percent — indistinguishable from an ADR-0003 modelling result.
