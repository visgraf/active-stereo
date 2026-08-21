"""The L2->L3 energy decoder (issue #12, exp005).

Two kinds of test, deliberately separate. **Stub-encoder tests** inject crafted
profiles and pin the readout mechanics exactly -- endpoint rejection, the
variance floor, multimodal inflation -- with no Gabor filtering in the way.
**Integration tests** run the real ``GaborEnergyEncoder`` underneath and pin the
properties exp005's falsifiers assume: no centroid bias toward the bank centre,
and end-to-end gain invariance of value, variance, *and the refusal decision*.

The precision the experiment is designed to *measure* (H1a/H1b) is asserted only
loosely here -- a unit test that pre-empted the experiment's falsifier would make
the experiment decoration.
"""

from __future__ import annotations

import numpy as np
import pytest

from activestereo.inference import DisparityMatcher, EnergyDecoder
from activestereo.types import FloatArray

H, W = 24, 40


class StubEncoder:
    """A ``DisparityEncoder`` returning a pre-built response volume."""

    def __init__(self, disparities: FloatArray, response: FloatArray) -> None:
        self._d = np.asarray(disparities, dtype=float)
        self._response = np.asarray(response, dtype=float)

    @property
    def disparities(self) -> FloatArray:
        return self._d

    def encode(self, left: FloatArray, right: FloatArray) -> FloatArray:
        return self._response.copy()  # match() mutates its volume in place


def stub_decoder(profile: FloatArray, K: int = 17, **kw) -> EnergyDecoder:
    """Decoder over a bank [0..K-1] whose every pixel sees ``profile`` (K,)."""
    response = np.broadcast_to(
        np.asarray(profile, float)[:, None, None], (K, H, W)
    ).copy()
    return EnergyDecoder(encoder=StubEncoder(np.arange(K, dtype=float), response), **kw)


def run_stub(profile, **kw):
    dec = stub_decoder(np.asarray(profile, float), K=len(profile), **kw)
    return dec.match(np.zeros((H, W)), np.zeros((H, W)))


def delta(K: int, k: int, height: float = 1.0, floor: float = 0.0):
    p = np.full(K, floor)
    p[k] += height
    return p


# --- Protocol and construction ----------------------------------------------


def test_satisfies_the_matcher_protocol():
    assert isinstance(EnergyDecoder(max_disparity=8), DisparityMatcher)


def test_rejects_a_non_uniform_bank():
    enc = StubEncoder(np.array([0.0, 1.0, 3.0]), np.zeros((3, H, W)))
    with pytest.raises(ValueError, match="uniformly spaced"):
        EnergyDecoder(encoder=enc)


def test_rejects_bad_readout_constants():
    with pytest.raises(ValueError, match="flatness"):
        EnergyDecoder(max_disparity=8, flatness=0.0)
    with pytest.raises(ValueError, match="centroid_halfwidth"):
        EnergyDecoder(max_disparity=8, centroid_halfwidth=0)


def test_shape_mismatch_raises():
    with pytest.raises(ValueError, match="shape mismatch"):
        EnergyDecoder(max_disparity=8).match(np.zeros((4, 6)), np.zeros((4, 7)))


# --- Readout mechanics, via crafted profiles --------------------------------


def test_delta_profile_reads_its_channel_with_the_floor_variance():
    """A single-channel delta is the most confident possible profile. Its value
    is the channel's disparity and its variance is exactly the quantisation
    floor step^2/12 -- strictly positive, because Estimate.precision zeroes any
    pixel whose variance is not > 0, and the most confident answer must not be
    the one that gets zero fusion weight."""
    est = run_stub(delta(17, 8))
    assert np.allclose(est.value[5, 20], 8.0)
    assert np.allclose(est.variance[5, 20], 1.0 / 12.0)
    assert (est.variance[np.isfinite(est.variance)] > 0).all()


