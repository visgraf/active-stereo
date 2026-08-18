"""The stimulus contract shared by synthetic and rendered scenes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

from activestereo.types import FloatArray, StereoRig


@dataclass(frozen=True)
class StereoStimulus:
    """A stereo pair with ground truth.

    Attributes
    ----------
    left, right : FloatArray
        Rectified images, shape (H, W), intensities in [0, 1].
    depth : FloatArray
        Ground-truth depth in **metres**, cyclopean frame, aligned with ``left``.
    disparity : FloatArray
        Ground-truth disparity in **pixels**, left-image convention, positive =
        crossed. Redundant with ``depth`` given ``rig``, but carried explicitly
        because RDS synthesis quantises it and the quantised value is the honest
        target for a matcher.
    matched : NDArray[bool]
        True where the left pixel has a corresponding right pixel.
    in_frame : NDArray[bool]
        True where the left pixel's correspondent falls inside the right image.

        These two masks are deliberately separate. A pixel can fail to match for
        two unrelated reasons: a nearer surface hid its partner (**half-occlusion**,
        a fact about scene geometry) or its partner fell outside the sensor
        (**out of frame**, a fact about the rig's field of view). Conflating them
        puts a band of border pixels into every occlusion statistic and makes a
        smooth, unoccluded surface look occluded. Use :attr:`occluded` for the
        geometric quantity.
    rig : StereoRig
        The rig that produced the pair.
    known : NDArray[bool] | None
        True where ground truth exists at all. ``None`` means "everywhere",
        which is the honest answer for a synthesised stimulus: an RDS or a render
        knows the depth of every pixel because it built them.

        Measured ground truth does not. A structured-light scanner leaves holes
        where it saw no return, and Middlebury encodes those as ``inf``
        (ADR-0011). That is a third pixel class, and it is categorically unlike
        the other two: ``matched`` and ``in_frame`` are claims about *the scene*,
        while this is a claim about *our knowledge of it*. Folding it into either
        one is the same mistake those two masks were separated to avoid --
        charging scanner holes to occlusion would inflate the one statistic
        exp001 turns on.
    """

    left: FloatArray
    right: FloatArray
    depth: FloatArray
    disparity: FloatArray
    matched: NDArray[np.bool_]
    in_frame: NDArray[np.bool_]
    rig: StereoRig
    known: NDArray[np.bool_] | None = None

    def __post_init__(self) -> None:
        shapes = {
            "left": self.left.shape,
            "right": self.right.shape,
            "depth": self.depth.shape,
            "disparity": self.disparity.shape,
            "matched": self.matched.shape,
            "in_frame": self.in_frame.shape,
        }
        if self.known is not None:
            shapes["known"] = self.known.shape
        if len(set(shapes.values())) != 1:
            raise ValueError(f"stimulus arrays disagree in shape: {shapes}")

    @property
    def shape(self) -> tuple[int, int]:
        # ndarray.shape is tuple[int, ...]; unpacking narrows it to a 2-tuple,
        # which __post_init__ has already guaranteed.
        rows, cols = self.left.shape
        return rows, cols

    @property
    def occluded(self) -> NDArray[np.bool_]:
        """Half-occlusion: in frame, but hidden by a nearer surface.

        Excludes pixels with no ground truth. Both this and :attr:`out_of_frame`
        are assertions about the scene, and a pixel we know nothing about
        supports neither: without a true disparity there is no correspondent to
        locate, so it can be shown to be neither occluded nor off-sensor. The
        three categories therefore no longer partition the frame -- what is left
        over is ``~known``, and :attr:`unknown_fraction` reports it.
        """
        out = self.in_frame & ~self.matched
        return out if self.known is None else (out & self.known)

    @property
    def out_of_frame(self) -> NDArray[np.bool_]:
        """Correspondent lies outside the right image. A rig limit, not geometry.

        Excludes pixels with no ground truth -- see :attr:`occluded`. Leaving them
        in would charge every scanner hole to the field-of-view statistic.
        """
        out = ~self.in_frame
        return out if self.known is None else (out & self.known)

    @property
    def occlusion_fraction(self) -> float:
        """Fraction of left pixels that are genuinely half-occluded."""
        return float(self.occluded.mean())

    @property
    def unknown_fraction(self) -> float:
        """Fraction of left pixels with no ground truth. Zero for a synthetic scene."""
        return 0.0 if self.known is None else float((~self.known).mean())

    @property
    def scorable(self) -> NDArray[np.bool_]:
        """Pixels a matcher can fairly be judged on: matchable, and truth exists.

        Scoring a matcher against a pixel whose true disparity nobody knows
        measures the scanner, not the matcher. Every existing caller gets this
        narrowing for free, because a synthetic stimulus leaves ``known`` at
        ``None`` and the mask is unchanged.
        """
        return self.matched if self.known is None else (self.matched & self.known)


def cross_check_disparity(
    disparity_left: FloatArray,
    disparity_right: FloatArray,
    tolerance: float = 1.0,
) -> NDArray[np.bool_]:
    """Recover ``matched`` from two ground-truth disparity fields.

    A left pixel is matched when the right field, sampled at the correspondent
    this pixel predicts, agrees within ``tolerance`` pixels. Both fields are
    ground truth, so this is a definition of half-occlusion rather than an
    estimate of it.

    This is the disparity-native core. :func:`scenes.blender.cross_check_occlusion`
    wraps it for callers holding depth maps instead.

    It is also, exactly, the algorithm Middlebury use to generate the
    ``mask0nocc.png`` they do not ship (``MiddEval3-SDK/code/computemask.cpp``),
    down to the ``round`` and the 1.0 px default -- with one deliberate
    difference: they leave an out-of-bounds correspondent labelled *occluded*,
    pooling a sensor limit with a fact about the scene. Here that pixel is simply
    unmatched, and :attr:`StereoStimulus.in_frame` carries the distinction.

    Parameters
    ----------
    disparity_left, disparity_right : (H, W) arrays, pixels, left-image
        convention, positive = crossed. Non-finite entries are unmatched.
    tolerance : pixels.
    """
    d = np.asarray(disparity_left, dtype=float)
    other = np.asarray(disparity_right, dtype=float)
    if d.shape != other.shape:
        raise ValueError(f"disparity fields disagree in shape: {d.shape} vs {other.shape}")

    H, W = d.shape
    rows, cols = np.indices((H, W))

    # Round the *target coordinate*, not the disparity, and round halves away
    # from zero. Both details are load-bearing only on exact-half disparities,
    # which continuous ground truth never produces and a quantised scanner
    # produces constantly.
    #
    #   x - rint(d)  != rint(x - d)  on a tie: with d = 131.5 and x = 2395,
    #   rint(131.5) = 132 gives 2263, while rint(2263.5) = 2264. Which one wins
    #   depends on the parity of x, which is not a property of the scene.
    #
    # np.rint is half-to-even; C's round() -- and therefore Middlebury's
    # computemask.cpp -- is half-away-from-zero. Matching it is what lets this
    # function reproduce their mask exactly rather than nearly.
    offset = np.nan_to_num(d, nan=0.0, posinf=0.0, neginf=0.0)
    exact = cols - offset
    target = np.trunc(exact + np.copysign(0.5, exact)).astype(int)
    in_bounds = (target >= 0) & (target < W) & np.isfinite(d)

    matched = np.zeros((H, W), dtype=bool)
    partner = other[rows[in_bounds], target[in_bounds]]
    matched[in_bounds] = np.abs(partner - d[in_bounds]) <= tolerance
    return matched


@runtime_checkable
class Scene(Protocol):
    """Produces a :class:`StereoStimulus`.

    Implementations must be deterministic given the injected ``rng``: this is
    what lets an experiment pin a result to a seed (CLAUDE.md §3).
    """

    @property
    def name(self) -> str:
        """Short identifier used in run manifests and result paths."""
        ...

    def render(self, rig: StereoRig, rng: np.random.Generator) -> StereoStimulus:
        """Generate a stereo pair with ground truth for the given rig."""
        ...
