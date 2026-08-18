"""Loader for the Middlebury 2014 stereo datasets.

The first stimulus family in this repo whose ground truth we did not author. An
RDS and a Blender render are inversions of our own generative model; these are
photographs of real objects with structured-light ground truth, and they are what
makes the transfer question askable at all (ADR-0012).

Everything specific to Middlebury's conventions lives here, because none of them
are documented on their public pages and every one of them fails silently:

**Row order.** PFM stores scanlines bottom-up. :func:`read_pfm` flips. Skipping
the flip yields a vertically mirrored ground truth whose statistics look entirely
normal.

**Unknown ground truth.** The scanner leaves holes, encoded as ``inf``. These are
neither occluded nor out of frame; see ADR-0011 and ``StereoStimulus.known``.

**Calibration.** ``doffs`` -- the x-offset between the two principal points --
is algebraically identical to this framework's vergence term. Middlebury write
``Z = baseline * f / (d + doffs)``; L1 writes ``d = f b (1/Z - 1/Zf)``. Equating
them gives ``doffs = f b / Zf``, hence ``vergence = 2 arctan(doffs / 2f)``. The
mapping is exact, not an approximation, and it is a pleasing external
confirmation of the off-axis choice in ADR-0007.

Note what that identity does *not* buy. Because the two formulas are the same
formula, a test showing that ``disparity_to_depth`` reproduces
``b f / (d + doffs)`` validates the translation in :func:`rig_from_calib` and
nothing about the physics. Depth here is therefore computed longhand from
Middlebury's own expression rather than by calling L1: ADR-0006 requires that the
stimulus and the estimator not share a code path.

**No occlusion mask.** ``mask0nocc.png`` is not distributed -- it is generated
locally by the Middlebury SDK, whose generator is a left-right cross-check at
1.0 px. We compute ``matched`` with :func:`scenes.base.cross_check_disparity`,
which is the same algorithm, so this reproduces their mask rather than
approximating it. Their version folds out-of-frame pixels into *occluded*; we keep
``in_frame`` separate, per ``scenes/base.py``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from activestereo.scenes.base import StereoStimulus, cross_check_disparity
from activestereo.types import FloatArray, StereoRig

#: Right-image variants. Geometry and ground truth are identical across all
#: three; only the photometry differs, which makes them a brightness-constancy
#: experiment that ships with the corpus.
RIGHT_VARIANTS = {
    "im1": "im1.png",  # same exposure and lighting as im0
    "im1E": "im1E.png",  # different exposure
    "im1L": "im1L.png",  # different lighting
}


def pfm_header(path: str | Path) -> tuple[str, int, int, float]:
    """Return ``(magic, width, height, scale)`` without reading the pixels.

    ``scale`` is negative for little-endian data, which is the only thing its
    sign is used for; Middlebury write ``-0.003922`` and the magnitude carries no
    meaning for disparity.
    """
    with Path(path).open("rb") as f:
        magic = _pfm_token(f)
        if magic not in ("Pf", "PF"):
            raise ValueError(f"{path}: not a PFM file (magic {magic!r})")
        width = int(_pfm_token(f))
        height = int(_pfm_token(f))
        scale = float(_pfm_token(f))
    return magic, width, height, scale


def _pfm_token(f: Any) -> str:
    """Read one whitespace-delimited header token, skipping ``#`` comments."""
    chars: list[bytes] = []
    while True:
        c = f.read(1)
        if c == b"":
            raise ValueError("truncated PFM header")
        if c == b"#":
            while f.read(1) not in (b"\n", b""):
                pass
            continue
        if c.isspace():
            if chars:
                return b"".join(chars).decode("ascii")
            continue
        chars.append(c)