def test_endpoint_peaks_are_declined_not_clamped():
    """An argmax within centroid_halfwidth of either bank end means the true
    disparity may lie outside the search range; the honest answer is nan.
    Subsumes BlockMatcher's best>0 / best<D-1 convention."""
    for k in (0, 1, 15, 16):
        est = run_stub(delta(17, k), centroid_halfwidth=2)
        assert np.isnan(est.value).all(), f"peak at channel {k} was answered"
    est = run_stub(delta(17, 2), centroid_halfwidth=2)
    assert np.isfinite(est.value).all()


def test_flat_profile_is_refused_in_both_arrays():
    """No preferred disparity -> no answer, and nan in value AND variance per
    the L3 contract. This is the profile a pixel with no correspondent should
    produce -- whether it actually does on real occlusions is exp005's H2, not
    something a unit test can grant."""
    est = run_stub(np.full(17, 3.0))
    assert np.isnan(est.value).all()
    assert np.isnan(est.variance).all()


def test_all_zero_profile_is_refused():
    est = run_stub(np.zeros(17))
    assert np.isnan(est.value).all()


def test_baseline_floor_does_not_bias_the_value():
    """The failure baseline subtraction exists to prevent: a uniform floor under
    an off-centre peak drags a naive full-profile centroid toward the bank
    centre. With the floor subtracted, the peak's channel is recovered."""
    est = run_stub(delta(17, 3, height=1.0, floor=0.5), centroid_halfwidth=1)
    assert np.allclose(est.value[0, 0], 3.0)
    est = run_stub(delta(17, 13, height=1.0, floor=0.5), centroid_halfwidth=1)
    assert np.allclose(est.value[0, 0], 13.0)


def test_multimodal_evidence_inflates_variance():
    """Two well-separated peaks: the value commits to one, but the full-profile
    second moment must report the ambiguity. This is the property that could
    escape the anti-calibration, and the readout must not hide it by using only
    the local window for the variance."""
    p = np.zeros(33)
    p[6] = 1.0
    p[26] = 0.999  # slightly lower, so the argmax is deterministic
    est = run_stub(p)
    sharp = run_stub(delta(33, 6))
    assert est.variance[0, 0] > 50.0
    assert est.variance[0, 0] > 100.0 * sharp.variance[0, 0]


def test_nan_pixels_from_the_encoder_stay_nan():
    K = 9
    response = np.ones((K, H, W))
    response[:, 3, 7] = np.nan  # encoder-invalid pixel, nan in every band
    response[4] += 1.0  # give everyone else a clear interior peak
    dec = EnergyDecoder(encoder=StubEncoder(np.arange(K, dtype=float), response))
    est = dec.match(np.zeros((H, W)), np.zeros((H, W)))
    assert np.isnan(est.value[3, 7]) and np.isnan(est.variance[3, 7])
    assert np.isfinite(est.value[0, 0])


# --- Integration with the real encoder --------------------------------------


def _pair(d0: int, shape=(48, 96), seed: int = 0, noise: float = 0.01):
    """Textured pair with exact known disparity, the repo's left[x] <-> right[x-d]
    convention (same construction as tests/conftest.py's synthetic_pair)."""
    rng = np.random.default_rng(seed)
    Hh, Ww = shape
    base = rng.random((Hh, Ww + d0))
    left = base[:, :Ww] + rng.normal(0, noise, (Hh, Ww))
    right = base[:, d0 : d0 + Ww] + rng.normal(0, noise, (Hh, Ww))
    return left, right


def test_recovers_a_known_disparity():
    left, right = _pair(8)
    est = EnergyDecoder(max_disparity=16).match(left, right)
    ok = np.isfinite(est.value)
    assert ok.mean() > 0.5
    # Loose by design: per-pixel precision is exp005 H1b's question, not ours.
    assert abs(np.median(est.value[ok]) - 8.0) < 1.0


