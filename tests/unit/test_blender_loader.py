"""The Blender loader, tested against synthetic multi-layer EXRs.

Nothing inside Blender can be tested from here -- `bpy` exists only in Blender.
But the *reading* half can be, and it is where a silent error would be most
costly: a depth pass misread as beauty produces plausible, smoothly varying,
completely wrong depth (ADR-0010).

These tests write EXRs using Blender's `<Layer>.<Pass>.<Channel>` channel naming
and read them back through the real code path.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from activestereo.scenes import Scene
from activestereo.scenes.blender import (
    albedo_texture_contrast,
    focal_px_from_blender,
    infer_depth_convention,
    radial_to_planar,
    rig_from_blender,
)
from activestereo.types import StereoRig

oiio = pytest.importorskip("OpenImageIO", reason="needs the 'blender' extra")

from activestereo.scenes.blender import (  # noqa: E402
    BlenderRenderScene,
    load_render,
    read_multilayer_exr,
)

H, W = 48, 64


def write_multipart_exr(path, depth, depth_channel="Z", seed=0):
    """Write a *multi-part* EXR: one part per pass, as Blender does.

    This is the layout that broke the reader in practice -- a reader stopping at
    part 0 sees only the beauty pass and reports no depth, silently.
    """
    rng = np.random.default_rng(seed)
    beauty = np.zeros((H, W, 4), dtype=np.float32)
    beauty[..., 0:3] = rng.random((H, W, 1))
    beauty[..., 3] = 1.0

    s0 = oiio.ImageSpec(W, H, 4, "float")
    s0.channelnames = ["R", "G", "B", "A"]
    s0.attribute("name", "ViewLayer.Combined")
    s1 = oiio.ImageSpec(W, H, 1, "float")
    s1.channelnames = [depth_channel]
    s1.attribute("name", "ViewLayer.Depth")

    out = oiio.ImageOutput.create(str(path))
    out.open(str(path), [s0, s1])
    out.write_image(beauty)
    out.open(str(path), s1, "AppendSubimage")
    out.write_image(np.asarray(depth, dtype=np.float32).reshape(H, W, 1))
    out.close()


def write_exr(path, depth, depth_channel="ViewLayer.Depth.Z", seed=0):
    """Write a Blender-style multi-layer EXR: Combined RGB plus a depth pass."""
    names = [
        "ViewLayer.Combined.R",
        "ViewLayer.Combined.G",
        "ViewLayer.Combined.B",
        depth_channel,
    ]
    rng = np.random.default_rng(seed)
    data = np.zeros((H, W, 4), dtype=np.float32)
    data[..., 0:3] = rng.random((H, W, 1))
    data[..., 3] = depth
    spec = oiio.ImageSpec(W, H, 4, "float")
    spec.channelnames = names
    out = oiio.ImageOutput.create(str(path))
    out.open(str(path), spec)
    out.write_image(data)
    out.close()
    return data


@pytest.fixture
def rig():
    return rig_from_blender(W, 36.0, 50.0, 0.064, 6.0)


def test_reads_depth_from_the_named_layer(tmp_path):
    """The essential property. OpenCV would return the beauty pass here and the
    error would be invisible -- see ADR-0010."""
    path = tmp_path / "left.exr"
    write_exr(path, np.full((H, W), 2.5, dtype=np.float32))
    layers = read_multilayer_exr(path)
    assert np.allclose(layers["depth"], 2.5)
    assert not np.allclose(layers["image"], 2.5), "beauty pass read as depth"


def test_accepts_both_depth_channel_spellings(tmp_path):
    """Blender has written the Z pass as both `.Z` and `.V` across versions."""
    for channel in ("ViewLayer.Depth.Z", "ViewLayer.Depth.V"):
        path = tmp_path / f"{channel.replace('.', '_')}.exr"
        write_exr(path, np.full((H, W), 1.75, dtype=np.float32), depth_channel=channel)
        assert np.allclose(read_multilayer_exr(path)["depth"], 1.75)


def test_non_hits_become_nan(tmp_path):
    """Blender writes rays that hit nothing as a very large value, not nan.
    Leaving it would put a 1e10 metre surface into cue fusion."""
    depth = np.full((H, W), 2.0, dtype=np.float32)
    depth[0, :] = 1e10
    path = tmp_path / "left.exr"
    write_exr(path, depth)
    out = read_multilayer_exr(path)["depth"]
    assert np.isnan(out[0]).all()
    assert np.isfinite(out[1:]).all()


def test_missing_depth_pass_raises(tmp_path):
    """Silence here would mean a stimulus with no ground truth scored as if it had."""
    path = tmp_path / "left.exr"
    spec = oiio.ImageSpec(W, H, 3, "float")
    spec.channelnames = ["R", "G", "B"]
    out = oiio.ImageOutput.create(str(path))
    out.open(str(path), spec)
    out.write_image(np.zeros((H, W, 3), dtype=np.float32))
    out.close()
    with pytest.raises(KeyError, match="no depth layer"):
        read_multilayer_exr(path)


def test_load_render_builds_a_stimulus(tmp_path, rig):
    depth = np.full((H, W), 2.0, dtype=np.float32)
    depth[:, 24:40] = 1.2
    write_exr(tmp_path / "left.exr", depth, seed=1)
    write_exr(tmp_path / "right.exr", depth, seed=2)

    stim = load_render(tmp_path, rig)
    assert stim.shape == (H, W)
    np.testing.assert_allclose(np.unique(np.round(stim.depth, 3)), [1.2, 2.0])
    assert np.nanmax(stim.disparity) > np.nanmin(stim.disparity)


def test_load_render_recovers_occlusion_at_the_step(tmp_path, rig):
    """Occlusion is recovered by left-right consistency between the two depth
    passes -- which is why both eyes are rendered."""
    depth = np.full((H, W), 2.0, dtype=np.float32)
    depth[:, 24:40] = 1.2
    write_exr(tmp_path / "left.exr", depth, seed=1)
    write_exr(tmp_path / "right.exr", depth, seed=2)
    stim = load_render(tmp_path, rig)
    assert 0.0 < stim.occlusion_fraction < 0.5


def test_one_eye_is_not_enough(tmp_path, rig):
    """A single depth pass cannot express half-occlusion. Fail loudly."""
    write_exr(tmp_path / "left.exr", np.full((H, W), 2.0, dtype=np.float32))
    with pytest.raises(FileNotFoundError, match="Both eyes are required"):
        load_render(tmp_path, rig)


def test_radial_to_planar_roundtrip():
    f = focal_px_from_blender(W, 36.0, 50.0)
    rows, cols = np.indices((H, W))
    u, v = cols - (W - 1) / 2.0, rows - (H - 1) / 2.0
    radial = 2.0 * np.sqrt(f**2 + u**2 + v**2) / f
    np.testing.assert_allclose(radial_to_planar(radial, f), 2.0, rtol=1e-9)


def test_depth_convention_diagnosis():
    f = focal_px_from_blender(W, 36.0, 50.0)
    rows, cols = np.indices((H, W))
    u, v = cols - (W - 1) / 2.0, rows - (H - 1) / 2.0
    assert infer_depth_convention(np.full((H, W), 2.0)) == "planar"
    assert infer_depth_convention(2.0 * np.sqrt(f**2 + u**2 + v**2) / f) == "radial"


def test_reads_depth_from_a_multipart_file(tmp_path):
    """The layout Blender actually writes. Reading only part 0 shows Combined and
    nothing else, with no error to say a layer was missed."""
    path = tmp_path / "left.exr"
    write_multipart_exr(path, np.full((H, W), 2.5, dtype=np.float32))
    layers = read_multilayer_exr(path)
    assert np.allclose(layers["depth"], 2.5)
    assert not np.allclose(layers["image"], 2.5)


def test_multipart_accepts_both_depth_spellings(tmp_path):
    for channel in ("Z", "V"):
        path = tmp_path / f"depth_{channel}.exr"
        write_multipart_exr(path, np.full((H, W), 1.25, dtype=np.float32), depth_channel=channel)
        assert np.allclose(read_multilayer_exr(path)["depth"], 1.25)


def test_multipart_load_render(tmp_path, rig):
    depth = np.full((H, W), 2.0, dtype=np.float32)
    depth[:, 24:40] = 1.2
    write_multipart_exr(tmp_path / "left.exr", depth, seed=1)
    write_multipart_exr(tmp_path / "right.exr", depth, seed=2)
    stim = load_render(tmp_path, rig)
    np.testing.assert_allclose(np.unique(np.round(stim.depth, 3)), [1.2, 2.0])
    assert 0.0 < stim.occlusion_fraction < 0.5


def write_cycles_exr(path, depth, seed=0):
    """A single-part file with Cycles' auxiliary passes, as rendered in practice.

    Cycles emits "Noisy Image" alongside "Combined", and more passes still when
    denoising data is enabled. All are colour passes with R/G/B channels.
    """
    names = [
        "ViewLayer.Combined.R",
        "ViewLayer.Combined.G",
        "ViewLayer.Combined.B",
        "ViewLayer.Combined.A",
        "ViewLayer.Depth.Z",
        "ViewLayer.Noisy Image.R",
        "ViewLayer.Noisy Image.G",
        "ViewLayer.Noisy Image.B",
        "ViewLayer.Denoising Albedo.R",
        "ViewLayer.Denoising Albedo.G",
        "ViewLayer.Denoising Albedo.B",
    ]
    rng = np.random.default_rng(seed)
    data = np.zeros((H, W, len(names)), dtype=np.float32)
    data[..., 0:3] = rng.random((H, W, 1)) * 0.5
    data[..., 3] = 1.0
    data[..., 4] = depth
    data[..., 5:8] = 0.9  # deliberately unlike Combined
    data[..., 8:11] = 0.1
    spec = oiio.ImageSpec(W, H, len(names), "float")
    spec.channelnames = names
    out = oiio.ImageOutput.create(str(path))
    out.open(str(path), spec)
    out.write_image(data)
    out.close()
    return data


def test_auxiliary_colour_passes_do_not_contaminate_the_image(tmp_path):
    """Averaging "Noisy Image" or "Denoising Albedo" into the beauty pass is
    silent corruption: the result still looks like a plausible photograph, but
    every matcher then works on an image the renderer never produced."""
    path = tmp_path / "left.exr"
    data = write_cycles_exr(path, np.full((H, W), 2.0, dtype=np.float32), seed=3)
    expected = data[..., 0:3].mean(axis=2)
    got = read_multilayer_exr(path)["image"]
    np.testing.assert_allclose(got, expected, rtol=1e-6)
    assert abs(float(got.mean()) - 0.9) > 0.2, "Noisy Image leaked into the beauty pass"


def test_cycles_layout_depth(tmp_path):
    path = tmp_path / "left.exr"
    write_cycles_exr(path, np.full((H, W), 1.75, dtype=np.float32))
    assert np.allclose(read_multilayer_exr(path)["depth"], 1.75)


# --- appearance passes ----------------------------------------------------
#
# Layer names below are the ones Blender 5.2 actually writes, confirmed with
# scripts/inspect_exr.py on a real render: "Diffuse Color", "Glossy Direct" and
# "Material Index", with spaces -- not the DiffCol/GlossDir/IndexMA
# abbreviations used elsewhere in Blender's own codebase.

CHART_PASSES = (
    "ViewLayer.Combined.R",
    "ViewLayer.Combined.G",
    "ViewLayer.Combined.B",
    "ViewLayer.Combined.A",
    "ViewLayer.Depth.Z",
    "ViewLayer.Diffuse Color.R",
    "ViewLayer.Diffuse Color.G",
    "ViewLayer.Diffuse Color.B",
    "ViewLayer.Glossy Direct.R",
    "ViewLayer.Glossy Direct.G",
    "ViewLayer.Glossy Direct.B",
    "ViewLayer.Material Index.X",
)


def write_chart_exr(path, depth, albedo, glossy, material_index, image=0.4):
    """A render with the appearance passes the material chart enables."""
    data = np.zeros((H, W, len(CHART_PASSES)), dtype=np.float32)
    data[..., 0:3] = image
    data[..., 3] = 1.0
    data[..., 4] = depth
    data[..., 5:8] = np.asarray(albedo, dtype=np.float32)[..., None]
    data[..., 8:11] = np.asarray(glossy, dtype=np.float32)[..., None]
    data[..., 11] = material_index
    spec = oiio.ImageSpec(W, H, len(CHART_PASSES), "float")
    spec.channelnames = list(CHART_PASSES)
    out = oiio.ImageOutput.create(str(path))
    out.open(str(path), spec)
    out.write_image(data)
    out.close()


def test_reads_the_appearance_passes(tmp_path):
    albedo = np.tile(np.linspace(0.0, 1.0, W, dtype=np.float32), (H, 1))
    write_chart_exr(
        tmp_path / "left.exr",
        np.full((H, W), 2.0, dtype=np.float32),
        albedo,
        np.full((H, W), 0.25, dtype=np.float32),
        np.full((H, W), 7, dtype=np.float32),
    )
    layers = read_multilayer_exr(tmp_path / "left.exr")
    np.testing.assert_allclose(layers["albedo"], albedo, rtol=1e-6)
    np.testing.assert_allclose(layers["glossy"], 0.25, rtol=1e-6)
    np.testing.assert_allclose(layers["material_index"], 7)


def test_albedo_is_not_mistaken_for_the_beauty_pass(tmp_path):
    """Diffuse Color and Combined are both RGB colour passes with identical
    channel letters. Substituting one for the other is silent: a shading-free
    albedo map still looks like a photograph, and every matcher downstream then
    runs on an image the renderer never produced. Same shape of error as
    ADR-0010's beauty/depth confusion."""
    write_chart_exr(
        tmp_path / "left.exr",
        np.full((H, W), 2.0, dtype=np.float32),
        np.full((H, W), 0.9, dtype=np.float32),
        np.zeros((H, W), dtype=np.float32),
        np.ones((H, W), dtype=np.float32),
        image=0.2,
    )
    layers = read_multilayer_exr(tmp_path / "left.exr")
    assert np.allclose(layers["image"], 0.2), "albedo leaked into the beauty pass"
    assert np.allclose(layers["albedo"], 0.9), "beauty pass leaked into albedo"


