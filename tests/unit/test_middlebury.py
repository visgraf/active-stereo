"""The Middlebury 2014 loader, tested against synthetic scene directories.

The corpus is ~1 GB and lives outside the repository, so none of it can be a test
fixture. Everything here writes a scene directory by hand -- PFM, PNG, calib.txt
-- and reads it back through the real code path.

The conventions being pinned are the ones that fail *silently*: PFM's bottom-up
row order gives a vertically mirrored ground truth with normal-looking
statistics, and a mis-parsed `doffs` biases every depth by a constant factor that
looks entirely plausible. Each was established by measurement at the Stage 0
checkpoint (ADR-0012), and each is fixed here as a measured fact rather than a
belief about the format.
"""

from __future__ import annotations

import struct

import numpy as np
import pytest

from activestereo.scenes import Scene
from activestereo.scenes.base import cross_check_disparity
from activestereo.scenes.middlebury import (
    MiddleburyScene,
    depth_from_disparity,
    pfm_header,
    read_calib,
    read_pfm,
    rig_from_calib,
)

cv2 = pytest.importorskip("cv2", reason="needs the 'cv' extra")

H, W = 32, 48

# Adirondack-perfect, verbatim. Real numbers, so a plausible-but-wrong parse of
# the matrix form has something to fail against.
CALIB = """cam0=[4161.221 0 1445.577; 0 4161.221 984.686; 0 0 1]
cam1=[4161.221 0 1654.636; 0 4161.221 984.686; 0 0 1]
doffs=209.059
baseline=176.252
width=2880
height=1988
ndisp=280
isint=0
vmin=25
vmax=248
dyavg=0
dymax=0
"""


def write_pfm(path, data, little_endian=True):
    """Write a single-channel PFM. Rows are stored **bottom-up**, per the format."""
    data = np.asarray(data, dtype=np.float32)
    scale = -1.0 if little_endian else 1.0
    fmt = "<f" if little_endian else ">f"
    with open(path, "wb") as f:
        f.write(b"Pf\n")
        f.write(f"{data.shape[1]} {data.shape[0]}\n".encode())
        f.write(f"{scale}\n".encode())
        for row in data[::-1]:  # flip: first row written is the image's last
            f.write(b"".join(struct.pack(fmt, v) for v in row))


def make_scene(tmp_path, disparity=None, calib=CALIB, variants=("im1E", "im1L")):
    """A minimal but complete scene directory."""
    d = tmp_path / "Synthetic-perfect"
    d.mkdir(exist_ok=True)

    if disparity is None:
        # A ramp, so row and column order are both detectable, plus a hole.
        disparity = np.tile(np.linspace(12.0, 30.0, W), (H, 1))
        disparity[5:8, 5:8] = np.inf

    write_pfm(d / "disp0.pfm", disparity)
    write_pfm(d / "disp1.pfm", disparity)
    write_pfm(d / "disp0-sd.pfm", np.full((H, W), 0.25, np.float32))
    (d / "calib.txt").write_text(calib)

    rng = np.random.default_rng(0)
    for name in ("im0", "im1", *variants):
        img = (rng.random((H, W)) * 255).astype(np.uint8)
        cv2.imwrite(str(d / f"{name}.png"), img)
    return d


# --- PFM -------------------------------------------------------------------


def test_pfm_header_reports_shape_and_endianness(tmp_path):
    write_pfm(tmp_path / "a.pfm", np.zeros((7, 11), np.float32))
    magic, width, height, scale = pfm_header(tmp_path / "a.pfm")
    assert (magic, width, height) == ("Pf", 11, 7)
    assert scale < 0, "negative scale marks little-endian"


def test_pfm_rows_are_flipped_to_top_down(tmp_path):
    """The convention that fails silently.

    PFM stores scanlines bottom-up. A reader that skips the flip returns a
    vertically mirrored ground truth whose min, max, median and histogram are all
    unchanged -- there is no statistic that would catch it, which is why it is
    pinned with an asymmetric array.
    """
    original = np.arange(H * W, dtype=np.float32).reshape(H, W)
    write_pfm(tmp_path / "d.pfm", original)
    np.testing.assert_array_equal(read_pfm(tmp_path / "d.pfm"), original)
    # And it is genuinely asymmetric, or the assertion above proves nothing.
    assert not np.array_equal(original, original[::-1])


