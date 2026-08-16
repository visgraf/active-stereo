"""Render a stereo pair with depth ground truth from Blender.

Tested against Blender 5.2 LTS; supports the 4.x API as well.

Blender 5.0 removed ``Scene.node_tree`` (the compositing tree became its own
datablock behind ``Scene.compositing_node_group``), deprecated ``use_nodes``, and
removed the Composite node in favour of a Group Output. This script branches on
the API rather than assuming either shape. If a future version moves something
else, run with ``--inspect`` to dump the API surface it depends on.

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
from pathlib import Path

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
    # No `choices`: engine identifiers move between versions (BLENDER_EEVEE ->
    # BLENDER_EEVEE_NEXT in 4.2 -> back again). Validated against the build instead.
    p.add_argument("--engine", default="CYCLES", help="CYCLES, BLENDER_EEVEE, ...")
    p.add_argument("--procedural", action="store_true", help="build a test scene")
    p.add_argument(
        "--mode",
        default="multilayer",
        choices=["multilayer", "compositor"],
        help="multilayer: one EXR per eye via the render output path (default). "
        "compositor: separate PNG/EXR files via File Output nodes (fragile).",
    )
    p.add_argument(
        "--inspect",
        action="store_true",
        help="print the bpy API surface this script depends on, then exit",
    )
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

    Materials are **emissive**, not lit. This is a matching *test target*, not a
    photometric scene: what it must guarantee is high-frequency, non-repeating,
    well-exposed texture at a known depth. Emission gives exactly that with no
    dependence on lighting, engine, or exposure -- a lit scene was coming out too
    dark to match, which is a property of the lighting rig rather than of the
    stereo algorithm under test.

    Use a real .blend when photometric realism is the point (ADR-0006); use this
    when you want to know whether the pipeline works.

    Texture is deliberately non-repeating: a repeating pattern creates matching
    ambiguity that is indistinguishable from matcher failure.
    """
    bpy.ops.wm.read_factory_settings(use_empty=True)

    # use_empty leaves no world at all, so the background renders black and
    # nothing is lit. Give it a mid-grey world for the non-emissive case.
    world = bpy.data.worlds.new("world")
    if getattr(world, "node_tree", None) is None:
        world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.05, 0.05, 0.05, 1.0)
    bpy.context.scene.world = world

    def noise_material(name, scale=40.0):
        mat = bpy.data.materials.new(name)
        if getattr(mat, "node_tree", None) is None:
            mat.use_nodes = True
        nt = mat.node_tree
        for node in list(nt.nodes):
            nt.nodes.remove(node)

        out = nt.nodes.new("ShaderNodeOutputMaterial")
        emission = nt.nodes.new("ShaderNodeEmission")
        emission.inputs["Strength"].default_value = 1.0

        tex = nt.nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = scale
        tex.inputs["Detail"].default_value = 8.0

        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.interpolation = "CONSTANT"
        # Move the WHITE stop to 0.5, not the black one. Setting elements[0]
        # (black) to 0.5 leaves black covering [0, 1] under CONSTANT
        # interpolation, and the whole scene renders black -- which is exactly
        # what happened.
        ramp.color_ramp.elements[1].position = 0.5

        nt.links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], emission.inputs["Color"])
        nt.links.new(emission.outputs["Emission"], out.inputs["Surface"])
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


CYCLES_MODULES = ("cycles", "bl_ext.system.cycles", "bl_ext.blender_org.cycles")


def ensure_cycles():
    """Enable the Cycles add-on if this build ships it.

    The module name moved when extensions arrived in 4.2, so several are tried.
    Returns True if Cycles is available afterwards.

    This matters more than it looks: EEVEE historically cannot render in
    ``--background`` mode on some platforms because it needs a GPU context, and
    it fails by producing nothing rather than by raising.
    """
    addons = bpy.context.preferences.addons
    if any(m in addons for m in CYCLES_MODULES):
        return True
    for module in CYCLES_MODULES:
        try:
            bpy.ops.preferences.addon_enable(module=module)
            if module in addons:
                print(f"[render_stereo] enabled Cycles add-on ({module})")
                return True
        except Exception:
            continue
    print(
        "[render_stereo] Cycles add-on not found. If this is an official "
        "Blender build, check Preferences > Add-ons for 'Cycles Render Engine'; "
        "some repackaged builds omit it.",
        file=sys.stderr,
    )
    return False


