"""Render a stereo pair with depth ground truth from Blender.

Runs inside Blender's bundled Python, which is **not** the project environment.
Dependencies are therefore limited to the standard library and ``bpy`` -- no
NumPy, no PyYAML, no ``activestereo``. Config is JSON for that reason.

Usage
-----
    blender --background scene.blend --python scripts/render_stereo.py -- \
        --out data/scenes/office_01 --config configs/scene/blender_office.json

    # or with no .blend, building a procedural test scene:
    blender --background --python scripts/render_stereo.py -- \
        --out data/scenes/testchart --procedural

Note the bare ``--``: everything after it goes to this script rather than to
Blender.

Outputs, in ``--out``
---------------------
    left.png  right.png            the stereo pair
    depth_left.exr  depth_right.exr  depth passes, one per eye
    rig.json                        camera parameters for ``rig_from_blender``

Both eyes get a depth pass because a single one cannot express half-occlusion,
and occlusion is the phenomenon several of our results turn on.

Stereo mode is **off-axis** (shifted frustum), not toe-in. See ADR-0007: off-axis
matches the L1 model exactly and introduces no vertical disparity, whereas toe-in
would produce a Vieth-Müller horopter that L1 does not currently model.
"""

import argparse
import json
import os
import sys

import bpy


def parse_args(argv):
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True, help="output directory")
    p.add_argument("--config", default=None, help="JSON config; CLI flags override")
    p.add_argument("--resolution", type=int, nargs=2, default=[640, 480])
    p.add_argument("--lens-mm", type=float, default=35.0)
    p.add_argument("--sensor-width-mm", type=float, default=36.0)
    p.add_argument("--interocular", type=float, default=0.064, help="baseline, metres")
    p.add_argument("--convergence", type=float, default=1.4, help="metres")
    p.add_argument("--samples", type=int, default=64)
    p.add_argument("--engine", default="CYCLES", choices=["CYCLES", "BLENDER_EEVEE_NEXT"])
    p.add_argument("--procedural", action="store_true", help="build a test scene")
    args = p.parse_args(argv)

    if args.config:
        with open(args.config) as f:
            cfg = json.load(f)
        for k, v in cfg.items():
            k = k.replace("-", "_")
            if hasattr(args, k) and f"--{k.replace('_', '-')}" not in argv:
                setattr(args, k, v)
    return args


def build_procedural_scene():
    """A textured backdrop with foreground objects at known depths.

    Deliberately high-frequency and non-repeating: repeating texture creates
    matching ambiguity that is indistinguishable from matcher failure, which
    would confound every comparison run on the scene.
    """
    bpy.ops.wm.read_factory_settings(use_empty=True)

    def noise_material(name, scale=40.0):
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        nt = mat.node_tree
        bsdf = nt.nodes["Principled BSDF"]
        tex = nt.nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = scale
        tex.inputs["Detail"].default_value = 8.0
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.interpolation = "CONSTANT"
        nt.links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = 1.0
        return mat

    bpy.ops.mesh.primitive_plane_add(size=8.0, location=(0.0, 3.0, 0.0), rotation=(1.5708, 0, 0))
    backdrop = bpy.context.active_object
    backdrop.name = "backdrop"
    backdrop.data.materials.append(noise_material("backdrop_noise", scale=60.0))

    for i, (x, y, z, r) in enumerate([(-0.5, 1.0, 0.1, 0.25), (0.4, 1.6, -0.1, 0.3)]):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=(x, y, z))
        obj = bpy.context.active_object
        obj.name = f"object_{i}"
        obj.data.materials.append(noise_material(f"object_noise_{i}", scale=90.0))

    light_data = bpy.data.lights.new("key", type="AREA")
    light_data.energy = 400.0
    light_data.size = 3.0
    light = bpy.data.objects.new("key", light_data)
    light.location = (2.0, -1.0, 2.5)
    bpy.context.collection.objects.link(light)


def setup_stereo_camera(args):
    cam = bpy.context.scene.camera
    if cam is None:
        cam_data = bpy.data.cameras.new("stereo_cam")
        cam = bpy.data.objects.new("stereo_cam", cam_data)
        bpy.context.collection.objects.link(cam)
        bpy.context.scene.camera = cam
        cam.location = (0.0, -0.0, 0.0)
        cam.rotation_euler = (1.5708, 0.0, 0.0)  # looking down +Y

    cam.data.lens = args.lens_mm
    cam.data.sensor_width = args.sensor_width_mm
    cam.data.sensor_fit = "HORIZONTAL"

    stereo = cam.data.stereo
    stereo.convergence_mode = "OFFAXIS"  # ADR-0007
    stereo.interocular_distance = args.interocular
    stereo.convergence_distance = args.convergence
    return cam