def read_pfm(path: str | Path) -> FloatArray:
    """Read a single-channel PFM as ``float64``, top-down.

    Returns
    -------
    (H, W) array. ``inf`` marks unknown ground truth and is deliberately
    preserved rather than converted to ``nan``: ``inf`` is what Middlebury wrote,
    and the conversion to this framework's ``nan`` convention belongs to
    :class:`MiddleburyScene`, where it is visible, not buried in a file reader.
    """
    path = Path(path)
    magic, width, height, scale = pfm_header(path)
    if magic == "PF":
        raise ValueError(f"{path}: colour PFM; disparity should be single-channel 'Pf'")

    with path.open("rb") as f:
        # Re-walk the header so the data offset is whatever the parser consumed,
        # rather than an assumed three newlines.
        for _ in range(4):
            _pfm_token(f)
        raw = f.read(width * height * 4)
    if len(raw) != width * height * 4:
        raise ValueError(
            f"{path}: expected {width * height * 4} bytes of pixel data, got {len(raw)}. "
            "Truncated download?"
        )

    dtype = np.dtype("<f4" if scale < 0 else ">f4")
    data = np.frombuffer(raw, dtype=dtype).reshape(height, width)
    # PFM scanlines run bottom-up. This flip is the whole reason the row-order
    # check exists in scripts/inspect_middlebury.py.
    return np.asarray(data[::-1], dtype=float)


def read_calib(path: str | Path) -> dict[str, Any]:
    """Parse ``calib.txt`` into a flat dict.

    Raises rather than defaulting on the three fields that set the scale of every
    depth in the scene. A missing ``doffs`` silently defaulted to zero would move
    the horopter to infinity and bias every depth by a constant factor that looks
    completely plausible.
    """
    path = Path(path)
    raw: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            raw[key.strip()] = value.strip()

    out: dict[str, Any] = {}
    for key in ("cam0", "cam1"):
        if key not in raw:
            raise ValueError(f"{path}: missing {key}")
        numbers = [float(t) for t in re.findall(r"-?\d+\.?\d*(?:[eE][-+]?\d+)?", raw[key])]
        if len(numbers) != 9:
            raise ValueError(f"{path}: {key} is not a 3x3 matrix: {raw[key]!r}")
        out[f"{key}_f"] = numbers[0]
        out[f"{key}_cx"] = numbers[2]
        out[f"{key}_cy"] = numbers[5]

    if not np.isclose(out["cam0_f"], out["cam1_f"], rtol=1e-9):
        raise ValueError(
            f"{path}: the two cameras have different focal lengths "
            f"({out['cam0_f']} vs {out['cam1_f']}). StereoRig models one focal "
            "length for the pair; this scene is not rectified as expected."
        )
    out["f"] = out["cam0_f"]
    out["cx"] = out["cam0_cx"]
    out["cy"] = out["cam0_cy"]

    for key in ("doffs", "baseline"):
        if key not in raw:
            raise ValueError(
                f"{path}: missing {key}. Without it the metric scale of every "
                "depth in this scene is unknown, and a default would be wrong by "
                "a constant factor that looks entirely plausible."
            )
        out[key] = float(raw[key])

    for key in ("width", "height", "ndisp", "isint", "vmin", "vmax"):
        if key in raw:
            out[key] = int(float(raw[key]))
    for key in ("dyavg", "dymax"):
        if key in raw:
            out[key] = float(raw[key])

    # cx1 - cx0 should reproduce doffs. It is the one internal consistency check
    # the file affords, and it is free.
    implied = out["cam1_cx"] - out["cam0_cx"]
    if not np.isclose(implied, out["doffs"], atol=1e-3):
        raise ValueError(
            f"{path}: doffs={out['doffs']} disagrees with cx1-cx0={implied:.4f}. "
            "One of them is wrong and the depth scale depends on both."
        )
    return out


