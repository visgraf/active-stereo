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

from collections.abc import Sequence
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


def _read_exr_parts(path: Path) -> list[tuple[str, list[str], FloatArray]]:
    """Read every part of an EXR as ``(part_name, channel_names, data)``.

    Blender writes multi-layer EXR as a **multi-part** file: one part per render
    pass, not one wide part with prefixed channel names. Reading only part 0
    yields the beauty pass and nothing else -- the depth pass is simply invisible,
    with no error to indicate anything is missing. Every part must be walked.
    """
    try:
        import OpenImageIO
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise ImportError(
            "Reading multi-layer EXR needs OpenImageIO: pip install OpenImageIO. "
            "OpenCV cannot address named layers."
        ) from exc

    src = OpenImageIO.ImageInput.open(str(path))
    if src is None:
        raise OSError(f"could not open {path}: {OpenImageIO.geterror()}")

    parts: list[tuple[str, list[str], FloatArray]] = []
    index = 0
    try:
        while True:
            spec = src.spec()
            # First two arguments are subimage and miplevel. Passing 0 here while
            # positioned on a later part re-seeks to part 0 with a mismatched
            # channel count, which segfaults rather than raising.
            pixels = src.read_image(index, 0, 0, spec.nchannels, "float")
            if pixels is None:
                raise OSError(f"could not read subimage {index} of {path}")
            data = np.asarray(pixels, dtype=float).reshape(spec.height, spec.width, spec.nchannels)
            parts.append((spec.get_string_attribute("name") or "", list(spec.channelnames), data))
            index += 1
            if not src.seek_subimage(index, 0):
                break
    finally:
        src.close()
    return parts


def read_multilayer_exr(path: str | Path) -> dict[str, FloatArray]:
    """Extract the beauty and depth layers from a Blender multi-layer EXR.

    Handles both layouts Blender has used: multi-part files, where each pass is
    its own part named e.g. ``ViewLayer.Depth`` with channels ``Z``; and
    single-part files with prefixed channel names like ``ViewLayer.Depth.Z``.
    The depth channel letter has been both ``Z`` and ``V``.

    Returns ``"image"`` (grayscale, [0, 1]) and ``"depth"`` (metres, non-hits as
    ``nan``).
    """
    path = Path(path)
    parts = _read_exr_parts(path)

    depth: FloatArray | None = None
    image: FloatArray | None = None

    for part_name, channels, data in parts:
        qualified = [f"{part_name}.{c}" if part_name else c for c in channels]

        if depth is None:
            idx = _find_channel(qualified, ("depth",), suffixes=(".z", ".v"))
            if idx is None and "depth" in part_name.lower():
                idx = 0
            if idx is not None:
                depth = data[..., idx].astype(float)

        if image is None:
            # Cycles emits auxiliary colour passes alongside the beauty pass --
            # "Noisy Image", and with denoising data also "Denoising Albedo" and
            # "Denoising Normal". Averaging those into the image is silent
            # corruption: the result still looks like a plausible photograph.
            # Take Combined when it is present; only fall back to bare R/G/B.
            colour = [
                i
                for i, name in enumerate(qualified)
                if name.lower().rsplit(".", 1)[-1] in ("r", "g", "b")
            ]
            preferred = [i for i in colour if "combined" in qualified[i].lower()]
            rgb = preferred or [i for i in colour if qualified[i].lower() in ("r", "g", "b")]
            if rgb:
                image = data[..., rgb].mean(axis=2)

    if depth is None:
        found = [(name, chans) for name, chans, _ in parts]
        raise KeyError(
            f"no depth layer in {path.name}. Parts present: {found}. "
            "Enable the Z pass before rendering (view_layer.use_pass_z)."
        )
    if image is None:
        image = parts[0][2][..., 0].astype(float)

    depth = np.array(depth, dtype=float, copy=True)
    depth[~np.isfinite(depth) | (depth > 1e6) | (depth <= 0)] = np.nan
    return {"image": image, "depth": depth}


def _find_channel(
    names: Sequence[str],
    contains: Sequence[str],
    suffixes: Sequence[str] = (),
) -> int | None:
    """Index of the first channel matching any substring or suffix, or None."""
    lowered = [n.lower() for n in names]
    for i, name in enumerate(lowered):
        if any(token in name for token in contains):
            return i
    for i, name in enumerate(lowered):
        if any(name.endswith(suffix) for suffix in suffixes):
            return i
    return None


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

    # Multi-layer layout (the default render mode): one EXR per eye, containing
    # both the beauty and depth passes as named layers.
    if (directory / "left.exr").exists():
        left_layers = read_multilayer_exr(directory / "left.exr")
        depth_left = left_layers["depth"]
        if depth_is_radial:
            depth_left = radial_to_planar(depth_left, rig.focal_px)

        right_path = directory / "right.exr"
        if not right_path.exists():
            raise FileNotFoundError(
                f"missing {right_path}. Both eyes are required: a single depth "
                "pass cannot express half-occlusion."
            )
        right_layers = read_multilayer_exr(right_path)
        depth_right = right_layers["depth"]
        if depth_is_radial:
            depth_right = radial_to_planar(depth_right, rig.focal_px)

        return StereoStimulus(
            left=left_layers["image"],
            right=right_layers["image"],
            depth=depth_left,
            disparity=depth_to_disparity(depth_left, rig),
            matched=cross_check_occlusion(depth_left, depth_right, rig),
            in_frame=_in_frame(depth_left, rig),
            rig=rig,
        )

    # Compositor layout: separate PNG and EXR files per pass.
    if not (directory / left_name).exists():
        contents = sorted(p.name for p in directory.iterdir()) if directory.is_dir() else []
        raise FileNotFoundError(
            f"{directory} matches neither render layout.\n"
            f"  multi-layer (default): left.exr, right.exr  -- not found\n"
            f"  compositor:            {left_name}, {depth_left_name}  -- not found\n"
            f"  directory contains:    {contents}\n"
            "If left.exr is present and this still fires, activestereo is out of "
            "date: multi-layer support was added in ADR-0010."
        )
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