def test_appearance_passes_are_optional(tmp_path):
    """A render without them must still load -- only the chart enables them."""
    write_exr(tmp_path / "left.exr", np.full((H, W), 2.0, dtype=np.float32))
    layers = read_multilayer_exr(tmp_path / "left.exr")
    assert "depth" in layers and "image" in layers
    assert "albedo" not in layers


# --- texture contrast -----------------------------------------------------


def test_texture_contrast_is_zero_on_constant_albedo():
    """The textureless end of the ladder must read exactly 0, not nan. `nan`
    would mean 'no support' -- a different fact, and one that would silently
    drop the most interesting condition out of every statistic."""
    out = albedo_texture_contrast(np.full((H, W), 0.5), window=7)
    interior = out[4:-4, 4:-4]
    assert np.all(np.isfinite(interior))
    np.testing.assert_allclose(interior, 0.0, atol=1e-9)


def test_texture_contrast_orders_by_spatial_frequency():
    """Fine texture must read higher than coarse *at the matcher's window*. This
    is the property the whole experiment bins on, and it is not automatic: noise
    finer than the pixel grid is antialiased away by the renderer and reads
    lower than a coarser pattern, which is exactly what happened on the first
    material chart."""
    cols = np.arange(W)
    fine = np.tile(0.5 + 0.4 * np.sin(cols * np.pi / 2.0), (H, 1))
    coarse = np.tile(0.5 + 0.4 * np.sin(cols * np.pi / 24.0), (H, 1))
    f = np.nanmedian(albedo_texture_contrast(fine, window=7)[4:-4, 4:-4])
    c = np.nanmedian(albedo_texture_contrast(coarse, window=7)[4:-4, 4:-4])
    assert f > c, f"fine texture {f:.4f} did not exceed coarse {c:.4f}"