def available_engines():
    """Engine identifiers, for diagnostics only.

    NOT a reliable availability test. `RenderSettings.bl_rna` exposes the
    *static* enum; render engines registered by add-ons -- Cycles among them --
    only appear in the context-resolved enum. Introspecting this and concluding
    "Cycles is not available in this build" was simply wrong.
    """
    try:
        prop = bpy.types.RenderSettings.bl_rna.properties["engine"]
        return [item.identifier for item in prop.enum_items]
    except Exception:
        return []


def try_set_engine(scene, engine):
    """Attempt to select an engine. Assignment succeeds iff it is registered."""
    try:
        scene.render.engine = engine
        return True
    except TypeError:
        return False


def setup_render(args):
    scene = bpy.context.scene

    if args.engine == "CYCLES":
        ensure_cycles()
    if not try_set_engine(scene, args.engine):
        candidates = ("CYCLES", "BLENDER_EEVEE_NEXT", "BLENDER_EEVEE")
        fallback = next((e for e in candidates if try_set_engine(scene, e)), None)
        if fallback is None:
            raise RuntimeError(
                f"could not select any render engine. Static enum reports {available_engines()}"
            )
        print(
            f"[render_stereo] engine {args.engine!r} could not be selected; using {fallback!r}",
            file=sys.stderr,
        )
    engine = scene.render.engine
    print(f"[render_stereo] engine: {engine}")

    if engine == "CYCLES" and hasattr(scene, "cycles"):
        scene.cycles.samples = args.samples
    elif hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = args.samples

    scene.render.resolution_x, scene.render.resolution_y = args.resolution
    scene.render.resolution_percentage = 100

    # Compositing must be enabled or the File Output nodes never execute.
    scene.render.use_compositing = True
    scene.render.use_multiview = True
    scene.render.views_format = "STEREO_3D"
    # One file per eye, not a single packed stereo image. Without this there is
    # no right-eye depth pass and occlusion ground truth cannot be recovered.
    if hasattr(scene.render.image_settings, "views_format"):
        scene.render.image_settings.views_format = "INDIVIDUAL"

    # The Z pass must be enabled before the compositor tree is built, or the
    # Render Layers node exposes no Depth socket.
    for view_layer in scene.view_layers:
        view_layer.use_pass_z = True

    return scene


def compositor_tree(scene):
    """Return the scene's compositing node tree, across the 4.x/5.x API split.

    Blender 5.0 removed ``Scene.node_tree``: the compositing tree became its own
    datablock, assigned via ``Scene.compositing_node_group``. ``Scene.use_nodes``
    is deprecated in 5.x (always True, setting it does nothing) and slated for
    removal in 6.0, so it is only touched on the legacy path.
    """
    if hasattr(scene, "compositing_node_group"):  # Blender 5.0+
        tree = bpy.data.node_groups.new("active_stereo_comp", "CompositorNodeTree")
        scene.compositing_node_group = tree
        return tree, 5
    scene.use_nodes = True  # Blender <= 4.x
    return scene.node_tree, 4


def set_individual_files(node):
    """Switch a File Output node to writing one ordinary image per input.

    In Blender 5.x the mode lives on ``node.format.media_type`` and defaults to
    ``MULTI_LAYER_IMAGE``, which restricts ``file_format`` to exactly
    ``OPEN_EXR_MULTILAYER``. Every other format assignment fails until it is set
    to ``IMAGE``.

    Separate files are what we want regardless: OpenCV cannot read named layers
    out of a multi-layer EXR, so a multi-layer output would force OpenImageIO
    into the dependency list (ADR-0009).

    Falls back to scanning the RNA of both the node and its format for any enum
    offering a non-MULTI option, in case this moves again. Returns
    ``(property, value)`` or ``(None, None)``.
    """
    fmt = getattr(node, "format", None)
    if fmt is not None and hasattr(fmt, "media_type"):
        fmt.media_type = "IMAGE"
        return "format.media_type", "IMAGE"

    for owner, prefix in ((node, ""), (fmt, "format.")):
        if owner is None:
            continue
        for prop in owner.bl_rna.properties:
            if prop.type != "ENUM" or prop.is_readonly:
                continue
            ids = [item.identifier for item in prop.enum_items]
            if len(ids) < 2 or not any("MULTI" in i for i in ids):
                continue
            target = next((i for i in ids if "MULTI" not in i), None)
            if target is None:
                continue
            try:
                setattr(owner, prop.identifier, target)
                return f"{prefix}{prop.identifier}", target
            except (TypeError, AttributeError):
                continue
    return None, None


