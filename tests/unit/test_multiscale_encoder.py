"""The multi-scale energy bank (issue #13, exp006).

The one test that matters most is the mechanism test: on a texture that is
periodic at fine scale, a single fine-scale encoder *must* alias (peaks at
``d0 ± period``) and the multi-scale combination *must* resolve it. That is the
entire claim coarse-to-fine fusion makes; if it fails in vitro there is no
point running the experiment.
"""

from __future__ import annotations

import numpy as np
import pytest

from activestereo.encoding import DisparityEncoder, MultiScaleEnergyEncoder
from activestereo.inference import EnergyDecoder
from activestereo.types import FloatArray

H, W = 48, 120


def periodic_pair(d0: int = 10, period: int = 8, seed: int = 0):
    """Stripes at ``period`` px (ambiguous to any matcher at lags of ±period)
    plus smoothed broadband blobs (unambiguous at coarse scale), shifted by
    ``d0`` -- the stimulus that separates a fine scale from a population."""
    rng = np.random.default_rng(seed)
    x = np.arange(W + d0, dtype=float)
    stripes = 0.5 * np.sin(2.0 * np.pi * x / period)[None, :].repeat(H, axis=0)
    noise = rng.standard_normal((H, W + d0 + 32))
    kernel = np.ones(24) / 24.0
    blobs = np.stack([np.convolve(row, kernel, mode="valid")[: W + d0] for row in noise])
    base = stripes + 2.0 * blobs + 0.02 * rng.standard_normal((H, W + d0))
    return base[:, :W], base[:, d0 : d0 + W]


def bank(K: int = 25) -> FloatArray:
    return np.arange(K, dtype=float)


class StubScale:
    """Stands in for one internal scale, for the dead/invalid branch tests."""

    def __init__(self, disparities: FloatArray, volume: FloatArray) -> None:
        self._d = disparities
        self._v = volume

    @property
    def disparities(self) -> FloatArray:
        return self._d

    def encode(self, left: FloatArray, right: FloatArray) -> FloatArray:
        return self._v.copy()


def test_satisfies_the_encoder_protocol():
    enc = MultiScaleEnergyEncoder(bank(9))
    assert isinstance(enc, DisparityEncoder)
    left = np.random.default_rng(0).random((16, 32))
    out = enc.encode(left, left.copy())
    assert out.shape == (9, 16, 32)
    finite = out[np.isfinite(out)]
    assert (finite >= 0).all()


def test_construction_rejects_bad_arguments():
    with pytest.raises(ValueError, match="combine"):
        MultiScaleEnergyEncoder(bank(), combine="mean")
    with pytest.raises(ValueError, match="scale"):
        MultiScaleEnergyEncoder(bank(), scales=())
    with pytest.raises(ValueError, match="floor"):
        MultiScaleEnergyEncoder(bank(), floor=0.0)
    with pytest.raises(ValueError, match="weights"):
        MultiScaleEnergyEncoder(bank(), scales=((8, 4), (16, 8)), weights=[1.0])


def test_single_fine_scale_aliases_on_periodic_texture():
    """First half of the mechanism claim: the ambiguity must actually exist, or
    the resolution test below proves nothing."""
    left, right = periodic_pair(d0=10, period=8)
    fine = EnergyDecoder(
        encoder=MultiScaleEnergyEncoder(bank(), scales=((8, 4),), combine="product")
    )
    est = fine.match(left, right)
    ok = np.isfinite(est.value)
    assert ok.mean() > 0.3
    gross = np.abs(est.value[ok] - 10.0) > 4.0
    assert gross.mean() > 0.15, (
        f"fine scale alone was only {gross.mean():.1%} grossly wrong -- the "
        "stimulus is not ambiguous enough to test disambiguation"
    )


def test_multiscale_resolves_the_aliasing():
    """Second half: the same stimulus through the population."""
    left, right = periodic_pair(d0=10, period=8)
    multi = EnergyDecoder(
        encoder=MultiScaleEnergyEncoder(bank(), scales=((8, 4), (32, 16)), combine="product")
    )
    est = multi.match(left, right)
    ok = np.isfinite(est.value)
    assert ok.mean() > 0.3
    gross = np.abs(est.value[ok] - 10.0) > 4.0
    assert gross.mean() < 0.05, f"aliases survived the population: {gross.mean():.1%}"
    assert abs(np.median(est.value[ok]) - 10.0) < 1.0


