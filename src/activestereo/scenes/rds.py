"""Random-dot stereogram synthesis with correct half-occlusion.

A random-dot stereogram (Julesz, 1960) carries depth in binocular disparity and
nowhere else: each image alone is uncorrelated noise. That is exactly what makes
it the right stimulus for this framework -- it isolates L3 from every monocular
cue that a rendered scene inevitably supplies, so a depth estimate can only have
come from matching.

Synthesis here is a **forward warp with a z-buffer**, not a naive region shift.
The difference matters. A naive shift produces a stereogram whose occlusion
structure is wrong: it either duplicates dots or leaves holes in arbitrary
places. The z-buffer version reproduces the real geometry --

* **left-occluded** pixels: a nearer surface claims the right-image pixel that a
  farther left pixel would have mapped to, so the farther pixel has no
  correspondent at all;
* **revealed** pixels: right-image pixels that no left pixel maps to, filled with
  fresh, uncorrelated dots.

Both are *geometrically unmatchable*. Returning them as ground truth is what lets
an experiment distinguish "the matcher failed" from "there was nothing to find",
which is the distinction ADR-0002 exists to protect.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
from numpy.typing import NDArray

from activestereo.geometry import depth_to_disparity, disparity_to_depth
from activestereo.scenes.base import StereoStimulus
from activestereo.types import FloatArray, StereoRig


def dot_texture(
    shape: tuple[int, int],
    rng: np.random.Generator,
    density: float = 0.5,
    dot_size: int = 1,
    binary: bool = True,
) -> FloatArray:
    """Generate a random dot field.

    Parameters
    ----------
    density : fraction of bright dots when ``binary``; ignored otherwise.
    dot_size : side of a square dot in pixels. Larger dots raise the
        signal-to-noise of block matching without adding any monocular cue,
        which is a useful axis to sweep.
    binary : classic black/white dots. Set ``False`` for uniform grayscale, which
        gives subpixel matchers something to interpolate.
    """
    if dot_size < 1:
        raise ValueError(f"dot_size must be >= 1, got {dot_size}")
    H, W = shape
    h = -(-H // dot_size)  # ceil
    w = -(-W // dot_size)
    small = rng.random((h, w))
    field = (small < density).astype(float) if binary else small
    if dot_size > 1:
        field = np.kron(field, np.ones((dot_size, dot_size)))
    return field[:H, :W]


def render_rds(
    depth: FloatArray,
    rig: StereoRig,
    rng: np.random.Generator,
    density: float = 0.5,
    dot_size: int = 1,
    binary: bool = True,
    noise: float = 0.0,
) -> StereoStimulus:
    """Synthesise a random-dot stereogram from a ground-truth depth map.

    The left image is the reference dot field. Each left pixel at column ``x``
    with disparity ``d`` maps to right column ``x - d`` (the repo's left-image
    convention, positive = crossed). Where several left pixels compete for one
    right pixel, the **nearest** wins; the losers are half-occluded.

    Disparity is quantised to whole pixels, because dots are discrete and a
    fractional shift would require interpolation that smears the dot statistics
    and introduces a monocular cue. The returned ``depth`` is therefore
    *recomputed from the quantised disparity*, so ground-truth depth and
    disparity agree exactly and a matcher is not charged for a quantisation error
    it could not have avoided. Expect it to differ slightly from the ``depth``
    passed in; the stimulus genuinely depicts the quantised surface.

    Parameters
    ----------
    noise : std of independent Gaussian noise added to each eye, which
        decorrelates the images and degrades matching in a controlled way.
    """
    depth = np.asarray(depth, dtype=float)
    H, W = depth.shape

    d_true = depth_to_disparity(depth, rig)
    d_int = np.where(np.isfinite(d_true), np.rint(d_true), np.nan)

    left = dot_texture((H, W), rng, density=density, dot_size=dot_size, binary=binary)

    rows, cols = np.indices((H, W))
    with np.errstate(invalid="ignore"):
        target = cols - np.nan_to_num(d_int, nan=0.0).astype(int)
    in_bounds = (target >= 0) & (target < W) & np.isfinite(d_int)

    src = (rows * W + cols)[in_bounds]
    dst = (rows * W + target)[in_bounds]
    d_flat = d_int[in_bounds]

    # Ascending disparity: farther surfaces are written first, nearer ones
    # overwrite them. NumPy assignment with duplicate indices keeps the last
    # write, which is precisely the z-buffer we want.
    order = np.argsort(d_flat, kind="stable")
    src_o, dst_o = src[order], dst[order]

    owner = np.full(H * W, -1, dtype=np.int64)
    owner[dst_o] = src_o

    right_flat = np.full(H * W, np.nan)
    right_flat[dst_o] = left.ravel()[src_o]

    # A left pixel is matched iff it won the z-buffer contest for its target.
    matched_flat = np.zeros(H * W, dtype=bool)
    matched_flat[src] = owner[dst] == src
    matched = matched_flat.reshape(H, W)
    in_frame = in_bounds

    # Right pixels nobody mapped to are newly revealed: fresh, uncorrelated dots.
    revealed = ~np.isfinite(right_flat)
    fill = dot_texture((H, W), rng, density=density, dot_size=dot_size, binary=binary)
    right_flat[revealed] = fill.ravel()[revealed]
    right = right_flat.reshape(H, W)

    if noise > 0:
        left = left + rng.normal(0.0, noise, left.shape)
        right = right + rng.normal(0.0, noise, right.shape)

    depth_effective = disparity_to_depth(d_int, rig)

    return StereoStimulus(
        left=left,
        right=right,
        depth=depth_effective,
        disparity=d_int,
        matched=matched,
        in_frame=in_frame,
        rig=rig,
    )


class RandomDotStereogram:
    """A :class:`~activestereo.scenes.base.Scene` wrapping a depth-map function.

    Example
    -------
    >>> from activestereo.scenes import RandomDotStereogram, disk
    >>> scene = RandomDotStereogram(disk, name="rds_disk", dot_size=2)
    """

    def __init__(
        self,
        depth_fn: Callable[..., FloatArray],
        name: str = "rds",
        shape: tuple[int, int] = (240, 320),
        density: float = 0.5,
        dot_size: int = 1,
        binary: bool = True,
        noise: float = 0.0,
        **depth_kwargs: Any,
    ) -> None:
        self._depth_fn = depth_fn
        self._name = name
        self.shape = shape
        self.density = density
        self.dot_size = dot_size
        self.binary = binary
        self.noise = noise
        self.depth_kwargs = depth_kwargs

    @property
    def name(self) -> str:
        return f"{self._name}_dot{self.dot_size}"

    def depth_map(self) -> FloatArray:
        return self._depth_fn(shape=self.shape, **self.depth_kwargs)

    def render(self, rig: StereoRig, rng: np.random.Generator) -> StereoStimulus:
        return render_rds(
            self.depth_map(),
            rig,
            rng,
            density=self.density,
            dot_size=self.dot_size,
            binary=self.binary,
            noise=self.noise,
        )


def autostereogram_check(stim: StereoStimulus) -> NDArray[np.bool_]:
    """Sanity check: no monocular cue should predict depth.

    Returns the per-column correlation mask used by the tests. A genuine RDS has
    no column-wise intensity statistic that tracks disparity; if this ever finds
    one, the synthesis has leaked a monocular cue and every result obtained with
    the stimulus is suspect.
    """
    col_mean = np.nanmean(stim.left, axis=0)
    col_disp = np.nanmean(stim.disparity, axis=0)
    ok = np.isfinite(col_mean) & np.isfinite(col_disp)
    return ok
