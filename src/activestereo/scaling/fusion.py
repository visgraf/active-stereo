"""Maximum-likelihood fusion of independent cues.

For Gaussian, conditionally independent cues the MLE combination is the
precision-weighted mean, with the fused precision the sum of precisions:

    mu* = (sum_i mu_i / s_i^2) / (sum_i 1 / s_i^2),    1/s*^2 = sum_i 1 / s_i^2

Two properties this implementation must preserve, because downstream code relies
on them: fusion never *increases* variance, and an invalid cue contributes
nothing rather than poisoning the result.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from activestereo.types import Estimate


def fuse_mle(cues: Sequence[Estimate]) -> Estimate:
    """Fuse cues by precision weighting.

    Parameters
    ----------
    cues : sequence of Estimate, all the same shape. Entries that are ``nan`` in a
        given cue are simply excluded from that pixel's fusion (precision zero).

    Returns
    -------
    Estimate whose entries are ``nan`` where *no* cue was valid.
    """
    if not cues:
        raise ValueError("fuse_mle requires at least one cue")
    shape = cues[0].value.shape
    for i, c in enumerate(cues):
        if c.value.shape != shape:
            raise ValueError(f"cue {i} has shape {c.value.shape}, expected {shape}")

    total_precision = np.zeros(shape)
    weighted_sum = np.zeros(shape)
    for c in cues:
        p = c.precision  # zero on invalid entries by construction
        total_precision += p
        weighted_sum += np.where(p > 0, c.value * p, 0.0)

    ok = total_precision > 0
    value = np.where(ok, weighted_sum / np.maximum(total_precision, 1e-300), np.nan)
    variance = np.where(ok, 1.0 / np.maximum(total_precision, 1e-300), np.nan)
    return Estimate(value=value, variance=variance)