def test_pfm_reads_both_byte_orders_identically(tmp_path):
    data = np.linspace(-3.0, 5.0, H * W, dtype=np.float32).reshape(H, W)
    write_pfm(tmp_path / "le.pfm", data, little_endian=True)
    write_pfm(tmp_path / "be.pfm", data, little_endian=False)
    np.testing.assert_allclose(read_pfm(tmp_path / "le.pfm"), read_pfm(tmp_path / "be.pfm"))


def test_pfm_preserves_inf_rather_than_converting_it(tmp_path):
    """`inf` is Middlebury's marker for unknown; `nan` is this framework's.

    The reader keeps what was written. Converting here would hide the one place
    the translation happens, which belongs in MiddleburyScene where it is visible.
    """
    data = np.ones((H, W), np.float32)
    data[3, 4] = np.inf
    write_pfm(tmp_path / "x.pfm", data)
    out = read_pfm(tmp_path / "x.pfm")
    assert np.isinf(out[3, 4])
    assert not np.isnan(out).any()


def test_pfm_rejects_a_truncated_file(tmp_path):
    write_pfm(tmp_path / "t.pfm", np.zeros((8, 8), np.float32))
    raw = (tmp_path / "t.pfm").read_bytes()
    (tmp_path / "t.pfm").write_bytes(raw[: len(raw) - 40])
    with pytest.raises(ValueError, match="Truncated"):
        read_pfm(tmp_path / "t.pfm")


# --- calibration -----------------------------------------------------------


def test_calib_parses_the_matrix_form(tmp_path):
    (tmp_path / "calib.txt").write_text(CALIB)
    c = read_calib(tmp_path / "calib.txt")
    assert c["f"] == pytest.approx(4161.221)
    assert c["cx"] == pytest.approx(1445.577)
    assert c["cy"] == pytest.approx(984.686)
    assert c["doffs"] == pytest.approx(209.059)
    assert c["baseline"] == pytest.approx(176.252)
    assert (c["width"], c["height"], c["ndisp"]) == (2880, 1988, 280)


def test_calib_to_rig_is_the_documented_mapping(tmp_path):
    """The whole of ADR-0012's translation table, against hand-computed values."""
    (tmp_path / "calib.txt").write_text(CALIB)
    rig = rig_from_calib(read_calib(tmp_path / "calib.txt"))

    assert rig.focal_px == pytest.approx(4161.221)
    assert rig.baseline == pytest.approx(0.176252), "millimetres must become metres"
    assert rig.principal_point == pytest.approx((984.686, 1445.577)), "(row, col)"

    expected = 2.0 * np.arctan(209.059 / (2 * 4161.221))
    assert rig.vergence == pytest.approx(expected)
    # doffs = f*b/Zf is the identity the mapping is derived from.
    assert rig.fixation_distance == pytest.approx(4161.221 * 0.176252 / 209.059)


def test_calib_refuses_a_missing_doffs(tmp_path):
    (tmp_path / "calib.txt").write_text(
        "\n".join(ln for ln in CALIB.splitlines() if not ln.startswith("doffs"))
    )
    with pytest.raises(ValueError, match="doffs"):
        read_calib(tmp_path / "calib.txt")


def test_calib_catches_a_doffs_inconsistent_with_the_camera_matrices(tmp_path):
    """`doffs` must equal cx1-cx0. It is the only internal check the file affords."""
    (tmp_path / "calib.txt").write_text(CALIB.replace("doffs=209.059", "doffs=109.059"))
    with pytest.raises(ValueError, match="disagrees with"):
        read_calib(tmp_path / "calib.txt")


