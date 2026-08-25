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
    is_forward_gaze,
    rectification_rotation,
    require_forward_azimuth,
    target_to_fixation,
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
    "is_forward_gaze",
    "project_toed_in",
    "rectification_rotation",
    "require_forward_azimuth",
    "target_to_fixation",
    "toed_in_disparity",
    "vieth_muller_circle",
    "vieth_muller_points",
    "vieth_muller_radius",
]
