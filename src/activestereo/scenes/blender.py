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

import itertools
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from activestereo.geometry import depth_to_disparity
from activestereo.scenes.base import StereoStimulus
from activestereo.types import FloatArray, StereoRig
from activestereo.utils import boxsum


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
    grows toward the corners as a function of image radius alone, or
    ``"unknown"``. Run this once per Blender version on a flat-wall render and
    record the answer in the lab notebook; do not carry the assumption between
    versions.

    **Only meaningful on a fronto-parallel calibration render.** Handed an
    ordinary scene it used to answer ``"radial"`` with complete confidence, for
    the wrong reason: any scene with nearer objects toward the middle of frame
    has depth "growing toward the corners". Acting on that answer applies a
    spurious radial correction of several percent at the field edge -- which is
    indistinguishable from an ADR-0003 foveal-confinement result, in the one
    place the invariants cannot reach. This is the failure shape ADR-0009 calls
    "introspection can be confidently wrong".

    The guard: a flat wall is **radially symmetric** about the principal point
    under either convention, so depth must vary *with* image radius and not
    *around* it. When within-radius spread is comparable to total spread, the
    input is not a calibration render and the answer is ``"unknown"``.
    """
    finite = np.isfinite(depth)
    if not finite.any():
        return "unknown"
    centre = float(np.nanmedian(depth[depth.shape[0] // 2, :]))
    if centre <= 0:
        return "unknown"
    values = depth[finite]
    total = float(np.max(values) - np.min(values))
    if total / centre < tolerance:
        return "planar"

    H, W = depth.shape
    rows, cols = np.indices((H, W))
    radius = np.hypot(cols - (W - 1) / 2.0, rows - (H - 1) / 2.0)
    edges = np.linspace(0.0, float(radius.max()), 17)
    within = [
        float(np.ptp(depth[sel]))
        for lo, hi in itertools.pairwise(edges)
        if (sel := finite & (radius >= lo) & (radius < hi)).sum() >= 8
    ]
    if not within or float(np.median(within)) > 0.25 * total:
        return "unknown"

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

    Always returns ``"image"`` (grayscale) and ``"depth"`` (metres, non-hits as
    ``nan``). When the render enabled them, also returns the appearance passes:
    ``"albedo"`` (Diffuse Color -- surface colour with lighting removed),
    ``"glossy"`` (Glossy Direct -- specular energy alone) and
    ``"material_index"``. Callers must treat those three as optional.

    Note that ``"image"`` is **linear radiance, not clipped to [0, 1]** as
    ``StereoStimulus`` documents for synthetic stimuli. Specular highlights
    legitimately exceed 1; clipping them here would destroy exactly the
    structure a gloss experiment is measuring.

    Blender writes these layer names with spaces -- ``ViewLayer.Diffuse Color.R``,
    ``ViewLayer.Glossy Direct.R``, ``ViewLayer.Material Index.X`` -- not the
    ``DiffCol``/``GlossDir``/``IndexMA`` abbreviations used elsewhere in its
    codebase. Verified against 5.2 with ``scripts/inspect_exr.py``.
    """
    path = Path(path)
    parts = _read_exr_parts(path)

    depth: FloatArray | None = None
    image: FloatArray | None = None
    extras: dict[str, FloatArray] = {}

    for part_name, channels, data in parts:
        qualified = [f"{part_name}.{c}" if part_name else c for c in channels]

        if depth is None:
            idx = _find_channel(qualified, ("depth",), suffixes=(".z", ".v"))
            if idx is None and "depth" in part_name.lower():
                idx = 0
            if idx is not None:
                depth = data[..., idx].astype(float)

        for key, token in (("albedo", "diffuse color"), ("glossy", "glossy direct")):
            if key not in extras:
                rgb = _rgb_channels(qualified, token)
                if rgb:
                    extras[key] = data[..., rgb].mean(axis=2).astype(float)

        if "material_index" not in extras:
            idx = _find_channel(qualified, ("material index", "indexma"))
            if idx is not None:
                extras["material_index"] = data[..., idx].astype(float)

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
    return {"image": image, "depth": depth, **extras}


