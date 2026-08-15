"""Forward and inverse projection for a converged binocular rig.

Sign convention (CLAUDE.md §3): disparity is in pixels, left-image convention,
positive = crossed = nearer than the fixation point.
"""

from __future__ import annotations

import numpy as np

from activestereo.types import FloatArray, StereoRig


def depth_to_disparity(Z: FloatArray, rig: StereoRig) -> FloatArray:
    """Map metric depth to retinal disparity (the generative direction, L1).

    For a rig fixating at distance ``Zf``, a point at depth ``Z`` produces

        d = f * b * (1/Z - 1/Zf)

    which is zero on the horopter, positive (crossed) nearer than fixation and
    negative (uncrossed) beyond it. With ``vergence == 0``, ``Zf`` is infinite and
    this reduces to the familiar parallel-camera relation ``d = f b / Z``.

    Parameters
    ----------
    Z : array, metres, cyclopean frame. Non-positive entries yield ``nan``.
    rig : StereoRig

    Returns
    -------
    array of disparity in pixels; ``nan`` where ``Z`` was invalid.
    """
    Z = np.asarray(Z, dtype=float)
    out = np.full(Z.shape, np.nan, dtype=float)
    ok = np.isfinite(Z) & (Z > 0)
    inv_fix = 0.0 if not np.isfinite(rig.fixation_distance) else 1.0 / rig.fixation_distance
    out[ok] = rig.focal_px * rig.baseline * (1.0 / Z[ok] - inv_fix)
    return out


def disparity_to_depth(d: FloatArray, rig: StereoRig) -> FloatArray:
    """Invert :func:`depth_to_disparity`.

    Exact inverse; the *uncertainty* of this inversion is not handled here but in
    L4 (`activestereo.scaling`), per the scaling closure. Entries that invert to a
    non-positive or infinite depth are returned as ``nan``.
    """
    d = np.asarray(d, dtype=float)
    out = np.full(d.shape, np.nan, dtype=float)
    inv_fix = 0.0 if not np.isfinite(rig.fixation_distance) else 1.0 / rig.fixation_distance
    inv_Z = d / (rig.focal_px * rig.baseline) + inv_fix
    ok = np.isfinite(inv_Z) & (inv_Z > 0)
    out[ok] = 1.0 / inv_Z[ok]
    return out
