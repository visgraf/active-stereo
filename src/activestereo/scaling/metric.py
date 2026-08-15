"""Disparity -> metric depth, with uncertainty propagated through the inversion."""

from __future__ import annotations

import numpy as np

from activestereo.types import Estimate, StereoRig


def scale_to_depth(disparity: Estimate, rig: StereoRig) -> Estimate:
    """Convert a disparity estimate to a metric depth estimate.

    The depth variance follows from a first-order propagation of the inverse
    relation ``Z = 1 / (d/(f b) + 1/Zf)``:

        dZ/dd = -Z^2 / (f b)   =>   var(Z) = (Z^2 / (f b))^2 var(d)

    The quadratic dependence on ``Z`` is the reason far depth is poorly
    constrained by stereo alone, and therefore the reason L4 fuses other cues.
    """
    d = disparity.value
    inv_fix = 0.0 if not np.isfinite(rig.fixation_distance) else 1.0 / rig.fixation_distance
    fb = rig.focal_px * rig.baseline

    with np.errstate(invalid="ignore", divide="ignore"):
        inv_Z = d / fb + inv_fix
        Z = np.where(inv_Z > 0, 1.0 / inv_Z, np.nan)
        jac = Z**2 / fb
        var_Z = jac**2 * disparity.variance

    bad = ~np.isfinite(Z) | ~np.isfinite(var_Z)
    Z = np.where(bad, np.nan, Z)
    var_Z = np.where(bad, np.nan, var_Z)
    return Estimate(value=Z, variance=var_Z)