def describe_node(node):
    """Full settable-property dump, for error messages that end the guessing."""
    lines = []
    for prop in sorted(node.bl_rna.properties, key=lambda pr: pr.identifier):
        if prop.identifier in ("rna_type", "bl_icon"):
            continue  # bl_icon is ~900 enum identifiers of pure noise
        detail = prop.type
        if prop.type == "ENUM":
            detail += f" {[i.identifier for i in prop.enum_items]}"
        lines.append(f"    {prop.identifier}: {detail}")
    return "\n".join(lines)


def setup_multilayer_output(scene, out_dir):
    """Write every enabled pass into one multi-layer EXR per eye. No compositor.

    This is the direct render path -- the same one that produced the working
    control render -- with the output format switched to multi-layer EXR. With
    `use_pass_z`, Blender writes Combined and Depth as named layers in a single
    file per view.

    The compositor path is retained behind `--mode compositor` but is not the
    default: its API broke three times within Blender 5.x and then began writing
    nothing at all without raising. `scene.render.filepath` has been stable for a
    decade. See ADR-0010.
    """
    settings = scene.render.image_settings
    if hasattr(settings, "media_type"):
        settings.media_type = "MULTI_LAYER_IMAGE"
    settings.file_format = "OPEN_EXR_MULTILAYER"
    settings.color_depth = "32"
    settings.exr_codec = "ZIP"
    # Prefer a single interleaved part where the build supports it; the reader
    # handles both, but single-part files are easier to inspect by hand.
    if hasattr(settings, "use_exr_interleave"):
        settings.use_exr_interleave = True
    if hasattr(settings, "views_format"):
        settings.views_format = "INDIVIDUAL"

    # No color_management override: multi-layer EXR is written linear, and data
    # passes are never view-transformed. Overriding here made the beauty pass
    # come out dark for no benefit.

    scene.render.use_compositing = False
    scene.render.filepath = os.path.join(out_dir, "frame")
    return scene


def setup_compositor(scene, out_dir, args):
    """Route the combined and depth passes to separate files.

    Depth goes out as 32-bit float OpenEXR: depth in metres has no business being
    quantised to 8 bits, and PNG would silently do exactly that.

    ``views_format = "INDIVIDUAL"`` on each output is what makes Blender write one
    file per eye rather than a single packed stereo image. Without it there is no
    right-eye depth pass, and half-occlusion ground truth is unrecoverable.
    """
    tree, api = compositor_tree(scene)
    for node in list(tree.nodes):
        tree.nodes.remove(node)

    render_layers = tree.nodes.new("CompositorNodeRLayers")

    def add_output(stem, file_format, color_depth, color_mode, socket, as_render):
        """Add a File Output node, across the 4.x/5.x property split.

        Blender 5.0 removed ``base_path``/``file_slots`` in favour of
        ``directory``/``file_name``/``file_output_items``.
        """
        node = tree.nodes.new("CompositorNodeOutputFile")

        if hasattr(node, "directory"):  # Blender 5.0+
            node.directory = out_dir
            node.file_name = stem
            if len(node.file_output_items):
                node.file_output_items[0].name = stem
        else:  # Blender <= 4.x
            node.base_path = out_dir
            node.file_slots[0].path = f"{stem}_"

        # Must precede any format assignment: in multi-layer mode the format
        # enum has exactly one legal value and every other assignment fails.
        if hasattr(node, "directory"):
            prop, _ = set_individual_files(node)
            if prop is None:
                print(
                    f"[render_stereo] WARNING: could not switch the {stem!r} File "
                    "Output node out of multi-layer mode; the format assignment "
                    "below will probably fail.",
                    file=sys.stderr,
                )

        try:
            node.format.file_format = file_format
            node.format.color_depth = color_depth
            node.format.color_mode = color_mode
        except TypeError as exc:
            raise RuntimeError(
                f"Could not set file_format={file_format!r} on the File Output "
                f"node: {exc}\n\nThe node is probably still in multi-layer mode "
                "and set_individual_files() did not find the enum that switches "
                "it. Node properties in this build:\n"
                f"{describe_node(node)}\n\nformat properties:\n"
                f"{describe_node(node.format)}"
            ) from exc
        if hasattr(node.format, "views_format"):
            node.format.views_format = "INDIVIDUAL"

        # Colour management must not touch the depth pass. With save_as_render
        # on, Blender applies the scene view transform (AgX/Filmic) on write,
        # which would silently turn metres into tone-mapped nonsense. The beauty
        # pass does want it; the Z pass emphatically does not.
        if hasattr(node, "save_as_render"):
            node.save_as_render = as_render
        if not as_render and hasattr(node.format, "color_management"):
            node.format.color_management = "OVERRIDE"

        tree.links.new(render_layers.outputs[socket], node.inputs[0])
        return node

    add_output("image", "PNG", "8", "BW", "Image", as_render=True)

    if "Depth" not in render_layers.outputs:
        raise RuntimeError(
            "Render Layers node exposes no Depth socket. Enable the Z pass "
            "(view_layer.use_pass_z) before building the compositor tree. "
            f"Available sockets: {[o.name for o in render_layers.outputs]}"
        )
    add_output("depth", "OPEN_EXR", "32", "BW", "Depth", as_render=False)

    if api >= 5:
        # 5.0 removed the Composite node; a Group Output is what terminates the
        # tree now. Not strictly needed for File Output nodes, but a tree with no
        # output socket is easy to mistake for a broken one when inspecting it.
        group_out = tree.nodes.new("NodeGroupOutput")
        tree.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        tree.links.new(group_out.inputs["Image"], render_layers.outputs["Image"])

    return tree


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
        "blender_binary": bpy.app.binary_path,
        "blender_build_hash": bpy.app.build_hash.decode()
        if isinstance(bpy.app.build_hash, bytes)
        else str(bpy.app.build_hash),
        "depth_pass": "Z",
        "mode": args.mode,
        "depth_is_radial": None,  # calibrate with infer_depth_convention()
        "note": (
            "Run activestereo.scenes.blender.infer_depth_convention on a "
            "fronto-parallel calibration render for this Blender version and "
            "record the answer here. Do not assume it across versions."
        ),
    }
    with open(os.path.join(out_dir, "rig.json"), "w") as f:
        json.dump(rig, f, indent=2)