def test_gain_invariance_is_bit_exact_for_powers_of_two():
    """Each scale's profile is a ratio, so gain cancels scale-by-scale BEFORE
    combination -- value, variance and the refusal mask must be bit-identical
    end to end, exactly as pinned for the single-scale decoder."""
    rng = np.random.default_rng(1)
    d0 = 8
    base = rng.random((40, 96 + d0))
    left = base[:, :96]
    right = base[:, d0 : d0 + 96]
    for combine in ("product", "sum"):
        dec = EnergyDecoder(
            encoder=MultiScaleEnergyEncoder(bank(17), scales=((8, 4), (16, 8)), combine=combine)
        )
        ref = dec.match(left, right)
        for gain in (0.5, 2.0):
            got = dec.match(left, right * gain)
            np.testing.assert_array_equal(
                np.isfinite(ref.value), np.isfinite(got.value), err_msg=f"{combine} mask"
            )
            np.testing.assert_array_equal(
                np.nan_to_num(ref.value), np.nan_to_num(got.value), err_msg=f"{combine} value"
            )
            np.testing.assert_array_equal(
                np.nan_to_num(ref.variance),
                np.nan_to_num(got.variance),
                err_msg=f"{combine} variance",
            )


def test_dead_scale_does_not_veto_under_product():
    """No evidence at one scale must not erase the others' evidence: a dead
    scale contributes a uniform profile, and the combined argmax follows the
    live scale."""
    K, h, w = 9, 6, 10
    live = np.full((K, h, w), 0.1)
    live[5] = 1.0  # clear interior peak at channel 5
    enc = MultiScaleEnergyEncoder(bank(K), scales=((8, 4), (16, 8)), combine="product")
    enc._encoders[0] = StubScale(bank(K), live)
    enc._encoders[1] = StubScale(bank(K), np.zeros((K, h, w)))  # dead everywhere
    out = enc.encode(np.zeros((h, w)), np.zeros((h, w)))
    assert np.isfinite(out).all()
    assert (np.argmax(out, axis=0) == 5).all()


def test_invalid_at_any_scale_is_nan_in_every_band():
    K, h, w = 9, 6, 10
    good = np.full((K, h, w), 1.0)
    good[4] += 1.0
    bad = good.copy()
    bad[:, 2, 3] = np.nan  # one pixel invalid at one scale
    enc = MultiScaleEnergyEncoder(bank(K), scales=((8, 4), (16, 8)), combine="sum")
    enc._encoders[0] = StubScale(bank(K), good)
    enc._encoders[1] = StubScale(bank(K), bad)
    out = enc.encode(np.zeros((h, w)), np.zeros((h, w)))
    assert np.isnan(out[:, 2, 3]).all()
    assert np.isfinite(out[:, 0, 0]).all()


def test_end_to_end_at_least_matches_single_scale_on_plain_texture():
    """On broadband noise (no aliasing to resolve) the population must not be
    worse than the best single scale it contains -- the combination should cost
    nothing where there is nothing to disambiguate. Loose bars: precision on
    real stimuli is exp006's question, not this suite's."""
    rng = np.random.default_rng(2)
    d0 = 8
    base = rng.random((48, 96 + d0))
    left = base[:, :96] + rng.normal(0, 0.01, (48, 96))
    right = base[:, d0 : d0 + 96] + rng.normal(0, 0.01, (48, 96))

    def med_err(encoder):
        est = EnergyDecoder(encoder=encoder).match(left, right)
        ok = np.isfinite(est.value)
        return float(np.median(np.abs(est.value[ok] - d0))), float(ok.mean())

    multi_err, multi_cov = med_err(
        MultiScaleEnergyEncoder(bank(17), scales=((4, 2), (8, 4), (16, 8)))
    )
    single_err, _ = med_err(MultiScaleEnergyEncoder(bank(17), scales=((24, 6),)))
    assert multi_cov > 0.4
    assert multi_err <= single_err * 1.5 + 0.25, (multi_err, single_err)
