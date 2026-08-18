"""The config -> scene dispatch.

``scene.kind`` was written into every scene config at bootstrap and read by
nothing, which is why ``configs/scene/textured_slant.yaml`` describes a stimulus
that has never existed. These tests pin the two properties that matter: the
committed configs actually resolve, and an unbuildable one fails loudly rather
than falling back to a random-dot stereogram and answering a different question.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from activestereo.scenes import RandomDotStereogram, Scene, from_config
from activestereo.scenes.registry import UNIMPLEMENTED
from activestereo.utils import load_config

CONFIGS = Path(__file__).resolve().parents[2] / "configs" / "scene"


def test_rds_config_builds_a_scene():
    scenes = from_config(load_config(CONFIGS / "rds_disk.yaml"))
    assert len(scenes) == 1
    assert isinstance(scenes[0], RandomDotStereogram)
    assert isinstance(scenes[0], Scene)
    assert scenes[0].shape == (240, 320)


def test_rds_config_round_trips_its_parameters():
    """The config's numbers must reach the scene, or the file is decoration."""
    cfg = load_config(CONFIGS / "rds_disk.yaml")
    scene = from_config(cfg)[0]
    assert scene.dot_size == cfg["scene"]["dot_size"]
    assert scene.density == cfg["scene"]["density"]

    from activestereo.types import StereoRig

    rig = StereoRig(baseline=0.064, focal_px=800.0, vergence=np.deg2rad(1.467))
    stim = scene.render(rig, np.random.default_rng(0))
    assert stim.shape == (240, 320)
    assert stim.known is None, "a synthetic stimulus knows every pixel (ADR-0011)"


def test_returns_a_list_even_for_a_single_scene():
    """Uniform arity: a config describes a stimulus *set*, and a caller should
    not have to know whether its own config happens to name one or ten."""
    assert isinstance(from_config(load_config(CONFIGS / "rds_disk.yaml")), list)


def test_unimplemented_kind_says_why():
    """textured_slant has no class behind it. The failure should say that, not
    raise a bare KeyError that reads like a typo."""
    with pytest.raises(ValueError, match="not implemented"):
        from_config(load_config(CONFIGS / "textured_slant.yaml"))
    assert "textured_slant" in UNIMPLEMENTED


def test_unknown_kind_lists_the_known_ones():
    with pytest.raises(ValueError, match="unknown scene kind"):
        from_config({"scene": {"kind": "holodeck"}})


def test_missing_kind_is_an_error_not_a_default():
    """Defaulting to RDS would silently answer a different question."""
    with pytest.raises(ValueError, match="no 'kind'"):
        from_config({"scene": {"shape": [64, 64]}})


def test_missing_scene_block_is_an_error():
    with pytest.raises(ValueError, match="no 'scene' block"):
        from_config({"matcher": {"max_disparity": 32}})


def test_middlebury_config_parses_and_reports_what_is_missing(tmp_path):
    """Without the corpus on disk this must name the fetch script, not fail
    somewhere deep in a PFM reader."""
    cfg = load_config(CONFIGS / "middlebury2014.yaml")
    cfg["scene"]["root"] = str(tmp_path)
    with pytest.raises(FileNotFoundError, match="fetch_middlebury"):
        from_config(cfg)


def test_middlebury_requires_an_explicit_scene_list(tmp_path):
    """ADR-0012: the scene list is pre-registered. Globbing whatever is on disk
    would make the corpus depend on fetch history rather than on a decision."""
    with pytest.raises(ValueError, match="pre-registered"):
        from_config({"scene": {"kind": "middlebury", "root": str(tmp_path), "scenes": []}})


def test_middlebury_config_matches_the_fetch_manifest():
    """Two files name the same ten scenes. If they drift, the experiment scores a
    different corpus than the one that was downloaded and checksummed."""
    import yaml

    scene_cfg = load_config(CONFIGS / "middlebury2014.yaml")
    manifest = yaml.safe_load(
        (CONFIGS.parent / "dataset" / "middlebury2014.yaml").read_text()
    )["dataset"]
    assert scene_cfg["scene"]["scenes"] == manifest["scenes"]
    assert scene_cfg["scene"]["variant"] == manifest["variant"]


def test_middlebury_builder_actually_constructs_a_scene(tmp_path):
    """The gap that let a real bug through.

    Every other middlebury test raises before reaching the constructor -- on a
    missing directory or a malformed config -- so none of them exercised the
    kwargs the builder forwards. `_reject_leftovers` validated the inherited keys
    without consuming them, so `shape` from configs/default.yaml was splatted into
    `MiddleburyScene(...)`, which has no such parameter. It failed only when the
    corpus was present, i.e. never in the suite.
    """
    pytest.importorskip("cv2", reason="needs the 'cv' extra")
    from test_middlebury import make_scene

    make_scene(tmp_path)
    (tmp_path / "Synthetic-perfect").rename(tmp_path / "Fake-perfect")

    cfg = load_config(CONFIGS / "middlebury2014.yaml")
    cfg["scene"]["root"] = str(tmp_path)
    cfg["scene"]["scenes"] = ["Fake"]
    scenes = from_config(cfg)

    assert len(scenes) == 1
    assert isinstance(scenes[0], Scene)
    stim = scenes[0].stimulus()
    assert stim.known is not None, "measured ground truth must carry a known mask"
    assert stim.rig.vergence > 0


def test_inherited_keys_matches_configs_default():
    """INHERITED_KEYS is what every scene block gets from configs/default.yaml
    whether it wants it or not. If default.yaml grows a scene key and this set
    does not, every non-RDS config starts failing as though it had a typo."""
    import yaml

    from activestereo.scenes.registry import INHERITED_KEYS

    base = yaml.safe_load((CONFIGS.parent / "default.yaml").read_text())
    assert set(base["scene"]) == INHERITED_KEYS


def test_a_typo_is_rejected_rather_than_dropped():
    """The reason leftovers are checked at all: a dropped key leaves the stimulus
    at its default while the config claims otherwise, and nothing reports it."""
    cfg = load_config(CONFIGS / "rds_disk.yaml")
    cfg["scene"]["dot_sizee"] = 9
    with pytest.raises(ValueError, match="does not use"):
        from_config(cfg)


def test_config_errors_surface_before_filesystem_errors(tmp_path):
    """A malformed config should say so even when the data is also absent --
    otherwise fixing the download only reveals the next problem."""
    with pytest.raises(ValueError, match="does not use"):
        from_config(
            {
                "scene": {
                    "kind": "middlebury",
                    "root": str(tmp_path),
                    "scenes": ["Adirondack"],
                    "downsampel": 3,
                }
            }
        )


def test_blender_chart_config_reports_missing_renders(tmp_path):
    cfg = load_config(CONFIGS / "material_chart.yaml")
    cfg["scene"]["stimulus_root"] = str(tmp_path)
    with pytest.raises(FileNotFoundError, match="render_chart_sweep"):
        from_config(cfg)
