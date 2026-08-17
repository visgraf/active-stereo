"""Sliding-window reductions shared across layers.

``boxsum`` lived as a private copy in three modules -- ``inference.block``,
``encoding.energy`` and ``scenes.blender`` -- each carrying a comment that a
small helper is better owned than imported. That argument holds at two copies and
stops holding at three: a bug fixed in one becomes a bug fixed in one of three.
See issue #5.

``utils`` is importable from everywhere (``docs/architecture.md``: "utils, types
<- everything"), so this creates no new dependency edge.
"""

from __future__ import annotations

import numpy as np

from activestereo.types import FloatArray


def boxsum(a: FloatArray, r: int) -> FloatArray:
    """Sum over every ``(2r+1) x (2r+1)`` window, same shape out.

    Computed from a summed-area table, so cost is independent of ``r``.

    Parameters
    ----------
    a : (H, W) array. Must be finite: ``nan`` propagates through the cumulative
        sums and contaminates every window downstream of it, not just the windows
        containing it. Callers masking invalid data (ADR-0002) substitute zeros
        and divide by ``boxsum(valid)``; ``scenes.blender.albedo_texture_contrast``
        shows the pattern.
    r : window radius in pixels. ``r = 0`` returns ``a`` unchanged in effect.

    Returns
    -------
    (H, W) window sums. Edges use **edge padding**, so a window overhanging the
    border repeats the border pixel rather than treating outside as zero. That
    choice is load-bearing: zero-padding would bias sums downward at the frame
    edge, which reads downstream as low contrast and therefore as low confidence
    exactly where the field of view ends.
    """
    pad = np.pad(a, r, mode="edge")
    c = np.cumsum(np.cumsum(pad, axis=0), axis=1)
    c = np.pad(c, ((1, 0), (1, 0)))
    k = 2 * r + 1
    H, W = a.shape
    return c[k : k + H, k : k + W] - c[0:H, k : k + W] - c[k : k + H, 0:W] + c[0:H, 0:W]
