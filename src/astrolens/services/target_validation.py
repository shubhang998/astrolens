"""Deterministic target-position validation for archive observations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from typing import Any

from astrolens.core.enums import TargetValidationStatus

CENTERED_THRESHOLD_ARCSEC = 5.0
NEARBY_THRESHOLD_ARCSEC = 60.0
LIKELY_OUT_OF_FRAME_ARCSEC = 180.0


@dataclass(frozen=True)
class TargetValidationResult:
    """Result of validating whether an observation likely contains a target."""

    status: TargetValidationStatus
    confidence: float
    distance_arcsec: float | None
    target_in_frame: bool | None
    notes: tuple[str, ...] = ()


def validate_observation_target(
    object_coordinates: Any,
    observation: Any,
    *,
    centered_threshold_arcsec: float = CENTERED_THRESHOLD_ARCSEC,
    nearby_threshold_arcsec: float = NEARBY_THRESHOLD_ARCSEC,
    likely_out_of_frame_arcsec: float = LIKELY_OUT_OF_FRAME_ARCSEC,
) -> TargetValidationResult:
    """Validate an observation center or MAST distance against requested coordinates.

    The helper accepts Pydantic models, dataclasses, simple objects, tuples, or mappings.
    It prefers archive-provided distance metadata when present, then falls back to
    computing separation from object RA/Dec and observation center RA/Dec.
    """

    if not _valid_thresholds(
        centered_threshold_arcsec,
        nearby_threshold_arcsec,
        likely_out_of_frame_arcsec,
    ):
        raise ValueError("Target validation thresholds must be positive and increasing.")

    object_position = _extract_coordinates(
        object_coordinates,
        ra_keys=("ra_deg", "ra", "s_ra"),
        dec_keys=("dec_deg", "dec", "s_dec"),
    )
    if object_position is None:
        return TargetValidationResult(
            status=TargetValidationStatus.UNVERIFIED,
            confidence=0.0,
            distance_arcsec=None,
            target_in_frame=None,
            notes=("Missing or invalid requested object coordinates.",),
        )

    distance_arcsec = _extract_distance_arcsec(observation)
    notes: list[str] = []
    if distance_arcsec is not None:
        notes.append("Used archive-provided target distance metadata.")
    else:
        observation_position = _extract_coordinates(
            observation,
            ra_keys=("ra_deg", "s_ra", "ra", "obs_ra", "pointing_ra"),
            dec_keys=("dec_deg", "s_dec", "dec", "obs_dec", "pointing_dec"),
        )
        if observation_position is None:
            return TargetValidationResult(
                status=TargetValidationStatus.UNVERIFIED,
                confidence=0.0,
                distance_arcsec=None,
                target_in_frame=None,
                notes=(
                    "Missing observation center/distance metadata; target placement "
                    "cannot be validated.",
                ),
            )
        distance_arcsec = angular_separation_arcsec(object_position, observation_position)
        notes.append("Computed target distance from object and observation coordinates.")

    return _result_for_distance(
        distance_arcsec,
        centered_threshold_arcsec=centered_threshold_arcsec,
        nearby_threshold_arcsec=nearby_threshold_arcsec,
        likely_out_of_frame_arcsec=likely_out_of_frame_arcsec,
        notes=notes,
    )


def angular_separation_arcsec(
    first_coordinates: tuple[float, float],
    second_coordinates: tuple[float, float],
) -> float:
    """Return great-circle angular separation in arcseconds for two RA/Dec pairs."""

    first_ra, first_dec = first_coordinates
    second_ra, second_dec = second_coordinates
    first_ra_rad = radians(first_ra)
    first_dec_rad = radians(first_dec)
    second_ra_rad = radians(second_ra)
    second_dec_rad = radians(second_dec)

    delta_ra = second_ra_rad - first_ra_rad
    delta_dec = second_dec_rad - first_dec_rad
    haversine = (
        sin(delta_dec / 2.0) ** 2
        + cos(first_dec_rad) * cos(second_dec_rad) * sin(delta_ra / 2.0) ** 2
    )
    angle_rad = 2.0 * asin(min(1.0, sqrt(haversine)))
    return angle_rad * 206_264.80624709636


def _result_for_distance(
    distance_arcsec: float,
    *,
    centered_threshold_arcsec: float,
    nearby_threshold_arcsec: float,
    likely_out_of_frame_arcsec: float,
    notes: list[str],
) -> TargetValidationResult:
    if distance_arcsec <= centered_threshold_arcsec:
        return TargetValidationResult(
            status=TargetValidationStatus.CENTERED,
            confidence=0.95,
            distance_arcsec=distance_arcsec,
            target_in_frame=True,
            notes=tuple([*notes, "Target is within the centered threshold."]),
        )

    if distance_arcsec <= nearby_threshold_arcsec:
        span = nearby_threshold_arcsec - centered_threshold_arcsec
        normalized = (distance_arcsec - centered_threshold_arcsec) / span
        confidence = 0.9 - (0.25 * normalized)
        return TargetValidationResult(
            status=TargetValidationStatus.IN_FRAME,
            confidence=_clamp_confidence(confidence),
            distance_arcsec=distance_arcsec,
            target_in_frame=True,
            notes=tuple([*notes, "Target is near the observation center."]),
        )

    if distance_arcsec <= likely_out_of_frame_arcsec:
        span = likely_out_of_frame_arcsec - nearby_threshold_arcsec
        normalized = (distance_arcsec - nearby_threshold_arcsec) / span
        confidence = 0.55 - (0.2 * normalized)
        return TargetValidationResult(
            status=TargetValidationStatus.NEARBY_OFFSET,
            confidence=_clamp_confidence(confidence),
            distance_arcsec=distance_arcsec,
            target_in_frame=None,
            notes=tuple(
                [
                    *notes,
                    "Target is offset from center; footprint metadata is needed to confirm "
                    "frame coverage.",
                ]
            ),
        )

    return TargetValidationResult(
        status=TargetValidationStatus.OUT_OF_FRAME,
        confidence=0.1,
        distance_arcsec=distance_arcsec,
        target_in_frame=False,
        notes=tuple([*notes, "Target is far from the observation center."]),
    )


def _extract_coordinates(
    value: Any,
    *,
    ra_keys: tuple[str, ...],
    dec_keys: tuple[str, ...],
) -> tuple[float, float] | None:
    if isinstance(value, tuple | list) and len(value) >= 2:
        return _validated_coordinates(_safe_float(value[0]), _safe_float(value[1]))

    ra_value = _first_field_value(value, ra_keys)
    dec_value = _first_field_value(value, dec_keys)
    coordinates = _validated_coordinates(_safe_float(ra_value), _safe_float(dec_value))
    if coordinates is not None:
        return coordinates

    nested_coordinates = _field_value(value, "coordinates")
    if nested_coordinates is not None and nested_coordinates is not value:
        coordinates = _extract_coordinates(
            nested_coordinates,
            ra_keys=ra_keys,
            dec_keys=dec_keys,
        )
        if coordinates is not None:
            return coordinates

    raw_metadata = _raw_metadata(value)
    if raw_metadata is None:
        return None
    ra_value = _first_field_value(raw_metadata, ra_keys)
    dec_value = _first_field_value(raw_metadata, dec_keys)
    return _validated_coordinates(_safe_float(ra_value), _safe_float(dec_value))


def _extract_distance_arcsec(observation: Any) -> float | None:
    distance_arcsec = _first_float_field(
        observation,
        ("distance_arcsec", "separation_arcsec", "target_distance_arcsec"),
    )
    if distance_arcsec is not None and distance_arcsec >= 0.0:
        return distance_arcsec

    distance_degrees = _first_float_field(
        observation,
        ("distance_degrees", "distance_deg", "distance"),
    )
    if distance_degrees is not None and distance_degrees >= 0.0:
        return distance_degrees * 3600.0

    raw_metadata = _raw_metadata(observation)
    if raw_metadata is None:
        return None
    distance_arcsec = _first_float_field(
        raw_metadata,
        ("distance_arcsec", "separation_arcsec", "target_distance_arcsec"),
    )
    if distance_arcsec is not None and distance_arcsec >= 0.0:
        return distance_arcsec
    distance_degrees = _first_float_field(
        raw_metadata,
        ("distance_degrees", "distance_deg", "distance"),
    )
    if distance_degrees is not None and distance_degrees >= 0.0:
        return distance_degrees * 3600.0
    return None


def _valid_thresholds(
    centered_threshold_arcsec: float,
    nearby_threshold_arcsec: float,
    likely_out_of_frame_arcsec: float,
) -> bool:
    return (
        0.0 < centered_threshold_arcsec
        < nearby_threshold_arcsec
        < likely_out_of_frame_arcsec
    )


def _validated_coordinates(
    ra_deg: float | None,
    dec_deg: float | None,
) -> tuple[float, float] | None:
    if ra_deg is None or dec_deg is None:
        return None
    if not (0.0 <= ra_deg < 360.0 and -90.0 <= dec_deg <= 90.0):
        return None
    return (ra_deg, dec_deg)


def _first_float_field(value: Any, keys: tuple[str, ...]) -> float | None:
    return _safe_float(_first_field_value(value, keys))


def _first_field_value(value: Any, keys: tuple[str, ...]) -> Any:
    for key in keys:
        field_value = _field_value(value, key)
        if field_value is not None and field_value != "":
            return field_value
    return None


def _field_value(value: Any, key: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(key)
    return getattr(value, key, None)


def _raw_metadata(value: Any) -> Mapping[str, Any] | None:
    raw_metadata = _field_value(value, "raw_metadata")
    return raw_metadata if isinstance(raw_metadata, Mapping) else None


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, value))


__all__ = [
    "CENTERED_THRESHOLD_ARCSEC",
    "LIKELY_OUT_OF_FRAME_ARCSEC",
    "NEARBY_THRESHOLD_ARCSEC",
    "TargetValidationResult",
    "TargetValidationStatus",
    "angular_separation_arcsec",
    "validate_observation_target",
]