def _rgb_channels(names: Sequence[str], token: str) -> list[int]:
    """Indices of the R/G/B channels belonging to the pass named ``token``.

    Matched on the qualified name so that ``Diffuse Color`` is not confused with
    ``Combined`` -- both are colour passes with identical channel letters, and
    picking the wrong one substitutes a shading-free albedo map for the rendered
    image, or vice versa. That is the same class of silent substitution ADR-0010
    was written about.
    """
    return [
        i
        for i, name in enumerate(names)
        if token in name.lower() and name.lower().rsplit(".", 1)[-1] in ("r", "g", "b")
    ]


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


def albedo_texture_contrast(albedo: FloatArray, window: int = 7) -> FloatArray:
    """Local standard deviation of albedo over a ``window``-sided box.

    This is the honest measure of "how much matching evidence does this pixel
    have". Measuring texture from the *rendered* image instead would conflate
    albedo variation with shading gradient: under a raking light a perfectly
    constant-albedo surface carries a strong intensity ramp, which looks like
    texture to any statistic computed on the beauty pass but supports matching
    far more weakly.

    Invalid pixels are masked before mixing, per ADR-0002 -- a window straddling
    the frame edge or a non-hit must not average `nan` in as though it were data.

    Parameters
    ----------
    albedo : (H, W) shading-free surface colour, from the Diffuse Color pass.
    window : odd side length in pixels. Match it to the matcher's own window;
        texture contrast is only meaningful relative to the support the matcher
        actually integrates over.

    Returns
    -------
    (H, W) standard deviation in albedo units, ``nan`` where support is too thin.
    """
    if window % 2 == 0:
        raise ValueError(f"window must be odd, got {window}")
    valid = np.isfinite(albedo)
    filled = np.where(valid, albedo, 0.0)
    r = window // 2

    n = boxsum(valid.astype(float), r)
    s = boxsum(filled, r)
    s2 = boxsum(filled * filled, r)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = s / np.maximum(n, 1.0)
        var = s2 / np.maximum(n, 1.0) - mean * mean
        # Catmull of floating-point error: a genuinely uniform patch can land a
        # hair below zero here, and sqrt of that is nan -- which would read as
        # "no support" rather than "no texture", inverting the meaning.
        out = np.sqrt(np.maximum(var, 0.0))
    return np.where(n > 0.5 * (2 * r + 1) ** 2, out, np.nan)


@dataclass(frozen=True)
class AppearanceGroundTruth:
    """Per-pixel surface appearance, straight from the renderer.

    Deliberately a sidecar rather than extra fields on
    :class:`~activestereo.scenes.base.StereoStimulus`: that contract is frozen
    and shared with RDS stimuli, which have no albedo, no specular component and
    no materials. Appearance is a property of rendered scenes only.

    Attributes
    ----------
    albedo : (H, W) surface colour with lighting removed (Diffuse Color pass).
    texture_contrast : (H, W) local albedo std -- see :func:`albedo_texture_contrast`.
    glossy_left, glossy_right : (H, W) specular energy alone (Glossy Direct),
        per eye, each in its own image frame.
    material_index : (H, W) integer material id, the exact condition label.
    """

    albedo: FloatArray
    texture_contrast: FloatArray
    glossy_left: FloatArray
    glossy_right: FloatArray
    material_index: NDArray[np.int_]

    def specular_mismatch(self, disparity: FloatArray) -> FloatArray:
        """Interocular specular disagreement at *corresponding* pixels, in [0, 1].

        This is the brightness-constancy violation, measured rather than assumed.
        A diffuse surface radiates equally toward both eyes, so its glossy energy
        matches after warping and this is ~0. A specular highlight is generated
        at a *different scene point* for each eye, so it does not survive the
        warp and this approaches 1.

        That distinction is the whole reason specularity is worse for stereo than
        texture loss: a textureless region withholds evidence, while a highlight
        supplies evidence for a correspondence that does not exist. ``BlockMatcher``
        assumes brightness constancy unconditionally (its cost is a raw SSD), so it
        has no way to notice.

        Returns ``nan`` where the correspondent falls outside the right image.
        """
        H, W = self.glossy_left.shape
        rows, cols = np.indices((H, W))
        target = cols - np.rint(np.nan_to_num(disparity, nan=0.0)).astype(int)
        ok = (target >= 0) & (target < W) & np.isfinite(disparity)

        warped = np.full((H, W), np.nan)
        warped[ok] = self.glossy_right[rows[ok], target[ok]]
        left = self.glossy_left
        with np.errstate(invalid="ignore", divide="ignore"):
            # Normalised so this is a *fraction* disagreeing rather than an
            # absolute radiance difference, which would simply track brightness.
            return np.abs(left - warped) / (left + warped + 1e-6)