def test_depth_uses_middleburys_formula_not_ours(tmp_path):
    """ADR-0006: the stimulus must not be produced by the estimator's code path.

    The two agree by construction -- that is the point of the mapping -- so this
    verifies `rig_from_calib`, and is deliberately not evidence about physics.
    """
    from activestereo.geometry import disparity_to_depth

    (tmp_path / "calib.txt").write_text(CALIB)
    calib = read_calib(tmp_path / "calib.txt")
    rig = rig_from_calib(calib)

    d = np.linspace(30.0, 240.0, 50)
    np.testing.assert_allclose(
        depth_from_disparity(d, calib), disparity_to_depth(d, rig), rtol=1e-9
    )


# --- the scene -------------------------------------------------------------


def test_scene_satisfies_the_protocol(tmp_path):
    assert isinstance(MiddleburyScene(make_scene(tmp_path), downsample=1), Scene)


def test_unknown_disparity_becomes_known_false(tmp_path):
    s = MiddleburyScene(make_scene(tmp_path), downsample=1).stimulus()
    assert s.known is not None
    assert not s.known[5:8, 5:8].any()
    assert s.known.sum() == H * W - 9
    assert np.isnan(s.disparity[5:8, 5:8]).all(), "inf must become nan (CLAUDE.md §3)"


def test_unknown_pixels_are_neither_occluded_nor_out_of_frame(tmp_path):
    """ADR-0011, on the corpus that forced it."""
    s = MiddleburyScene(make_scene(tmp_path), downsample=1).stimulus()
    hole = np.zeros((H, W), bool)
    hole[5:8, 5:8] = True
    assert not (s.occluded & hole).any()
    assert not (s.out_of_frame & hole).any()
    assert s.unknown_fraction == pytest.approx(9 / (H * W))


def test_in_frame_is_derived_not_taken_from_a_mask(tmp_path):
    """Middlebury's own generator folds out-of-frame into 'occluded'; we do not.

    A left pixel whose correspondent falls off the left edge is a field-of-view
    limit. Here the disparity ramp starts at 12 px, so the first 12 columns have
    no partner and must land in `out_of_frame`, never in `occluded`.
    """
    s = MiddleburyScene(make_scene(tmp_path), downsample=1).stimulus()
    assert s.out_of_frame[:, :10].any()
    assert not (s.out_of_frame & s.occluded).any()
    assert not s.in_frame[:, 0].any()


def test_right_variant_changes_pixels_and_nothing_else(tmp_path):
    """im1E / im1L vary photometry with geometry held exactly fixed -- which is
    what makes them a brightness-constancy experiment rather than a new scene."""
    scene = MiddleburyScene(make_scene(tmp_path), downsample=1)
    base = scene.stimulus("im1")
    for variant in ("im1E", "im1L"):
        other = scene.stimulus(variant)
        assert not np.array_equal(base.right, other.right)
        np.testing.assert_array_equal(base.left, other.left)
        np.testing.assert_array_equal(np.nan_to_num(base.disparity), np.nan_to_num(other.disparity))
        np.testing.assert_array_equal(base.matched, other.matched)
        np.testing.assert_array_equal(base.known, other.known)


def test_unknown_right_variant_raises(tmp_path):
    scene = MiddleburyScene(make_scene(tmp_path), downsample=1)
    with pytest.raises(ValueError, match="unknown right variant"):
        scene.stimulus("im1X")


def test_rig_mismatch_raises_rather_than_rescaling(tmp_path):
    from activestereo.types import StereoRig

    scene = MiddleburyScene(make_scene(tmp_path), downsample=1)
    wrong = StereoRig(baseline=0.064, focal_px=800.0, vergence=scene.rig.vergence)
    with pytest.raises(ValueError, match="rig mismatch"):
        scene.render(wrong, np.random.default_rng(0))


def test_render_ignores_rng(tmp_path):
    scene = MiddleburyScene(make_scene(tmp_path), downsample=1)
    a = scene.render(scene.rig, np.random.default_rng(1))
    b = scene.render(scene.rig, np.random.default_rng(999))
    np.testing.assert_array_equal(a.left, b.left)
    np.testing.assert_array_equal(a.matched, b.matched)


