"""Ground-truth depth maps for synthetic stimuli.

Default depths span 0.9-1.6 m, chosen so that with the demo rig (64 mm baseline,
800 px focal, fixation at 2.5 m) every disparity lands strictly *inside* a 48 px
search range. This is not cosmetic. A matcher must reject the endpoints of its
own search range -- index 0 has no left neighbour for the parabolic fit -- so a
surface sitting exactly at the fixation plane produces zero disparity and is
correctly discarded wholesale. Put the fixation plane behind the scene.

Each returns depth in **metres**, cyclopean frame, shape (H, W). These are the
classic psychophysical surfaces: a floating disk (Julesz), a staircase
("wedding cake"), a slanted plane, and a sinusoidal corrugation. Between them
they exercise depth steps, gradients, and curvature -- the three things a
disparity estimator can fail at differently.
"""

from __future__ import annotations

import numpy as np

from activestereo.types import FloatArray


def _grid(shape: tuple[int, int]) -> tuple[FloatArray, FloatArray]:
    """Normalised (row, col) coordinates in [-1, 1], aspect-preserving on rows."""
    H, W = shape
    rows = np.linspace(-1.0, 1.0, H)[:, None] * np.ones((1, W))
    cols = np.ones((H, 1)) * np.linspace(-1.0, 1.0, W)[None, :]
    return rows, cols


def disk(
    shape: tuple[int, int] = (240, 320),
    near: float = 0.9,
    far: float = 1.6,
    radius: float = 0.4,
) -> FloatArray:
    """A disk at ``near`` floating in front of a plane at ``far``.

    The canonical random-dot stereogram stimulus: a shape with a hard depth step
    and therefore a genuine half-occlusion band along each vertical edge. If your
    pipeline handles this, it handles occlusion.
    """
    rows, cols = _grid(shape)
    inside = np.hypot(rows, cols) <= radius
    return np.where(inside, near, far)


def staircase(
    shape: tuple[int, int] = (240, 320),
    depths: tuple[float, ...] = (0.9, 1.1, 1.3, 1.6),
) -> FloatArray:
    """Vertical bands at successive depths -- the "wedding cake".

    Multiple simultaneous depth steps of differing magnitude, which is where a
    single global smoothness prior tends to reveal itself.
    """
    H, W = shape
    out = np.empty((H, W), dtype=float)
    edges = np.linspace(0, W, len(depths) + 1).astype(int)
    for i, z in enumerate(depths):
        out[:, edges[i] : edges[i + 1]] = z
    return out


def slanted_plane(
    shape: tuple[int, int] = (240, 320),
    near: float = 0.9,
    far: float = 1.6,
) -> FloatArray:
    """A plane slanted about the vertical axis: smooth horizontal depth gradient.

    Contains no depth step, so it is fully matched -- useful as the control
    condition against which the occluded stimuli are compared.
    """
    _, cols = _grid(shape)
    t = (cols + 1.0) / 2.0
    return near + t * (far - near)


def corrugated(
    shape: tuple[int, int] = (240, 320),
    mean_depth: float = 1.0,
    amplitude: float = 0.15,
    cycles: float = 2.0,
) -> FloatArray:
    """Sinusoidal depth corrugation: curvature without discontinuity.

    The stimulus that separates estimators which recover *depth* from those which
    merely recover *depth ordering*.
    """
    _, cols = _grid(shape)
    return mean_depth + amplitude * np.sin(np.pi * cycles * cols)
