"""Unit tests for the L2 binocular energy-model encoder.

These check Protocol conformance and basic contract properties (shape,
non-negativity, nan-propagation, determinism), plus one fast smoke test for
gain invariance. The full, quantitatively-thresholded validation of gain
invariance across 5 seeds x 5 gains is exp002
(experiments/exp002_energy_model_validation), not here -- see its findings.md.
"""

from __future__ import annotations

import numpy as np
import pytest

from activestereo.encoding import DisparityEncoder, GaborEnergyEncoder


def _bank(center=8, half_width=8, step=1.0):
    return np.arange(center - half_width, center + half_width + step, step)


def test_energy_encoder_satisfies_protocol():
    assert isinstance(GaborEnergyEncoder(_bank()), DisparityEncoder)


def test_rejects_empty_bank():
    with pytest.raises(ValueError, match="non-empty"):
        GaborEnergyEncoder(np.array([]))


def test_output_shape_and_bank_length(synthetic_pair):
    left, right, _ = synthetic_pair(shape=(64, 96), disparity=8)
    enc = GaborEnergyEncoder(_bank())
    resp = enc.encode(left, right)
    assert resp.shape == (enc.disparities.size, 64, 96)


def test_response_is_non_negative(synthetic_pair):
    left, right, _ = synthetic_pair(shape=(64, 96), disparity=8)
    enc = GaborEnergyEncoder(_bank())
    resp = enc.encode(left, right)
    finite = np.isfinite(resp)
    assert np.all(resp[finite] >= 0.0)


def test_peak_channel_matches_known_disparity(synthetic_pair):
    left, right, d0 = synthetic_pair(shape=(64, 96), disparity=8, noise=0.01)
    enc = GaborEnergyEncoder(_bank(center=8, half_width=8, step=1.0))
    resp = enc.encode(left, right)
    valid_cols = np.all(np.isfinite(resp), axis=0)
    assert valid_cols.any(), "no pixels had full support -- kernel radius too large for W=96?"
    peak = enc.disparities[np.argmax(resp, axis=0)]
    err = np.abs(peak[valid_cols] - d0)
    assert np.median(err) <= 1.0, (
        f"median peak-channel error {np.median(err):.2f}px exceeds one bank step -- "
        "did someone break the phase-shift combination formula?"
    )


def test_invalid_input_pixels_with_no_support_become_nan(synthetic_pair):
    """A band of nan wider than the kernel diameter must leave its deep interior
    nan in the output (ADR-0002: mask before mixing; no valid support -> no
    manufactured answer). A narrow gap is expected to be filled in by the
    surrounding valid data -- that is normalised convolution working correctly,
    not a bug -- so the band here is deliberately wider than the ~37px kernel."""
    left, right, _ = synthetic_pair(shape=(64, 96), disparity=8)
    left = left.copy()
    left[:, 20:70] = np.nan
    enc = GaborEnergyEncoder(_bank())
    resp = enc.encode(left, right)
    deep_interior = resp[:, :, 40:50]  # >= kernel radius away from both band edges
    assert not np.any(np.isfinite(deep_interior)), (
        "a column with zero valid support in its kernel window produced a finite "
        "response -- masking-before-mixing (ADR-0002) is not being honoured"
    )


def test_deterministic(synthetic_pair):
    left, right, _ = synthetic_pair(shape=(64, 96), disparity=8)
    enc = GaborEnergyEncoder(_bank())
    r1 = enc.encode(left, right)
    r2 = enc.encode(left, right)
    np.testing.assert_array_equal(r1, r2, err_msg="encode() is nondeterministic -- rng leak?")


def test_peak_channel_is_gain_invariant():
    """Fast smoke test for the property exp002 validates in full (issue #1):
    interocular contrast gain must not move the peak channel."""
    rng = np.random.default_rng(0)
    shape = (64, 96)
    d0 = 8
    base = rng.random((shape[0], shape[1] + d0))
    left = base[:, : shape[1]]
    right_full = base[:, d0 : d0 + shape[1]]

    enc = GaborEnergyEncoder(_bank(center=8, half_width=8, step=1.0))
    resp_g1 = enc.encode(left, right_full * 1.0)
    resp_g2 = enc.encode(left, right_full * 0.5)

    valid = np.all(np.isfinite(resp_g1), axis=0) & np.all(np.isfinite(resp_g2), axis=0)
    peak1 = enc.disparities[np.argmax(resp_g1, axis=0)]
    peak2 = enc.disparities[np.argmax(resp_g2, axis=0)]
    drift = np.abs(peak1[valid] - peak2[valid])
    assert np.median(drift) <= 1.0, (
        f"peak channel drifted {np.median(drift):.2f}px under a gain change -- "
        "the contrast-invariance property no longer holds"
    )