class BlenderRenderScene:
    """A rendered directory, presented as a :class:`Scene`.

    Lets a render flow through anything that already consumes a ``Scene`` --
    ``exp001``'s runner, the integration tests -- without those learning anything
    about EXR layouts.

    Two places where this stretches the ``Scene`` contract, both deliberate and
    neither silent:

    **It ignores ``rng``.** The protocol promises determinism *given* an injected
    generator so that a result pins to a seed. A pre-baked render is stronger than
    that: it is the same pixels every time, whatever the seed. The seed that
    mattered was Cycles' sampling seed, and it was fixed when the file was written.

    **It refuses a mismatched ``rig``.** ``render(rig, rng)`` takes a rig, but the
    geometry here was fixed at render time and is recorded in ``rig.json``. Quietly
    accepting a different one would rescale every depth in the stimulus by the
    ratio of focal lengths and report it as ground truth, so it raises instead.
    """

    def __init__(
        self,
        directory: str | Path,
        depth_is_radial: bool | None = None,
        name: str | None = None,
    ) -> None:
        self.directory = Path(directory)
        meta_path = self.directory / "rig.json"
        if not meta_path.exists():
            raise FileNotFoundError(
                f"missing {meta_path}. A render without its intrinsics cannot be "
                "turned into a stimulus: focal length and baseline set the scale "
                "of every disparity in it."
            )
        self.meta = json.loads(meta_path.read_text())
        chart_path = self.directory / "chart.json"
        self.chart = json.loads(chart_path.read_text()) if chart_path.exists() else None
        self._name = name or f"blender_{self.directory.name}"
        self._rig = rig_from_blender(
            self.meta["resolution_x"],
            self.meta["sensor_width_mm"],
            self.meta["lens_mm"],
            self.meta["interocular"],
            self.meta["convergence_distance"],
        )
        self._depth_is_radial = depth_is_radial
        self._layers: dict[str, dict[str, FloatArray]] = {}

    @property
    def name(self) -> str:
        return self._name

    @property
    def rig(self) -> StereoRig:
        """The rig this render was actually made with."""
        return self._rig

    def _eye(self, which: str) -> dict[str, FloatArray]:
        if which not in self._layers:
            path = self.directory / f"{which}.exr"
            if not path.exists():
                raise FileNotFoundError(
                    f"missing {path}. Both eyes are required: a single depth pass "
                    "cannot express half-occlusion."
                )
            self._layers[which] = read_multilayer_exr(path)
        return self._layers[which]

    def depth_is_radial(self) -> bool:
        """Resolve the depth convention, measuring it where that is possible.

        Precedence: an explicit constructor argument, then ``rig.json``, then --
        for a material-chart render only -- direct measurement against the known
        fronto-parallel backdrop. Raises rather than guessing.

        The guessing is what this replaces. ``rig.json`` writes
        ``depth_is_radial: null`` because the render script genuinely cannot tell,
        and the previous caller did ``bool(meta.get("depth_is_radial"))``, which
        turns "nobody has checked" into "planar, definitely" without a word. An
        uncorrected radial pass looks like a few percent of peripheral depth
        error -- exactly the signature of an ADR-0003 modelling result.
        """
        if self._depth_is_radial is not None:
            return self._depth_is_radial
        recorded = self.meta.get("depth_is_radial")
        if recorded is not None:
            self._depth_is_radial = bool(recorded)
            return self._depth_is_radial

        if self.chart is not None:
            depth = self._eye("left")["depth"]
            index = self._eye("left").get("material_index")
            if index is not None:
                flat = np.where(np.rint(index) == self.chart["index_backdrop"], depth, np.nan)
                verdict = infer_depth_convention(flat)
                if verdict in ("planar", "radial"):
                    self._depth_is_radial = verdict == "radial"
                    return self._depth_is_radial

        raise ValueError(
            f"depth convention for {self.directory} is unknown.\n"
            "Blender's depth pass is radial or planar depending on version and "
            "engine, and an uncorrected radial pass is indistinguishable from a "
            "few percent of peripheral modelling error.\n"
            "Render a fronto-parallel wall, run infer_depth_convention on it, and "
            "record the answer as 'depth_is_radial' in rig.json -- or pass it "
            "explicitly to BlenderRenderScene."
        )

    def render(self, rig: StereoRig, rng: np.random.Generator | None = None) -> StereoStimulus:
        """Return the stimulus. ``rng`` is unused; ``rig`` must match the render."""
        self._check_rig(rig)
        return self.stimulus()

    def _check_rig(self, rig: StereoRig) -> None:
        mine = self._rig
        for field, got, want in (
            ("focal_px", rig.focal_px, mine.focal_px),
            ("baseline", rig.baseline, mine.baseline),
            ("vergence", rig.vergence, mine.vergence),
        ):
            if not np.isclose(got, want, rtol=1e-6, atol=1e-9):
                raise ValueError(
                    f"rig mismatch on {field}: caller passed {got!r}, but this "
                    f"render was made with {want!r} (from {self.directory}/rig.json).\n"
                    "Scaling a rendered disparity field with the wrong rig produces "
                    "metric depth that is wrong by a constant factor and looks "
                    "entirely plausible. Use BlenderRenderScene.rig."
                )

    def stimulus(self) -> StereoStimulus:
        """The stereo pair with ground-truth depth, disparity and occlusion."""
        radial = self.depth_is_radial()
        left, right = self._eye("left"), self._eye("right")

        depth_left = left["depth"]
        depth_right = right["depth"]
        if radial:
            depth_left = radial_to_planar(depth_left, self._rig.focal_px)
            depth_right = radial_to_planar(depth_right, self._rig.focal_px)

        return StereoStimulus(
            left=left["image"],
            right=right["image"],
            depth=depth_left,
            disparity=depth_to_disparity(depth_left, self._rig),
            matched=cross_check_occlusion(depth_left, depth_right, self._rig),
            in_frame=_in_frame(depth_left, self._rig),
            rig=self._rig,
        )

    def appearance(self, window: int = 7) -> AppearanceGroundTruth:
        """Per-pixel appearance ground truth. Requires the render to have the passes."""
        left, right = self._eye("left"), self._eye("right")
        missing = [k for k in ("albedo", "glossy", "material_index") if k not in left]
        if missing:
            raise KeyError(
                f"{self.directory} has no {missing} pass. Re-render with "
                "--scene material-chart, which enables diffuse_color, "
                "glossy_direct and material_index. Without them, 'how textured is "
                "this pixel' can only be guessed from the beauty pass, which "
                "confuses albedo texture with shading gradient."
            )
        albedo = left["albedo"]
        return AppearanceGroundTruth(
            albedo=albedo,
            texture_contrast=albedo_texture_contrast(albedo, window=window),
            glossy_left=left["glossy"],
            glossy_right=right["glossy"],
            material_index=np.rint(left["material_index"]).astype(int),
        )

    def conditions(self) -> dict[int, dict[str, Any]]:
        """Material index -> its condition, from ``chart.json``."""
        if self.chart is None:
            raise FileNotFoundError(
                f"no chart.json in {self.directory}; material_index has no labels. "
                "Only --scene material-chart writes one."
            )
        return {m["material_index"]: m for m in self.chart["materials"]}


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
