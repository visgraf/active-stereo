"""L1 — generative geometry: projection, oculomotor rotations, and the Vieth-Muller horopter."""

from activestereo.geometry.horopter import (
    vieth_muller_circle,
    vieth_muller_points,
    vieth_muller_radius,
)
from activestereo.geometry.oculomotor import (
    EyeRotations,
    eye_rotations,
    fixation_distance,
    fixation_point,
)
from activestereo.geometry.projection import (
    BinocularProjection,
    depth_to_disparity,
    disparity_to_depth,
    project_toed_in,
    toed_in_disparity,
)

__all__ = [
    "BinocularProjection",
    "EyeRotations",
    "depth_to_disparity",
    "disparity_to_depth",
    "eye_rotations",
    "fixation_distance",
    "fixation_point",
    "project_toed_in",
    "toed_in_disparity",
    "vieth_muller_circle",
    "vieth_muller_points",
    "vieth_muller_radius",
]