def test_imperfect_scenes_are_refused(tmp_path):
    """dymax > 0 means vertical disparity, and every matcher in inference/ assumes
    epipolar lines are image rows. Loading one would produce quiet nonsense."""
    d = make_scene(tmp_path, calib=CALIB.replace("dymax=0", "dymax=1.516"))
    with pytest.raises(ValueError, match="vertical disparity"):
        MiddleburyScene(d, downsample=1)


def test_missing_calib_raises_with_a_useful_message(tmp_path):
    d = make_scene(tmp_path)
    (d / "calib.txt").unlink()
    with pytest.raises(FileNotFoundError, match="metric scale"):
        MiddleburyScene(d)


# --- downsampling ----------------------------------------------------------


def test_downsampling_leaves_metric_depth_and_vergence_alone(tmp_path):
    """The self-consistency check for the whole scaling story.

    Z = f b / (d + doffs). Under a factor k, f, d and doffs all scale by 1/k and
    the metre cancels exactly; vergence = 2 arctan(doffs/2f) is a ratio of two
    pixel quantities and is invariant. If either moved, the rig and the ground
    truth would be describing different cameras.
    """
    d = make_scene(tmp_path)
    full = MiddleburyScene(d, downsample=1)
    small = MiddleburyScene(d, downsample=3)

    assert small.rig.vergence == pytest.approx(full.rig.vergence)
    assert small.rig.focal_px == pytest.approx(full.rig.focal_px / 3)
    assert small.rig.baseline == pytest.approx(full.rig.baseline)

    a, b = full.stimulus(), small.stimulus()
    assert b.shape == (H // 3, W // 3)

    # Ground truth is point-sampled at the block centre, so the downsampled depth
    # is not merely close to the full-resolution depth -- it is the *same values*,
    # taken from known positions. Compare those exactly rather than settling for a
    # tolerance on min and max, which a factor-of-k error could still slip past.
    off = (3 - 1) // 2
    np.testing.assert_array_equal(b.depth, a.depth[off :: 3, off :: 3][: b.shape[0], : b.shape[1]])


def test_downsampling_scales_disparity_by_the_factor(tmp_path):
    d = make_scene(tmp_path)
    a = MiddleburyScene(d, downsample=1).stimulus()
    b = MiddleburyScene(d, downsample=3).stimulus()
    assert np.nanmedian(b.disparity) == pytest.approx(np.nanmedian(a.disparity) / 3, rel=0.05)


def test_ndisp_rounds_up_so_the_search_range_still_covers_the_scene(tmp_path):
    """BlockMatcher rejects a winner at the last index of its range, so ndisp must
    not be an underestimate -- an off-by-one silently discards every true
    maximum-disparity pixel."""
    d = make_scene(tmp_path)
    assert MiddleburyScene(d, downsample=1).ndisp == 280
    assert MiddleburyScene(d, downsample=3).ndisp == 94  # ceil(280/3)
    s = MiddleburyScene(d, downsample=3).stimulus()
    assert np.nanmax(s.disparity) < MiddleburyScene(d, downsample=3).ndisp


def test_image_downsampling_averages_and_ground_truth_does_not(tmp_path):
    """The deliberate asymmetry (ADR-0012).

    Images get a box mean, which is a genuine antialiasing low-pass. Disparity is
    point-sampled, because averaging across a depth discontinuity invents a
    surface at the mean depth that exists nowhere in the scene.
    """
    step = np.full((H, W), 10.0)
    step[:, W // 2 :] = 40.0
    d = make_scene(tmp_path, disparity=step)
    s = MiddleburyScene(d, downsample=3).stimulus()

    # Ground truth: only the two true disparities survive. An average would emit
    # intermediate values along the step -- a surface at 25 px that is nowhere in
    # the scene, sitting exactly where the occlusion statistics are computed.
    present = np.unique(np.round(s.disparity[np.isfinite(s.disparity)] * 3))
    assert set(present) <= {10.0, 40.0}, f"averaged across the step: {present}"

    # The image, conversely, *must* be averaged: decimating it would alias fine
    # texture into noise, which is the signal exp003 found decisive. Check the
    # block mean directly rather than inferring it.
    full = MiddleburyScene(d, downsample=1).stimulus()
    block = full.left[:30, :45].reshape(10, 3, 15, 3).mean(axis=(1, 3))
    np.testing.assert_allclose(s.left[:10, :15], block, rtol=1e-12)
    assert not np.allclose(s.left[:10, :15], full.left[1:30:3, 1:45:3]), (
        "image was decimated, not averaged"
    )


def test_noise_floor_scales_with_the_factor(tmp_path):
    d = make_scene(tmp_path)
    assert MiddleburyScene(d, downsample=1).noise_floor() == pytest.approx(0.25)
    assert MiddleburyScene(d, downsample=3).noise_floor() == pytest.approx(0.25 / 3)


# --- the cross-check, against Middlebury's own generator --------------------


def _computemask(disp0, disp1, thresh=1.0):
    """Transcription of MiddEval3-SDK-1.6/code/computemask.cpp, dir = -1.

    C's round() is half-away-from-zero, which is not numpy's default and is the
    entire reason this reference exists.
    """
    import math

    out = np.zeros(disp0.shape, bool)
    width = disp0.shape[1]
    for y in range(disp0.shape[0]):
        for x in range(width):
            dx = disp0[y, x]
            if np.isinf(dx):
                continue
            v = x - dx
            x1 = math.trunc(v + math.copysign(0.5, v))
            if x1 < 0 or x1 >= width:
                continue
            if abs(dx - disp1[y, x1]) <= thresh:
                out[y, x] = True
    return out


def test_cross_check_reproduces_middleburys_generator(tmp_path):
    """Not "close to" -- it is the same algorithm, so anything short of exact
    agreement is a bug here. Verified against 2.88M real pixels at the Stage 0
    checkpoint; this keeps it true."""
    rng = np.random.default_rng(3)
    d0 = rng.uniform(2.0, 20.0, (24, 40))
    d1 = d0 + rng.normal(0.0, 1.2, d0.shape)
    d0[2:5, 30:33] = np.inf
    np.testing.assert_array_equal(cross_check_disparity(d0, d1, 1.0), _computemask(d0, d1, 1.0))


def test_cross_check_agrees_on_exact_half_disparities(tmp_path):
    """The case the previous test cannot reach, and the only case that ever
    disagreed.

    Continuous disparity never lands on a tie; Middlebury's quantised scanner
    lands on one constantly. Two things separate a naive implementation from
    `computemask.cpp` there, and both are invisible everywhere else:

    - ``x - rint(d)`` is not ``rint(x - d)`` on a tie. With d = 131.5 at x = 2395
      the first gives 2263 and the second 2264, and which wins depends on the
      *parity of the column index* -- not a property of the scene.
    - ``np.rint`` breaks ties to even; C's ``round`` breaks them away from zero.

    Every disparity here is an exact half, so a regression in either detail shows
    up immediately rather than as six pixels in a million.
    """
    rows, cols = 8, 64
    d0 = np.zeros((rows, cols))
    for y in range(rows):
        # Vary the offset per row so ties fall on both even and odd columns.
        d0[y] = np.arange(cols) * 0.0 + (10.5 + y)
    assert np.all((d0 % 1.0) == 0.5), "the fixture must be all ties"

    d1 = d0.copy()
    np.testing.assert_array_equal(cross_check_disparity(d0, d1, 1.0), _computemask(d0, d1, 1.0))

    # And with the partner perturbed, so acceptance is not uniformly true.
    rng = np.random.default_rng(11)
    d1 = d0 + rng.choice([-1.5, 0.0, 1.5], size=d0.shape)
    ours = cross_check_disparity(d0, d1, 1.0)
    assert 0 < ours.mean() < 1, "fixture must produce a mix of matched and not"
    np.testing.assert_array_equal(ours, _computemask(d0, d1, 1.0))
