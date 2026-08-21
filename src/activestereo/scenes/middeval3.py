"""Loader for MiddEval3, the Middlebury Stereo Evaluation v3 distribution.

Deliberately minimal, and deliberately not :class:`MiddleburyScene`. That class
loads the scenes2014 corpus -- perfect rectification, ground truth handled by
us, our masks, our downsampling. This one loads the *benchmark's* tree
(``MiddEval3/trainingQ/<Scene>/``), whose pairs are already at the working
resolution and whose scoring belongs to the benchmark's own SDK: producing
leaderboard-comparable numbers means using their evaluator and their masks,
so this loader hands over images and calibration and nothing else. Building a
:class:`StereoStimulus` here would create a second, slightly different scoring
path for the same photographs, which is exactly the kind of duplicate
convention CLAUDE.md §3 forbids.

The consequential difference from :class:`MiddleburyScene`: v3 pairs have
**imperfect rectification** -- residual vertical disparities are part of the
benchmark. ``MiddleburyScene`` refuses such scenes because every matcher in
``inference/`` assumes epipolar lines are image rows. This loader accepts them
and *records* ``dyavg``/``dymax`` instead, because measuring what that
assumption costs is the point of running the benchmark at all. The refusal
was right for experiments that wanted the assumption satisfied; the benchmark
wants it stressed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from activestereo.scenes.middlebury import read_calib, rig_from_calib
from activestereo.types import FloatArray, StereoRig


class MiddEval3Scene:
    """One ``MiddEval3/<split>/<Scene>`` directory: images and calibration.

    Parameters
    ----------
    directory : a scene directory containing ``im0.png``, ``im1.png`` and
        ``calib.txt``. Ground-truth files (``disp0GT.pfm``, masks), when
        present, are read by the SDK's evaluator, never here.
    """

    def __init__(self, directory: str | Path, name: str | None = None) -> None:
        self.directory = Path(directory)
        calib_path = self.directory / "calib.txt"
        if not calib_path.exists():
            raise FileNotFoundError(
                f"missing {calib_path}. Fetch the benchmark first: "
                "python scripts/fetch_middeval3.py"
            )
        self.calib: dict[str, Any] = read_calib(calib_path)
        self._name = name or f"middeval3_{self.directory.name}"

    @property
    def name(self) -> str:
        return self._name

    @property
    def rig(self) -> StereoRig:
        """The capture rig at this resolution, via the doffs-vergence identity."""
        return rig_from_calib(self.calib)

    @property
    def ndisp(self) -> int:
        """The benchmark's per-pair search bound. Pass as ``max_disparity``
        directly, not ``ndisp - 1`` -- see :meth:`MiddleburyScene.ndisp`."""
        return int(self.calib["ndisp"])

    @property
    def dyavg(self) -> float:
        """Average residual vertical disparity, pixels. 0.0 when not recorded."""
        return float(self.calib.get("dyavg", 0.0))

    @property
    def dymax(self) -> float:
        """Maximum residual vertical disparity, pixels. 0.0 when not recorded."""
        return float(self.calib.get("dymax", 0.0))

    @property
    def left(self) -> FloatArray:
        return self._image("im0.png")

    @property
    def right(self) -> FloatArray:
        return self._image("im1.png")

    def _image(self, filename: str) -> FloatArray:
        import cv2  # optional 'cv' extra; see scenes.blender._read_gray

        from activestereo.scenes.blender import _read_gray

        return _read_gray(cv2, self.directory / filename)


def training_scenes(root: str | Path, resolution: str = "Q") -> list[MiddEval3Scene]:
    """Every scene under ``<root>/MiddEval3/training<resolution>``, sorted.

    The training list is the benchmark's, not ours -- whatever the
    distribution contains is what gets evaluated, so unlike the scenes2014
    manifest there is no pre-registered subset to enforce here.
    """
    split = Path(root).expanduser() / "MiddEval3" / f"training{resolution}"
    if not split.is_dir():
        raise FileNotFoundError(
            f"no {split}. Fetch the benchmark first: python scripts/fetch_middeval3.py"
        )
    return [MiddEval3Scene(d) for d in sorted(split.iterdir()) if (d / "calib.txt").exists()]