def view_suffixes(scene):
    """Per-eye filename suffixes, read from the build rather than assumed.

    Blender appends `scene.render.views[*].file_suffix` (conventionally `_L` and
    `_R`) to multiview outputs. Reading them beats hardcoding, because a .blend
    can override them and the defaults have changed across versions.
    """
    try:
        return {v.name: v.file_suffix for v in scene.render.views if v.use and v.file_suffix}
    except Exception:
        return {"left": "_L", "right": "_R"}


def rename_multiview_outputs(scene, out_dir):
    """Normalise Blender's `image_0001_L.png` outputs to `left.png` etc.

    Matches on the suffix appearing anywhere in the stem, so it is indifferent to
    whether Blender puts the frame number before or after the view suffix.
    """
    suffixes = view_suffixes(scene)
    if getattr(scene.render.image_settings, "file_format", "") == "OPEN_EXR_MULTILAYER":
        mapping = {}
        for fname in sorted(os.listdir(out_dir)):
            stem, ext = os.path.splitext(fname)
            if not stem.startswith("frame"):
                continue
            for suffix, view in ((s2, v) for v, s2 in suffixes.items() if s2):
                if suffix in stem:
                    eye = "left" if view.lower().startswith("l") else "right"
                    mapping[fname] = f"{eye}{ext}"
        for src, dst in mapping.items():
            os.replace(os.path.join(out_dir, src), os.path.join(out_dir, dst))
        return mapping

    eye_of = {}
    for view, suffix in suffixes.items():
        eye_of[suffix] = "left" if view.lower().startswith("l") else "right"

    mapping = {}
    for fname in sorted(os.listdir(out_dir)):
        stem, ext = os.path.splitext(fname)
        if stem.startswith("control_"):
            continue  # the control render, not compositor output
        if not stem.startswith(("image", "depth")):
            continue
        kind = "" if stem.startswith("image") else "depth_"
        eye = next((e for suf, e in eye_of.items() if suf in stem), None)
        if eye is None:
            continue
        mapping[fname] = f"{kind}{eye}{ext}"

    for src, dst in mapping.items():
        os.replace(os.path.join(out_dir, src), os.path.join(out_dir, dst))
    return mapping


