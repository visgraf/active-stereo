"""Interface for L3 disparity matchers.

Keeping matchers behind a Protocol is what makes them swappable, which is the
property the framework needs in order to compare inference strategies (block
matching, SGBM, MRF/BP, learned) under an otherwise identical pipeline.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from activestereo.types import Estimate, FloatArray


@runtime_checkable
class DisparityMatcher(Protocol):
    """Estimates a disparity field with per-pixel uncertainty.

    Contract
    --------
    - Returns an :class:`Estimate` whose ``value`` is disparity in **pixels**
      (left-image convention, positive = crossed) and whose ``variance`` is in
      **pixels squared**.
    - Unmatched, occluded, or out-of-range pixels are ``nan`` in *both* arrays.
      Never 0, never -1 (CLAUDE.md §3).
    - Output shape equals the shape of ``left``.
    - Deterministic given the same inputs.
    """

    @property
    def name(self) -> str:
        """Short identifier used in run manifests and result paths."""
        ...

    def match(self, left: FloatArray, right: FloatArray) -> Estimate:
        """Compute the disparity field for a rectified stereo pair."""
        ...