def test_texture_contrast_masks_invalid_before_mixing():
    """ADR-0002. A window with no valid support must stay nan rather than
    averaging nan in as though it were data."""
    albedo = np.full((H, W), 0.5)
    albedo[:, 10:40] = np.nan
    out = albedo_texture_contrast(albedo, window=7)
    assert np.all(np.isnan(out[:, 20:30])), "manufactured a value with no valid support"
    assert np.all(np.isfinite(out[4:-4, 45:-4])), "valid region was contaminated"


def test_texture_contrast_rejects_even_window():
    with pytest.raises(ValueError, match="odd"):
        albedo_texture_contrast(np.zeros((H, W)), window=8)


# --- depth convention guard -----------------------------------------------


def test_depth_convention_refuses_a_scene_that_is_not_a_flat_wall():
    """Regression: this used to answer "radial" with total confidence on any
    ordinary scene, because nearer objects toward the middle of frame make depth
    "grow toward the corners" for reasons that have nothing to do with the
    convention. Acting on it applies a spurious few-percent peripheral
    correction -- indistinguishable from an ADR-0003 modelling result, in the
    one component the invariants cannot reach."""
    depth = np.full((H, W), 1.6)
    depth[8:24, 8:24] = 1.05  # a nearer patch, off-centre: not radially symmetric
    assert infer_depth_convention(depth) == "unknown"


