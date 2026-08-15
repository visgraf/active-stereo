"""activestereo — a six-layer active Bayesian inference framework for stereo vision.

Layer map (see CLAUDE.md and docs/architecture.md):

    L1 geometry  -> L2 encoding -> L3 inference -> L4 scaling
                         ^                              |
                         |                              v
                    L6 policy   <----------------  L5 control

Conventions enforced repo-wide:
    disparity  : pixels, left-image convention, positive = crossed
    depth Z    : metres, cyclopean frame, +Z forward
    angles     : radians internally
    invalid    : np.nan (never 0 or -1)
"""

__version__ = "0.1.0"

from activestereo.types import Estimate, StereoRig

__all__ = ["Estimate", "StereoRig", "__version__"]
