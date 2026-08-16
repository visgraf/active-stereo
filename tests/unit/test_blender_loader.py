"""The Blender loader, tested against synthetic multi-layer EXRs.

Nothing inside Blender can be tested from here -- `bpy` exists only in Blender.
But the *reading* half can be, and it is where a silent error would be most
costly: a depth pass misread as beauty produces plausible, smoothly varying,
completely wrong depth (ADR-0010).

These tests write EXRs using Blender's `<Layer>.<Pass>.<Channel>` channel naming
and read them back through the real code path.
"""

from __future__ import annotations

import numpy as np
import pytest

from activestereo.scenes.blender import (
    focal_px_from_blender,
    infer_depth_convention,
    radial_to_planar,
    rig_from_blender,
)

oiio = pytest.importorskip("OpenImageIO", reason="needs the 'blender' extra")

from activestereo.scenes.blender import load_render, read_multilayer_exr  # noqa: E402

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
