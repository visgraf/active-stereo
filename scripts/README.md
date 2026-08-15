# Scripts

CLI entry points and Blender render scripts. Scripts orchestrate; they do not
implement. Anything reusable belongs in `src/activestereo/`.

## Blender

`render_stereo.py` (to migrate, issue #2) runs inside Blender's Python:

```bash
blender --background scene.blend --python scripts/render_stereo.py -- --config configs/scene/textured_slant.yaml
```

Note the `--` separating Blender's arguments from the script's.

Blender's bundled Python is not the project environment. Keep render scripts
dependency-light — standard library and `bpy` only — and do the analysis outside
Blender on the rendered output.
