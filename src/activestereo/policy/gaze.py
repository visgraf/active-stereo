"""Information-maximising gaze selection."""

from __future__ import annotations

import numpy as np

from activestereo.types import FloatArray


def next_fixation(
    saliency: FloatArray,
    visited: list[tuple[int, int]] | None = None,
    inhibition_radius: float = 20.0,
) -> tuple[int, int] | None:
    """Pick the next fixation as the argmax of saliency, with inhibition of return.

    Inhibition of return is not decoration: without it the policy re-fixates the
    same maximum whenever a fixation fails to reduce uncertainty there, which is
    exactly the geometric-occlusion case (ADR-0002).

    Returns
    -------
    (row, col), or ``None`` when no valid candidate remains -- the correct signal
    to terminate the active-sampling loop rather than spin.
    """
    s = np.array(saliency, dtype=float, copy=True)
    if visited:
        H, W = s.shape
        rows, cols = np.indices((H, W))
        for r0, c0 in visited:
            near = np.hypot(rows - r0, cols - c0) <= inhibition_radius
            s[near] = np.nan

    if not np.isfinite(s).any():
        return None
    idx = int(np.nanargmax(s))
    r, c = np.unravel_index(idx, s.shape)
    return int(r), int(c)