def test_depth_convention_still_diagnoses_genuine_calibration_renders():
    """The guard must not cost us the answer on the input the function is for."""
    f = focal_px_from_blender(W, 36.0, 50.0)
    rows, cols = np.indices((H, W))
    u, v = cols - (W - 1) / 2.0, rows - (H - 1) / 2.0
    assert infer_depth_convention(np.full((H, W), 2.0)) == "planar"
    assert infer_depth_convention(2.0 * np.sqrt(f**2 + u**2 + v**2) / f) == "radial"


# --- BlenderRenderScene ---------------------------------------------------


def _chart_render(directory, depth_is_radial=None, material_index=None):
    """Write a two-eye chart render with rig.json and chart.json."""
    directory.mkdir(parents=True, exist_ok=True)
    depth = np.full((H, W), 2.0, dtype=np.float32)
    depth[:, 24:40] = 1.2
    if material_index is None:
        # 20 is the backdrop, and must label *only* the flat part: the depth
        # convention is measured against it, so labelling the near slab as
        # backdrop too would make the "flat wall" not flat.
        material_index = np.full((H, W), 20.0)
        material_index[:, 24:40] = 1.0
    index = material_index
    rng = np.random.default_rng(0)
    albedo = rng.random((H, W)).astype(np.float32)
    for eye, glossy in (("left", 0.1), ("right", 0.1)):
        write_chart_exr(
            directory / f"{eye}.exr",
            depth,
            albedo,
            np.full((H, W), glossy, dtype=np.float32),
            index,
        )
    (directory / "rig.json").write_text(
        json.dumps(
            {
                "resolution_x": W,
                "sensor_width_mm": 36.0,
                "lens_mm": 50.0,
                "interocular": 0.064,
                "convergence_distance": 6.0,
                "depth_is_radial": depth_is_radial,
            }
        )
    )
    (directory / "chart.json").write_text(
        json.dumps(
            {
                "index_backdrop": 20,
                "materials": [
                    {"material_index": 1, "label": "dense_matte", "roughness": 1.0},
                    {"material_index": 2, "label": "none_glossy", "roughness": 0.15},
                ],
            }
        )
    )
    return directory


