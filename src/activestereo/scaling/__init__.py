"""L4 — metric scaling and MLE cue fusion.

This is where the *scaling closure* is discharged: disparity is dimensionless
until this layer supplies the metric scale from rig geometry and vergence state.
"""

from activestereo.scaling.fusion import fuse_mle
from activestereo.scaling.metric import scale_to_depth

__all__ = ["fuse_mle", "scale_to_depth"]