def test_readout_is_unbiased_where_the_peak_won():
    """The centre-bias pin promised in issue #12, stated against the mechanism
    it actually found.

    The naive version of this test -- unconditional median error at d0 far off
    the bank centre -- FAILED when first run, by +0.99 px on a [0..32] bank and
    +3.0 px on [0..64]. Diagnosis (recorded in the #12 constants comment): the
    bias scales with distance from the bank centre and not from the bank edge,
    a ±2-channel centroid cannot move a value 3 px, and neither readout
    constant changes it -- so it is not the centroid. The answered population
    is a *mixture*: pixels where the true peak won (values at d0) and pixels
    where broadband noise won (argmax roughly uniform over the bank, median at
    the bank centre). The pull is contamination by the second class, i.e. the
    encoder's per-pixel discriminability that exp002 already measured -- the
    quantity H1a/H1b exist to score, not something a unit test may pre-empt.

    What the readout itself owes, and what this test pins: pixels that landed
    near the truth are unbiased. Measured +0.006 px at first writing.
    """
    for d0 in (5, 27):
        left, right = _pair(d0, shape=(48, 128))
        est = EnergyDecoder(max_disparity=32).match(left, right)
        near = np.isfinite(est.value) & (np.abs(est.value - d0) <= 2.0)
        assert near.mean() > 0.2, f"d0={d0}: too few peak-won pixels to measure"
        bias = float(np.median(est.value[near]) - d0)
        assert abs(bias) < 0.25, f"d0={d0}: peak-won median off by {bias:+.3f} px"


def test_contamination_pulls_toward_the_centre_and_grows_with_the_bank():
    """Characterisation, not endorsement: the mixture contamination described in
    the previous test is real, directional, and bank-width-dependent, and this
    pin makes sure it cannot change silently. Measured at first writing:
    +1.0 px (bank [0..32]) and +3.0 px (bank [0..64]) at d0=5. If a future
    encoder or readout change removes it, this test should FAIL and be inverted
    -- deliberately, with the number recorded -- not weakened."""
    left, right = _pair(5, shape=(48, 128))
    biases = []
    for dmax in (32, 64):
        est = EnergyDecoder(max_disparity=dmax).match(left, right)
        ok = np.isfinite(est.value)
        biases.append(float(np.median(est.value[ok]) - 5.0))
    assert biases[0] > 0.25, "contamination pull vanished on the narrow bank"
    assert biases[1] > biases[0], "pull no longer grows with bank width"


def test_gain_invariance_is_exact_for_powers_of_two():
    """Scaling the right image by 2^n changes only floating-point exponents, so
    every linear step is bit-exact and the whole readout -- value, variance, and
    crucially the *refusal mask* -- must be identical. The mask clause is what
    the relative (ratio) flatness rule exists to pass: an absolute mass floor
    would answer different pixels at different exposures."""
    left, right = _pair(8)
    dec = EnergyDecoder(max_disparity=16)
    base = dec.match(left, right)
    for gain in (0.5, 2.0):
        scaled = dec.match(left, right * gain)
        np.testing.assert_array_equal(
            np.isfinite(base.value), np.isfinite(scaled.value), err_msg=f"mask, g={gain}"
        )
        np.testing.assert_array_equal(
            np.nan_to_num(base.value), np.nan_to_num(scaled.value), err_msg=f"value, g={gain}"
        )
        np.testing.assert_array_equal(
            np.nan_to_num(base.variance),
            np.nan_to_num(scaled.variance),
            err_msg=f"variance, g={gain}",
        )


def test_constant_images_are_fully_refused():
    """A blank wall has no disparity evidence. The Gabor DC leakage gives a
    uniform positive coherence across every channel, which the flatness rule --
    not a special case -- must refuse."""
    flat = np.full((H, W), 0.5)
    est = EnergyDecoder(max_disparity=8).match(flat, flat.copy())
    assert np.isnan(est.value).all()
    assert np.isnan(est.variance).all()