def test_render_scene_satisfies_the_scene_protocol(tmp_path):
    assert isinstance(BlenderRenderScene(_chart_render(tmp_path / "r")), Scene)


def test_render_scene_builds_a_stimulus(tmp_path):
    scene = BlenderRenderScene(_chart_render(tmp_path / "r", depth_is_radial=False))
    stim = scene.render(scene.rig, np.random.default_rng(0))
    assert stim.shape == (H, W)
    np.testing.assert_allclose(np.unique(np.round(stim.depth, 3)), [1.2, 2.0])
    assert 0.0 < stim.occlusion_fraction < 0.5


def test_render_scene_refuses_a_mismatched_rig(tmp_path):
    """Scaling a rendered disparity field with the wrong rig yields metric depth
    that is wrong by a constant factor and entirely plausible-looking. The Scene
    protocol hands in a rig; this render's geometry was fixed when it was
    written, so disagreement is an error rather than a request."""
    scene = BlenderRenderScene(_chart_render(tmp_path / "r", depth_is_radial=False))
    wrong = StereoRig(baseline=0.064, focal_px=800.0, vergence=scene.rig.vergence)
    with pytest.raises(ValueError, match="rig mismatch on focal_px"):
        scene.render(wrong, np.random.default_rng(0))


def test_render_scene_ignores_the_rng(tmp_path):
    """A pre-baked render is the same pixels whatever the seed. The Scene
    protocol's determinism clause is satisfied more strongly than it asks."""
    scene = BlenderRenderScene(_chart_render(tmp_path / "r", depth_is_radial=False))
    a = scene.render(scene.rig, np.random.default_rng(0))
    b = scene.render(scene.rig, np.random.default_rng(999))
    np.testing.assert_array_equal(a.left, b.left)
    np.testing.assert_array_equal(a.depth, b.depth)