def setup_render(args):
    scene = bpy.context.scene
    scene.render.engine = args.engine
    if args.engine == "CYCLES":
        scene.cycles.samples = args.samples
    scene.render.resolution_x, scene.render.resolution_y = args.resolution
    scene.render.resolution_percentage = 100

    scene.render.use_multiview = True
    scene.render.views_format = "STEREO_3D"

    scene.use_nodes = True
    scene.view_layers[0].use_pass_z = True
    return scene


def setup_compositor(scene, out_dir):
    """Route the combined and depth passes to separate files.

    Depth goes out as 32-bit float OpenEXR: depth in metres has no business being
    quantised to 8 bits, and PNG would silently do exactly that.
    """
    tree = scene.node_tree
    for node in list(tree.nodes):
        tree.nodes.remove(node)

    render_layers = tree.nodes.new("CompositorNodeRLayers")

    image_out = tree.nodes.new("CompositorNodeOutputFile")
    image_out.base_path = out_dir
    image_out.format.file_format = "PNG"
    image_out.format.color_mode = "BW"
    image_out.format.color_depth = "8"
    image_out.file_slots[0].path = "image_"
    tree.links.new(render_layers.outputs["Image"], image_out.inputs[0])

    depth_out = tree.nodes.new("CompositorNodeOutputFile")
    depth_out.base_path = out_dir
    depth_out.format.file_format = "OPEN_EXR"
    depth_out.format.color_depth = "32"
    depth_out.format.color_mode = "BW"
    depth_out.file_slots[0].path = "depth_"
    tree.links.new(render_layers.outputs["Depth"], depth_out.inputs[0])


def write_rig(args, out_dir):
    """Record the camera parameters the loader needs.

    A render whose intrinsics are not written down is not reproducible, however
    carefully the pixels were computed.
    """
    rig = {
        "resolution_x": args.resolution[0],
        "resolution_y": args.resolution[1],
        "lens_mm": args.lens_mm,
        "sensor_width_mm": args.sensor_width_mm,
        "interocular": args.interocular,
        "convergence_distance": args.convergence,
        "convergence_mode": "OFFAXIS",
        "engine": args.engine,
        "blender_version": bpy.app.version_string,
        "depth_pass": "Z",
        "depth_is_radial": None,  # calibrate with infer_depth_convention()
        "note": (
            "Run activestereo.scenes.blender.infer_depth_convention on a "
            "fronto-parallel calibration render for this Blender version and "
            "record the answer here. Do not assume it across versions."
        ),
    }
    with open(os.path.join(out_dir, "rig.json"), "w") as f:
        json.dump(rig, f, indent=2)


def rename_multiview_outputs(out_dir):
    """Normalise Blender's ``name_L0001.png`` outputs to ``left.png`` etc."""
    mapping = {}
    for fname in os.listdir(out_dir):
        stem, ext = os.path.splitext(fname)
        if stem.startswith("image_"):
            eye = "left" if stem.endswith("_L") or "_L" in stem else "right"
            mapping[fname] = f"{eye}{ext}"
        elif stem.startswith("depth_"):
            eye = "left" if stem.endswith("_L") or "_L" in stem else "right"
            mapping[fname] = f"depth_{eye}{ext}"
    for src, dst in mapping.items():
        os.replace(os.path.join(out_dir, src), os.path.join(out_dir, dst))
    return mapping


def main():
    args = parse_args(sys.argv)
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)

    if args.procedural:
        build_procedural_scene()

    setup_stereo_camera(args)
    scene = setup_render(args)
    setup_compositor(scene, out_dir)

    bpy.ops.render.render(write_still=False)

    renamed = rename_multiview_outputs(out_dir)
    write_rig(args, out_dir)

    print(f"[render_stereo] wrote {len(renamed)} files to {out_dir}")
    if not any(v.startswith("depth_") for v in renamed.values()):
        print(
            "[render_stereo] WARNING: no depth pass written. The stimulus has no "
            "ground truth and cannot be used for evaluation.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
