"""Loader for scenes rendered by ``scripts/render_stereo.py``.

Blender writes a stereo pair plus a depth pass; this module converts them into a
:class:`~activestereo.scenes.base.StereoStimulus` in *our* conventions. Every
unit and frame conversion happens here and nowhere else, which is the point of
having an I/O boundary at all.

Two conversions are easy to get wrong, so both are explicit:

**Depth pass geometry.** Blender's depth pass may be *radial* (distance along the
ray) or *planar* (distance along the camera's view axis) depending on version and
render engine. Our framework wants planar depth. ``load_render`` takes an explicit
``depth_is_radial`` flag rather than guessing; ``infer_depth_convention`` will
tell you which one a calibration render used.

**Occlusion ground truth.** A single rendered pair does not carry it. The render
script writes a right-eye depth pass alongside, and :func:`cross_check_occlusion`
recovers half-occlusion by left-right consistency. Where that pass is missing,
``matched`` is all-True and any occlusion-sensitive result from the scene should
be treated as unvalidated.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from activestereo.geometry import depth_to_disparity
from activestereo.scenes.base import StereoStimulus
from activestereo.types import FloatArray, StereoRig


def focal_px_from_blender(resolution_x: int, sensor_width_mm: float, lens_mm: float) -> float:
    """Convert a Blender camera to focal length in pixels.

    ``f_px = lens_mm * resolution_x / sensor_width_mm``, valid when the camera's
    sensor fit is horizontal (Blender's default for landscape renders).
    """
    if min(resolution_x, sensor_width_mm, lens_mm) <= 0:
        raise ValueError("resolution, sensor width, and lens must all be positive")
    return float(lens_mm * resolution_x / sensor_width_mm)


def rig_from_blender(
    resolution_x: int,
    sensor_width_mm: float,
    lens_mm: float,
    interocular: float,
    convergence_distance: float,
) -> StereoRig:
    """Build a :class:`StereoRig` matching a Blender stereo camera.

    ``convergence_distance`` is Blender's off-axis convergence plane. We express
    it as the equivalent vergence angle so that ``rig.fixation_distance`` returns
    it back. See ADR-0007 for why off-axis is the mode to use.
    """
    vergence = 2.0 * np.arctan(interocular / (2.0 * convergence_distance))
    return StereoRig(
        baseline=float(interocular),
        focal_px=focal_px_from_blender(resolution_x, sensor_width_mm, lens_mm),
        vergence=float(vergence),
    )


def radial_to_planar(depth: FloatArray, focal_px: float) -> FloatArray:
    """Convert ray distance to distance along the optical axis.

    ``Z = r * f / sqrt(f^2 + u^2 + v^2)`` for pixel offset ``(u, v)`` from the
    principal point. The correction is negligible at the centre and reaches
    several percent at the corners of a wide field -- exactly the region where
    ADR-0003's foveal confinement is already doing work, so an uncorrected error
    here is easy to mistake for a modelling result.
    """
    H, W = depth.shape
    rows, cols = np.indices((H, W))
    u = cols - (W - 1) / 2.0
    v = rows - (H - 1) / 2.0
    return depth * focal_px / np.sqrt(focal_px**2 + u**2 + v**2)


def infer_depth_convention(depth: FloatArray, tolerance: float = 1e-3) -> str:
    """Diagnose a calibration render of a fronto-parallel plane.

    Returns ``"planar"`` if depth is constant across the field, ``"radial"`` if it
    grows toward the corners, or ``"unknown"``. Run this once per Blender version
    on a flat-wall render and record the answer in the lab notebook; do not carry
    the assumption between versions.
    """
    finite = np.isfinite(depth)
    if not finite.any():
        return "unknown"
    centre = float(np.nanmedian(depth[depth.shape[0] // 2, :]))
    if centre <= 0:
        return "unknown"
    spread = float(np.nanmax(depth[finite]) - np.nanmin(depth[finite])) / centre
    if spread < tolerance:
        return "planar"
    corner = float(np.nanmean([depth[0, 0], depth[0, -1], depth[-1, 0], depth[-1, -1]]))
    return "radial" if corner > centre else "unknown"


def cross_check_occlusion(
    depth_left: FloatArray,
    depth_right: FloatArray,
    rig: StereoRig,
    tolerance: float = 1.0,
) -> NDArray[np.bool_]:
    """Recover half-occlusion by left-right consistency.

    A left pixel is matched when the right-eye depth at its predicted
    correspondent implies the same disparity, within ``tolerance`` pixels. This is
    ground truth rather than an estimate: both depth maps come from the renderer.
    """
    d = depth_to_disparity(depth_left, rig)
    H, W = depth_left.shape
    rows, cols = np.indices((H, W))
    target = cols - np.rint(np.nan_to_num(d, nan=0.0)).astype(int)
    in_bounds = (target >= 0) & (target < W) & np.isfinite(d)

    matched = np.zeros((H, W), dtype=bool)
    d_right = depth_to_disparity(depth_right[rows[in_bounds], target[in_bounds]], rig)
    matched[in_bounds] = np.abs(d_right - d[in_bounds]) <= tolerance
    return matched


def load_render(
    directory: str | Path,
    rig: StereoRig,
    depth_is_radial: bool = False,
    left_name: str = "left.png",
    right_name: str = "right.png",
    depth_left_name: str = "depth_left.exr",
    depth_right_name: str = "depth_right.exr",
) -> StereoStimulus:
    """Load a render directory written by ``scripts/render_stereo.py``.

    Requires OpenCV with EXR support (``OPENCV_IO_ENABLE_OPENEXR=1``), an optional
    dependency. Raises rather than silently substituting a default if the depth
    pass is missing -- a stimulus without ground truth is not a stimulus.
    """
    import os

    os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
    import cv2

    directory = Path(directory)
    left = _read_gray(cv2, directory / left_name)
    right = _read_gray(cv2, directory / right_name)
    depth_left = _read_depth(cv2, directory / depth_left_name)

    if depth_is_radial:
        depth_left = radial_to_planar(depth_left, rig.focal_px)

    right_depth_path = directory / depth_right_name
    if right_depth_path.exists():
        depth_right = _read_depth(cv2, right_depth_path)
        if depth_is_radial:
            depth_right = radial_to_planar(depth_right, rig.focal_px)
        matched = cross_check_occlusion(depth_left, depth_right, rig)
    else:
        matched = np.isfinite(depth_left)

    return StereoStimulus(
        left=left,
        right=right,
        depth=depth_left,
        disparity=depth_to_disparity(depth_left, rig),
        matched=matched,
        in_frame=_in_frame(depth_left, rig),
        rig=rig,
    )


def _in_frame(depth: FloatArray, rig: StereoRig) -> NDArray[np.bool_]:
    """Whether each left pixel's correspondent lands inside the right image."""
    d = depth_to_disparity(depth, rig)
    H, W = depth.shape
    _, cols = np.indices((H, W))
    target = cols - np.rint(np.nan_to_num(d, nan=0.0)).astype(int)
    return (target >= 0) & (target < W) & np.isfinite(d)


def _read_gray(cv2: Any, path: Path) -> FloatArray:
    """``cv2`` is passed in rather than imported at module scope: OpenCV is an
    optional dependency, so it is typed ``Any`` and resolved by the caller."""
    if not path.exists():
        raise FileNotFoundError(f"missing image: {path}")
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise OSError(f"could not decode image: {path}")
    return img.astype(float) / 255.0


def _read_depth(cv2: Any, path: Path) -> FloatArray:
    if not path.exists():
        raise FileNotFoundError(
            f"missing depth pass: {path}. Re-render with --depth-pass; a stimulus "
            "without ground truth cannot be used for evaluation."
        )
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED | cv2.IMREAD_ANYDEPTH)
    if img is None:
        raise OSError(f"could not decode depth pass: {path}")
    if img.ndim == 3:
        img = img[..., 0]
    depth = img.astype(float)
    # Blender writes non-hits as a very large value rather than nan.
    depth[~np.isfinite(depth) | (depth > 1e6) | (depth <= 0)] = np.nan
    return depth