def test_depth_convention_is_measured_from_the_chart_backdrop(tmp_path):
    """rig.json writes depth_is_radial as null because the render script cannot
    tell. The old caller did bool(None) -> False, turning "nobody checked" into
    "planar, definitely" without a word. A chart render carries a known
    fronto-parallel backdrop, so the answer can be measured instead of assumed."""
    scene = BlenderRenderScene(_chart_render(tmp_path / "r", depth_is_radial=None))
    assert scene.depth_is_radial() is False


def test_depth_convention_raises_when_it_cannot_be_established(tmp_path):
    """Better to stop than to assume. An uncorrected radial pass looks exactly
    like a few percent of peripheral modelling error."""
    directory = tmp_path / "plain"
    directory.mkdir()
    depth = np.full((H, W), 2.0, dtype=np.float32)
    depth[:, 24:40] = 1.2
    write_exr(directory / "left.exr", depth, seed=1)
    write_exr(directory / "right.exr", depth, seed=2)
    (directory / "rig.json").write_text(
        json.dumps(
            {
                "resolution_x": W,
                "sensor_width_mm": 36.0,
                "lens_mm": 50.0,
                "interocular": 0.064,
                "convergence_distance": 6.0,
                "depth_is_radial": None,
            }
        )
    )
    with pytest.raises(ValueError, match="depth convention"):
        BlenderRenderScene(directory).stimulus()


def test_appearance_requires_the_passes(tmp_path):
    directory = tmp_path / "plain"
    directory.mkdir()
    write_exr(directory / "left.exr", np.full((H, W), 2.0, dtype=np.float32), seed=1)
    write_exr(directory / "right.exr", np.full((H, W), 2.0, dtype=np.float32), seed=2)
    (directory / "rig.json").write_text(
        json.dumps(
            {
                "resolution_x": W,
                "sensor_width_mm": 36.0,
                "lens_mm": 50.0,
                "interocular": 0.064,
                "convergence_distance": 6.0,
                "depth_is_radial": False,
            }
        )
    )
    with pytest.raises(KeyError, match="material_index"):
        BlenderRenderScene(directory).appearance()


def test_specular_mismatch_is_zero_for_a_diffuse_surface(tmp_path):
    """A diffuse surface radiates equally toward both eyes, so its glossy energy
    survives the warp. This is the baseline the gloss axis is measured against."""
    scene = BlenderRenderScene(_chart_render(tmp_path / "r", depth_is_radial=False))
    stim = scene.stimulus()
    mismatch = scene.appearance().specular_mismatch(stim.disparity)
    assert np.nanmedian(mismatch) < 1e-3


def test_specular_mismatch_detects_a_highlight_in_one_eye_only(tmp_path):
    """The brightness-constancy violation itself: a highlight generated at a
    different scene point per eye does not survive warping. BlockMatcher's SSD
    cost assumes constancy unconditionally and cannot notice."""
    directory = _chart_render(tmp_path / "r", depth_is_radial=False)
    depth = np.full((H, W), 2.0, dtype=np.float32)
    depth[:, 24:40] = 1.2
    albedo = np.full((H, W), 0.5, dtype=np.float32)
    left_glossy = np.zeros((H, W), dtype=np.float32)
    left_glossy[:, 8:16] = 5.0  # a highlight the right eye does not see
    write_chart_exr(directory / "left.exr", depth, albedo, left_glossy, np.full((H, W), 20.0))
    write_chart_exr(
        directory / "right.exr",
        depth,
        albedo,
        np.zeros((H, W), dtype=np.float32),
        np.full((H, W), 20.0),
    )
    scene = BlenderRenderScene(directory, depth_is_radial=False)
    mismatch = scene.appearance().specular_mismatch(scene.stimulus().disparity)
    assert np.nanmedian(mismatch[:, 8:16]) > 0.9
    assert np.nanmedian(mismatch[:, 40:]) < 0.1


def test_missing_rig_json_raises(tmp_path):
    directory = tmp_path / "bare"
    directory.mkdir()
    with pytest.raises(FileNotFoundError, match=r"rig\.json"):
        BlenderRenderScene(directory)
