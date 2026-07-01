from types import SimpleNamespace

import pytest

from astrolens.connectors.mast import MastObservationSummary
from astrolens.core.models import Coordinates
from astrolens.services.target_validation import (
    TargetValidationStatus,
    angular_separation_arcsec,
    validate_observation_target,
)


def test_validate_observation_target_centered_from_coordinates() -> None:
    result = validate_observation_target(
        Coordinates(ra_deg=187.70593077, dec_deg=12.39112325),
        MastObservationSummary(
            obsid="centered",
            ra_deg=187.70593077,
            dec_deg=12.39112325,
        ),
    )

    assert result.status == TargetValidationStatus.CENTERED
    assert result.confidence == 0.95
    assert result.distance_arcsec == pytest.approx(0.0)
    assert result.target_in_frame is True
    assert "Computed target distance" in result.notes[0]


def test_validate_observation_target_nearby_from_simple_fields() -> None:
    result = validate_observation_target(
        {"ra_deg": 10.0, "dec_deg": 0.0},
        SimpleNamespace(ra_deg=10.01, dec_deg=0.0),
    )

    assert result.status == TargetValidationStatus.IN_FRAME
    assert result.distance_arcsec == pytest.approx(36.0, abs=0.01)
    assert 0.65 < result.confidence < 0.9
    assert result.target_in_frame is True


def test_validate_observation_target_offset_when_far_from_center() -> None:
    result = validate_observation_target(
        {"ra_deg": 10.0, "dec_deg": 0.0},
        {"ra_deg": 10.1, "dec_deg": 0.0},
    )

    assert result.status == TargetValidationStatus.OUT_OF_FRAME
    assert result.distance_arcsec == pytest.approx(360.0, abs=0.01)
    assert result.confidence == 0.1
    assert result.target_in_frame is False


def test_validate_observation_target_uses_raw_metadata_coordinates() -> None:
    result = validate_observation_target(
        {"coordinates": {"ra_deg": 10.0, "dec_deg": 0.0}},
        {"raw_metadata": {"s_ra": "10.01", "s_dec": "0.0"}},
    )

    assert result.status == TargetValidationStatus.IN_FRAME
    assert result.distance_arcsec == pytest.approx(36.0, abs=0.01)
    assert result.target_in_frame is True


def test_validate_observation_target_uncertain_without_observation_metadata() -> None:
    result = validate_observation_target(
        {"ra_deg": 10.0, "dec_deg": 0.0},
        {"obsid": "missing-position"},
    )

    assert result.status == TargetValidationStatus.UNVERIFIED
    assert result.confidence == 0.0
    assert result.distance_arcsec is None
    assert result.target_in_frame is None
    assert "Missing observation center" in result.notes[0]


def test_validate_observation_target_prefers_mast_distance_degrees() -> None:
    result = validate_observation_target(
        {"ra_deg": 10.0, "dec_deg": 0.0},
        MastObservationSummary(
            obsid="mast-distance",
            ra_deg=11.0,
            dec_deg=0.0,
            distance_degrees=0.001,
        ),
    )

    assert result.status == TargetValidationStatus.CENTERED
    assert result.distance_arcsec == pytest.approx(3.6)
    assert result.target_in_frame is True
    assert "archive-provided" in result.notes[0]


def test_angular_separation_handles_ra_wrap() -> None:
    distance = angular_separation_arcsec((359.999, 0.0), (0.001, 0.0))

    assert distance == pytest.approx(7.2, abs=0.01)
