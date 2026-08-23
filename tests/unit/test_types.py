"""Shared types and the uncertainty-first-class invariant."""

import dataclasses

import numpy as np
import pytest

from activestereo.types import Estimate, Fixation, StereoRig


def test_rig_rejects_nonphysical_parameters():
    with pytest.raises(ValueError, match="baseline"):
        StereoRig(baseline=0.0, focal_px=800.0)
    with pytest.raises(ValueError, match="focal_px"):
        StereoRig(baseline=0.064, focal_px=-1.0)


@pytest.mark.regression
@pytest.mark.parametrize(
    "field", ["baseline", "focal_px", "vergence", "principal_row", "principal_col"]
)
@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_rig_rejects_nonfinite_fields(field, bad):
    """StereoRig must reject non-finite parameters at construction.

    Found during migration step 2, when Fixation gained finiteness checks and
    StereoRig was left without them, creating an asymmetry in the arguments to
    geometry.oculomotor.eye_rotations (step 3). `nan <= 0` is False, so the
    sign checks alone admitted StereoRig(baseline=nan, focal_px=nan,
    vergence=nan), which then produced NaN through fixation_distance and the
    L4 scaling path with no error at the source — the unmarked-invalid case
    ADR-0011 forbids.
    """
    kwargs: dict = {"baseline": 0.064, "focal_px": 800.0, "vergence": 0.0}
    if field == "principal_row":
        kwargs["principal_point"] = (bad, 0.0)
        match = "principal_point"
    elif field == "principal_col":
        kwargs["principal_point"] = (0.0, bad)
        match = "principal_point"
    else:
        kwargs[field] = bad
        match = field
    with pytest.raises(ValueError, match=match):
        StereoRig(**kwargs)


def test_fixation_rejects_negative_vergence():
    with pytest.raises(ValueError, match="vergence"):
        Fixation(azimuth=0.0, elevation_down=0.0, vergence=-1e-9)


def test_fixation_zero_vergence_is_legal():
    """Zero means parallel gaze, fixation at infinity — a state, not an error."""
    f = Fixation(azimuth=0.1, elevation_down=-0.2, vergence=0.0)
    assert f.vergence == 0.0


@pytest.mark.parametrize("field", ["azimuth", "elevation_down", "vergence"])
@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_fixation_rejects_nonfinite_fields(field, bad):
    # Checked per-field and explicitly: `nan < 0` is False, so a sign check
    # alone admits NaN. StereoRig had the same hole until it gained the
    # matching checks (see test_rig_rejects_nonfinite_fields).
    kwargs = {"azimuth": 0.0, "elevation_down": 0.0, "vergence": 0.0}
    kwargs[field] = bad
    with pytest.raises(ValueError, match=field):
        Fixation(**kwargs)


def test_fixation_is_frozen():
    f = Fixation.forward(0.05)
    with pytest.raises(dataclasses.FrozenInstanceError):
        f.vergence = 0.1


def test_fixation_forward_postcondition():
    """forward() is the ADR-0013 static-degradation path: straight ahead,
    vergence passed through unchanged."""
    f = Fixation.forward(0.128)
    assert f.azimuth == 0.0
    assert f.elevation_down == 0.0
    assert f.vergence == 0.128


def test_fixation_equality_is_structural_not_angular():
    """Pins the declared open question (docs/plans/fixation-migration.md):
    fixations differing by 2*pi are the same oculomotor state but compare
    unequal today. If wrapping or a custom __eq__ is ever added, this test
    fails and forces the open question to be resolved deliberately rather
    than as a side effect."""
    a = Fixation(azimuth=0.0, elevation_down=0.0, vergence=0.1)
    b = Fixation(azimuth=2.0 * np.pi, elevation_down=0.0, vergence=0.1)
    assert a != b
    assert a == Fixation(azimuth=0.0, elevation_down=0.0, vergence=0.1)


def test_estimate_rejects_shape_mismatch():
    with pytest.raises(ValueError, match="shape mismatch"):
        Estimate(value=np.zeros((2, 2)), variance=np.zeros((3, 3)))


def test_precision_is_zero_on_invalid_entries():
    e = Estimate(
        value=np.array([1.0, np.nan, 3.0]),
        variance=np.array([0.25, np.nan, 0.0]),
    )
    np.testing.assert_allclose(e.precision, [4.0, 0.0, 0.0])
    np.testing.assert_array_equal(e.valid, [True, False, True])