def rig_from_calib(calib: dict[str, Any]) -> StereoRig:
    """Translate a parsed ``calib.txt`` into a :class:`StereoRig`.

    The whole of the mapping:

    ==================  =======================================================
    ``f``               ``focal_px``, pixels, unchanged
    ``baseline``        ``baseline / 1000``, **mm -> m** at the I/O boundary
    ``cy``, ``cx``      ``principal_point = (row, col)`` -- *not* ``(x, y)``
    ``doffs``           ``vergence = 2 arctan(doffs / 2f)``
    ==================  =======================================================

    ``doffs`` and ``f`` are both in pixels, so the vergence is a pure ratio and
    is therefore **invariant under downsampling** -- see
    :meth:`MiddleburyScene.downsample`.
    """
    f = float(calib["f"])
    doffs = float(calib["doffs"])
    if doffs < 0:
        raise ValueError(
            f"negative doffs ({doffs}) implies a diverged rig, i.e. a fixation "
            "point behind the observer. StereoRig has no representation for that."
        )
    return StereoRig(
        baseline=float(calib["baseline"]) / 1000.0,
        focal_px=f,
        principal_point=(float(calib["cy"]), float(calib["cx"])),
        vergence=2.0 * float(np.arctan(doffs / (2.0 * f))),
    )


def depth_from_disparity(disparity: FloatArray, calib: dict[str, Any]) -> FloatArray:
    """Middlebury's ``Z = baseline * f / (d + doffs)``, in **metres**.

    Written longhand rather than delegating to ``geometry.disparity_to_depth``.
    The two are algebraically identical given :func:`rig_from_calib`, and that is
    exactly why the stimulus must not call the estimator's version: ADR-0006 --
    if the ground truth came out of the code path being evaluated, agreeing with
    it proves nothing.
    """
    d = np.asarray(disparity, dtype=float)
    denom = d + float(calib["doffs"])
    with np.errstate(invalid="ignore", divide="ignore"):
        Z_mm = np.where(denom > 0, float(calib["f"]) * float(calib["baseline"]) / denom, np.nan)
    return np.asarray(np.where(np.isfinite(Z_mm), Z_mm / 1000.0, np.nan), dtype=float)


def _in_frame(disparity: FloatArray, width: int) -> NDArray[np.bool_]:
    """Whether each left pixel's correspondent lands inside the right image.

    Derived from ground-truth disparity rather than read from a mask, because
    Middlebury's own mask folds this into "occluded" and ``scenes/base.py`` keeps
    the two apart. Non-finite disparity is not in frame *and* not out of frame --
    it is unknown, and ``StereoStimulus.out_of_frame`` masks it out via ``known``.
    """
    d = np.asarray(disparity, dtype=float)
    _, cols = np.indices(d.shape)
    target = cols - np.rint(np.nan_to_num(d, nan=0.0, posinf=0.0, neginf=0.0)).astype(int)
    return np.asarray((target >= 0) & (target < width) & np.isfinite(d))


