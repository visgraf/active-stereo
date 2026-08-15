"""L6 — active sampling: saliency, foveal confinement, gaze policy."""

from activestereo.policy.foveation import linearization_penalty
from activestereo.policy.gaze import next_fixation
from activestereo.policy.saliency import masked_blur, uncertainty_saliency

__all__ = [
    "linearization_penalty",
    "masked_blur",
    "next_fixation",
    "uncertainty_saliency",
]