def inspect_api():
    """Print the API surface this script depends on, then exit.

    Faster than another render-crash-edit cycle when Blender moves something:
    run with --inspect and paste the output.
    """
    scene = bpy.context.scene
    print(f"blender          : {bpy.app.version_string}")
    print(f"engines          : {available_engines()}")
    print(f"scene.node_tree  : {hasattr(scene, 'node_tree')}")
    print(f"compositing_node_group: {hasattr(scene, 'compositing_node_group')}")
    print(f"image_settings.views_format: {hasattr(scene.render.image_settings, 'views_format')}")
    print(f"render.views     : {[(v.name, v.file_suffix) for v in scene.render.views]}")
    cam = scene.camera
    if cam is not None:
        modes = bpy.types.CameraStereoData.bl_rna.properties["convergence_mode"]
        print(f"convergence modes: {[i.identifier for i in modes.enum_items]}")
    print(f"cycles addon     : {'cycles' in bpy.context.preferences.addons}")
    try:
        tree = bpy.data.node_groups.new("_probe", "CompositorNodeTree")
        node = tree.nodes.new("CompositorNodeRLayers")
        print(f"RLayers sockets  : {[o.name for o in node.outputs]}")

        out = tree.nodes.new("CompositorNodeOutputFile")
        props = sorted(
            pr.identifier
            for pr in out.bl_rna.properties
            if not pr.is_readonly or pr.type == "COLLECTION"
        )
        print(f"OutputFile props : {props}")
        for name in ("base_path", "directory", "file_name", "file_slots", "file_output_items"):
            print(f"  has {name:18s}: {hasattr(out, name)}")
        enums = {
            pr.identifier: [i.identifier for i in pr.enum_items]
            for pr in out.bl_rna.properties
            if pr.type == "ENUM" and not pr.is_readonly
        }
        print(f"OutputFile enums : {enums}")
        prop, value = set_individual_files(out)
        print(f"individual-files switch: {prop} -> {value}")
        fmt_prop = out.format.bl_rna.properties["file_format"]
        print(f"file_format now  : {[i.identifier for i in fmt_prop.enum_items]}")

        bpy.data.node_groups.remove(tree)
    except Exception as exc:  # diagnostic path: report anything that goes wrong
        print(f"compositor probe failed: {type(exc).__name__}: {exc}")


def main():
    args = parse_args(sys.argv)
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)

    if args.procedural:
        build_procedural_scene()

    setup_stereo_camera(args)
    scene = setup_render(args)

    if args.inspect:
        inspect_api()
        return

    if args.mode == "multilayer":
        setup_multilayer_output(scene, out_dir)
    else:
        setup_compositor(scene, out_dir, args)

    if args.mode == "compositor":
        # Control render through the normal output path, independent of the
        # compositor: if these appear and the compositor files do not, the node
        # tree is the problem rather than the render.
        scene.render.filepath = os.path.join(out_dir, "control_")
    bpy.ops.render.render(write_still=True)

    print(f"[render_stereo] use_compositing: {scene.render.use_compositing}")
    group = getattr(scene, "compositing_node_group", None)
    if group is not None:
        print(
            f"[render_stereo] compositor tree: {group.name!r}, "
            f"{len(group.nodes)} nodes, {len(group.links)} links"
        )

    layer = scene.view_layers[0]
    print(f"[render_stereo] use_pass_z: {layer.use_pass_z}  (view layer {layer.name!r})")

    produced = sorted(os.listdir(out_dir))
    print(f"[render_stereo] engine used: {scene.render.engine}")
    print(f"[render_stereo] files in {out_dir}:")
    for name in produced:
        size = os.path.getsize(os.path.join(out_dir, name))
        print(f"    {name}  ({size} bytes)")
    if not produced:
        print(
            "[render_stereo] Nothing was written at all. The render produced no "
            "output. If the engine above is EEVEE, retry with --engine CYCLES: "
            "EEVEE needs a GPU context and can silently produce nothing under "
            "--background.",
            file=sys.stderr,
        )

    renamed = rename_multiview_outputs(scene, out_dir)
    write_rig(args, out_dir)
    out_dir_path = Path(out_dir)

    print(f"[render_stereo] wrote {len(renamed)} files to {out_dir}")

    if args.mode == "multilayer":
        expected = [out_dir_path / "left.exr", out_dir_path / "right.exr"]
        missing = [p.name for p in expected if not p.exists()]
        if missing:
            print(
                f"[render_stereo] WARNING: missing {missing}. Both eyes are "
                "required: a single depth pass cannot express half-occlusion.",
                file=sys.stderr,
            )
        else:
            print(
                "[render_stereo] OK. Depth is a named layer inside each EXR; "
                "verify it with:\n"
                f"    python scripts/inspect_exr.py {expected[0]}"
            )
    else:
        if not any(v.startswith("depth_") for v in renamed.values()):
            print(
                "[render_stereo] WARNING: no depth pass written. The stimulus "
                "has no ground truth and cannot be used for evaluation.",
                file=sys.stderr,
            )

    leftover = [
        f
        for f in sorted(os.listdir(out_dir))
        if f.startswith(("image", "depth", "frame"))
        and not f.startswith("control_")
        and f not in renamed
    ]
    if leftover:
        print(
            f"[render_stereo] WARNING: could not classify {leftover}. The view "
            "suffixes did not match; run with --inspect and check render.views.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
