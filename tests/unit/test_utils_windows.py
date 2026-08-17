"""Unit tests for ``utils.boxsum``.

Previously a private helper duplicated in three modules (issue #5) and therefore
only ever tested through its callers. Now shared, so its contract is pinned here:
three layers depend on it, and the edge-padding convention in particular is
load-bearing rather than incidental.
"""

from __future__ import annotations

import numpy as np

from activestereo.utils import boxsum


def _naive(a, r):
    """Reference implementation: explicit per-window sum over an edge-padded array."""
    pad = np.pad(a, r, mode="edge")
    H, W = a.shape
    out = np.empty_like(a, dtype=float)
    for i in range(H):
        for j in range(W):
            out[i, j] = pad[i : i + 2 * r + 1, j : j + 2 * r + 1].sum()
    return out


def test_matches_a_naive_window_sum():
    """The summed-area table is an optimisation, so it owes an exact answer."""
    rng = np.random.default_rng(0)
    a = rng.random((13, 17))
    for r in (0, 1, 2, 3, 5):
        np.testing.assert_allclose(boxsum(a, r), _naive(a, r), rtol=1e-12, atol=1e-12)


def test_radius_zero_is_the_identity():
    rng = np.random.default_rng(1)
    a = rng.random((8, 11))
    np.testing.assert_allclose(boxsum(a, 0), a, rtol=1e-12)


def test_uniform_input_gives_the_window_area():
    for r in (1, 3, 4):
        out = boxsum(np.ones((12, 15)), r)
        np.testing.assert_allclose(out, (2 * r + 1) ** 2, rtol=1e-12)


def test_edges_are_edge_padded_not_zero_padded():
    """Zero-padding would bias sums downward at the frame border, which reads
    downstream as low contrast and therefore as low confidence exactly where the
    field of view ends. All three callers rely on this, so pin it."""
    a = np.ones((9, 9))
    out = boxsum(a, 2)
    assert out[0, 0] == 25.0, "corner window was not edge-padded (zero-padded?)"
    np.testing.assert_allclose(out, 25.0, rtol=1e-12)


def test_shape_is_preserved():
    for shape in ((1, 1), (1, 9), (9, 1), (6, 7)):
        assert boxsum(np.ones(shape), 2).shape == shape


def test_valid_count_pattern_used_by_every_caller():
    """The masking-before-mixing idiom (ADR-0002): sum the data with invalid
    entries zeroed, sum the mask, divide. All three callers do exactly this, so
    the combination is worth one test of its own."""
    a = np.arange(36, dtype=float).reshape(6, 6)
    valid = np.ones((6, 6), dtype=bool)
    valid[2:4, 2:4] = False

    n = boxsum(valid.astype(float), 1)
    s = boxsum(np.where(valid, a, 0.0), 1)
    mean = s / n

    # A window with no invalid neighbours must equal the ordinary window mean.
    fully_valid = n == 9.0
    assert fully_valid.any()
    reference = _naive(a, 1) / 9.0
    np.testing.assert_allclose(mean[fully_valid], reference[fully_valid], rtol=1e-12)

    # And no invalid value can influence any window, however extreme it is.
    extreme = a.copy()
    extreme[2:4, 2:4] = 1e12
    np.testing.assert_array_equal(s, boxsum(np.where(valid, extreme, 0.0), 1))

    # The mask count must actually drop next to the hole, or the division above
    # is dividing by a constant and the whole idiom is doing nothing.
    assert n[2, 2] < 9.0
