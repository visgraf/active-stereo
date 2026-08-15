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
    """

    left: FloatArray
    right: FloatArray
    depth: FloatArray
    disparity: FloatArray
    matched: NDArray[np.bool_]
    in_frame: NDArray[np.bool_]
    rig: StereoRig

    def __post_init__(self) -> None:
        shapes = {
            "left": self.left.shape,
            "right": self.right.shape,
            "depth": self.depth.shape,
            "disparity": self.disparity.shape,
            "matched": self.matched.shape,
            "in_frame": self.in_frame.shape,
        }
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
        """Half-occlusion: in frame, but hidden by a nearer surface."""
        return self.in_frame & ~self.matched

    @property
    def out_of_frame(self) -> NDArray[np.bool_]:
        """Correspondent lies outside the right image. A rig limit, not geometry."""
        return ~self.in_frame

    @property
    def occlusion_fraction(self) -> float:
        """Fraction of left pixels that are genuinely half-occluded."""
        return float(self.occluded.mean())

    @property
    def scorable(self) -> NDArray[np.bool_]:
        """Pixels a matcher can fairly be judged on: in frame and matchable."""
        return self.matched


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
