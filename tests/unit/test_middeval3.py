"""The MiddEval3 loader and the PFM writer that benchmark submissions go through.

Same fixture strategy as test_middlebury.py: the distribution lives outside the
repository, so every test writes a scene directory by hand and reads it back
through the real code path.

The writer is tested by round-trip through :func:`read_pfm` rather than against
hand-packed bytes: read_pfm's conventions (bottom-up rows, sign-of-scale
endianness) are already pinned by test_middlebury.py, so agreement with it *is*
agreement with the format.
"""

from __future__ import annotations

import numpy as np
import pytest

from activestereo.scenes.middeval3 import MiddEval3Scene, training_scenes
from activestereo.scenes.middlebury import read_pfm, write_pfm

cv2 = pytest.importorskip("cv2", reason="needs the 'cv' extra")

H, W = 24, 36

# ArtL from trainingQ, verbatim -- an imperfect-rectification pair (dymax > 0),
# because accepting those is exactly where this loader differs from
# MiddleburyScene and a perfect-rectification fixture would not exercise it.
CALIB = """cam0=[695.902 0 337.703; 0 695.902 235.847; 0 0 1]
cam1=[695.902 0 337.703; 0 695.902 235.847; 0 0 1]
doffs=0
baseline=139.008
width=694
height=554
ndisp=64
isint=0
vmin=8
vmax=55
dyavg=0.253
dymax=1.145
"""


def _scene_dir(tmp_path, calib=CALIB):
    d = tmp_path / "ArtL"
    d.mkdir()
    (d / "calib.txt").write_text(calib)
    rng = np.random.default_rng(7)
    for name in ("im0.png", "im1.png"):
        cv2.imwrite(str(d / name), rng.integers(0, 255, size=(H, W), dtype=np.uint8))
    return d


# --- write_pfm --------------------------------------------------------------


def test_write_pfm_roundtrips_through_read_pfm(tmp_path):
    rng = np.random.default_rng(0)
    a = rng.normal(size=(H, W)) * 100.0
    write_pfm(tmp_path / "d.pfm", a)
    back = read_pfm(tmp_path / "d.pfm")
    np.testing.assert_allclose(back, a.astype(np.float32), rtol=0, atol=0)


def test_write_pfm_converts_nan_to_inf(tmp_path):
    a = np.full((4, 5), 3.5)
    a[1, 2] = np.nan  # the framework's invalid marker (CLAUDE.md §3)
    write_pfm(tmp_path / "d.pfm", a)
    back = read_pfm(tmp_path / "d.pfm")
    # read_pfm preserves inf deliberately; nan must have become Middlebury's
    # marker on the way out, so nothing in the file is nan.
    assert np.isposinf(back[1, 2])
    assert not np.isnan(back).any()


def test_write_pfm_rejects_non_2d(tmp_path):
    with pytest.raises(ValueError, match="2-D"):
        write_pfm(tmp_path / "d.pfm", np.zeros((2, 3, 4)))


# --- MiddEval3Scene ---------------------------------------------------------


def test_scene_exposes_images_rig_and_ndisp(tmp_path):
    scene = MiddEval3Scene(_scene_dir(tmp_path))
    assert scene.left.shape == (H, W)
    assert scene.right.shape == (H, W)
    assert 0.0 <= scene.left.min() and scene.left.max() <= 1.0
    assert scene.ndisp == 64
    assert np.isclose(scene.rig.baseline, 0.139008)  # mm -> m at the boundary
    assert np.isclose(scene.rig.focal_px, 695.902)


def test_imperfect_rectification_is_recorded_not_refused(tmp_path):
    # MiddleburyScene refuses dymax > 0; this loader's whole reason to exist
    # is measuring what that residual costs, so it must load and report it.
    scene = MiddEval3Scene(_scene_dir(tmp_path))
    assert scene.dyavg == pytest.approx(0.253)
    assert scene.dymax == pytest.approx(1.145)


def test_missing_calib_raises_with_the_fetch_command(tmp_path):
    empty = tmp_path / "NoScene"
    empty.mkdir()
    with pytest.raises(FileNotFoundError, match="fetch_middeval3"):
        MiddEval3Scene(empty)


def test_training_scenes_lists_the_tree(tmp_path):
    split = tmp_path / "MiddEval3" / "trainingQ"
    split.mkdir(parents=True)
    for name in ("B_scene", "A_scene"):
        d = split / name
        d.mkdir()
        (d / "calib.txt").write_text(CALIB)
        cv2.imwrite(str(d / "im0.png"), np.zeros((H, W), dtype=np.uint8))
        cv2.imwrite(str(d / "im1.png"), np.zeros((H, W), dtype=np.uint8))
    scenes = training_scenes(tmp_path)
    assert [s.directory.name for s in scenes] == ["A_scene", "B_scene"]


def test_training_scenes_missing_tree_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="fetch_middeval3"):
        training_scenes(tmp_path)
