"""L2 — neural encoding: binocular energy model and disparity tuning.

Migration target: the binocular energy model from `active_stereo_demo.py`.
The Protocol below fixes the interface so L3 can be developed against it now.
"""

from activestereo.encoding.base import DisparityEncoder

__all__ = ["DisparityEncoder"]