def _block_mean(a: FloatArray, k: int) -> FloatArray:
    """Average over ``k x k`` blocks, masking invalid pixels before mixing.

    The right operation for an *image*: downsampling is a low-pass filter, and
    skipping the antialiasing aliases fine texture into noise -- which is
    precisely the signal exp003 found decisive. Masked per ADR-0002.
    """
    a = np.asarray(a, dtype=float)
    H, W = (s - s % k for s in a.shape)
    valid = np.isfinite(a[:H, :W])
    filled = np.where(valid, a[:H, :W], 0.0)
    shape = (H // k, k, W // k, k)
    total = filled.reshape(shape).sum(axis=(1, 3))
    count = valid.reshape(shape).sum(axis=(1, 3))
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.asarray(np.where(count > 0, total / count, np.nan), dtype=float)


def _decimate(a: NDArray[Any], k: int) -> NDArray[Any]:
    """Point-sample the centre of each ``k x k`` block.

    Deliberately *not* an average, and the asymmetry with :func:`_block_mean` is
    the point. Averaging disparity across a depth discontinuity invents a surface
    at the mean depth that exists nowhere in the scene, and edges are where every
    occlusion statistic lives.

    For even ``k`` the block centre falls between pixels, leaving a half-pixel
    offset relative to the image block mean. Small -- it costs ``0.5 * gradient``
    of disparity -- but real, and it is why odd factors are preferred.
    """
    H, W = (s - s % k for s in a.shape[:2])
    off = (k - 1) // 2
    return np.asarray(a[off:H:k, off:W:k])


class MiddleburyScene:
    """A Middlebury 2014 scene directory, presented as a :class:`Scene`.

    Mirrors :class:`~activestereo.scenes.blender.BlenderRenderScene`, including
    both places where a pre-baked stimulus stretches the ``Scene`` contract:

    **It ignores ``rng``.** The protocol promises determinism *given* an injected
    generator. A photograph is stronger than that -- it is the same pixels every
    time, whatever the seed.

    **It refuses a mismatched ``rig``.** The geometry was fixed by a physical
    camera and is recorded in ``calib.txt``. Quietly accepting a different rig
    would rescale every ground-truth depth and report it as measured.

    Parameters
    ----------
    directory : a ``<Scene>-perfect`` directory.
    downsample : integer factor. ``1`` is full resolution -- 2880x1988 with
        ``ndisp`` up to 800, which no matcher in ``inference/`` will fit in
        memory. Odd factors avoid the half-pixel sampling offset described in
        :func:`_decimate`.
    tolerance : cross-check threshold in **full-resolution** pixels.
    """

    def __init__(
        self,
        directory: str | Path,
        downsample: int = 3,
        tolerance: float = 1.0,
        name: str | None = None,
    ) -> None:
        self.directory = Path(directory)
        calib_path = self.directory / "calib.txt"
        if not calib_path.exists():
            raise FileNotFoundError(
                f"missing {calib_path}. A scene without its calibration cannot be "
                "turned into a stimulus: focal length, baseline and doffs set the "
                "metric scale of every depth in it."
            )
        if downsample < 1:
            raise ValueError(f"downsample must be >= 1, got {downsample}")

        self.calib = read_calib(calib_path)
        self.downsample = int(downsample)
        self.tolerance = float(tolerance)
        self._name = name or f"middlebury_{self.directory.name}"

        if self.calib.get("dymax", 0.0) > 0.0:
            raise ValueError(
                f"{self.directory} has dymax={self.calib['dymax']} px of vertical "
                "disparity (an '-imperfect' scene). Every matcher in inference/ "
                "assumes epipolar lines are image rows, unconditionally. Use the "
                "'-perfect' variant."
            )

    @property
    def name(self) -> str:
        return self._name

    @property
    def rig(self) -> StereoRig:
        """The rig this scene was actually captured with, at the working scale.

        ``focal_px`` and the principal point scale with the downsampling factor;
        ``baseline`` is metric and does not. ``vergence`` is a ratio of two pixel
        quantities and is therefore invariant -- which is the check that the
        downsampling is self-consistent, since metric depth must not move when
        only the sampling grid changes.
        """
        k = self.downsample
        scaled = dict(self.calib)
        scaled["f"] = self.calib["f"] / k
        scaled["doffs"] = self.calib["doffs"] / k
        scaled["cx"] = self.calib["cx"] / k
        scaled["cy"] = self.calib["cy"] / k
        return rig_from_calib(scaled)

    @property
    def ndisp(self) -> int:
        """Conservative search bound at the working scale.

        Pass this to a matcher as ``max_disparity``, **not** ``ndisp - 1``:
        ``BlockMatcher`` rejects a winner at the last index of its search range,
        so an off-by-one here silently discards every true maximum-disparity pixel.
        """
        return int(np.ceil(self.calib["ndisp"] / self.downsample))

    def _image(self, filename: str) -> FloatArray:
        path = self.directory / filename
        if not path.exists():
            raise FileNotFoundError(f"missing image: {path}")

        import cv2  # optional 'cv' extra; see scenes.blender._read_gray

        img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise OSError(f"could not decode image: {path}")
        # Rec. 601 luminance, matching scenes.blender._read_gray exactly. One
        # luminance convention in this repo, not one per loader.
        return np.asarray(img, dtype=float) / 255.0

    def stimulus(self, right_variant: str = "im1") -> StereoStimulus:
        """Build the stimulus. ``right_variant`` selects the photometry.

        ``im1E`` (different exposure) and ``im1L`` (different lighting) share
        geometry and ground truth with ``im1`` exactly, so switching between them
        varies brightness constancy and nothing else.
        """
        if right_variant not in RIGHT_VARIANTS:
            raise ValueError(
                f"unknown right variant {right_variant!r}; expected one of "
                f"{sorted(RIGHT_VARIANTS)}"
            )
        k = self.downsample
        disp0 = read_pfm(self.directory / "disp0.pfm")
        disp1 = read_pfm(self.directory / "disp1.pfm")

        # Masks are derived at FULL resolution and then decimated. The 1.0 px
        # cross-check tolerance is defined at full resolution; applying it after
        # downsampling would loosen it by a factor of k and quietly shrink the
        # occluded set.
        known_full = np.isfinite(disp0)
        matched_full = cross_check_disparity(disp0, disp1, tolerance=self.tolerance)
        in_frame_full = _in_frame(disp0, disp0.shape[1])

        # inf is Middlebury's marker; nan is this framework's (CLAUDE.md §3).
        # The conversion happens here, once, where it is visible.
        disp0 = np.where(known_full, disp0, np.nan)

        left = self._image("im0.png")
        right = self._image(RIGHT_VARIANTS[right_variant])
        depth_full = depth_from_disparity(disp0, self.calib)

        # Both helpers are the identity at k = 1, so there is no special case:
        # a branch here would be a second code path exercised only at full
        # resolution, which is the configuration least often run.
        known = _decimate(known_full, k)
        matched = _decimate(matched_full, k)
        in_frame = _decimate(in_frame_full, k)

        return StereoStimulus(
            left=_block_mean(left, k),
            right=_block_mean(right, k),
            depth=_decimate(depth_full, k),
            disparity=_decimate(disp0, k) / k,
            matched=np.asarray(matched, dtype=bool),
            in_frame=np.asarray(in_frame, dtype=bool),
            rig=self.rig,
            known=np.asarray(known, dtype=bool),
        )

    def render(self, rig: StereoRig, rng: np.random.Generator | None = None) -> StereoStimulus:
        """Return the stimulus. ``rng`` is unused; ``rig`` must match the capture."""
        self._check_rig(rig)
        return self.stimulus()

    def _check_rig(self, rig: StereoRig) -> None:
        mine = self.rig
        for field, got, want in (
            ("focal_px", rig.focal_px, mine.focal_px),
            ("baseline", rig.baseline, mine.baseline),
            ("vergence", rig.vergence, mine.vergence),
        ):
            if not np.isclose(got, want, rtol=1e-6, atol=1e-9):
                raise ValueError(
                    f"rig mismatch on {field}: caller passed {got!r}, but "
                    f"{self.directory.name} was captured with {want!r} "
                    f"(from calib.txt, downsample={self.downsample}).\n"
                    "Scaling a measured disparity field with the wrong rig gives "
                    "metric depth that is wrong by a constant factor and looks "
                    "entirely plausible. Use MiddleburyScene.rig."
                )

    def noise_floor(self) -> float:
        """Median ground-truth disparity uncertainty, pixels, at the working scale.

        From ``disp0-sd.pfm``. A residual smaller than this is the scanner, not
        the matcher, and reporting it as a result would be reporting noise.
        """
        path = self.directory / "disp0-sd.pfm"
        if not path.exists():
            raise FileNotFoundError(
                f"missing {path}; only '-perfect' scenes carry sample statistics."
            )
        sd = read_pfm(path)
        finite = np.isfinite(sd)
        if not finite.any():
            return float("nan")
        return float(np.median(sd[finite])) / self.downsample
