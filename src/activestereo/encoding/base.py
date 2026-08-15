"""Interface for L2 disparity encoders."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from activestereo.types import FloatArray


@runtime_checkable
class DisparityEncoder(Protocol):
    """Maps a stereo pair to a population response over a disparity bank.

    Implementations are the neural front end: complex-cell energy, phase-shift or
    position-shift banks, learned encoders. They produce *evidence*, never a
    decision -- the argmax over the bank belongs to L3.
    """

    @property
    def disparities(self) -> FloatArray:
        """Disparity tuning centres of the bank, pixels, shape (K,)."""
        ...

    def encode(self, left: FloatArray, right: FloatArray) -> FloatArray:
        """Return the response volume, shape (K, H, W), non-negative.

        Invalid pixels (outside the overlap, occluded) are ``nan`` in every band.
        """
        ...
