"""Pure visual quality heuristics for archive product selection.

These helpers keep source-product ranking policy explicit without depending on
connector or API models. Integration layers can pass a model object, mapping, or
keyword fields that expose product filename, project, description, and related
provenance metadata.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class VisualQualityTier(IntEnum):
    """Ordered production-quality tiers for display-oriented source products."""

    RAW_PREVIEW = 100
    PROCESSED_ARCHIVE_PRODUCT = 200
    HLA_HLSP_HAP_COLOR_COMPOSITE = 300
    ASTROLENS_RENDERED = 400
    OUTREACH_RELEASE = 500


@dataclass(frozen=True, slots=True)
class VisualProductMetadata:
    """Small, dependency-light product description used by the quality helper."""

    product_filename: str | None = None
    project: str | None = None
    description: str | None = None
    product_type: str | None = None
    file_format: str | None = None
    calibration_level: str | None = None
    data_uri: str | None = None
    source: str | None = None
    raw_metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class VisualQualityAssessment:
    """Deterministic assessment for visual product ranking and provenance."""

    tier: VisualQualityTier
    score: int
    provenance_label: str
    reasons: tuple[str, ...] = ()
    penalties: tuple[str, ...] = ()
    is_color_or_composite: bool = False
    is_single_filter_jwst_preview: bool = False
    is_detector_panel_preview: bool = False


_RAW_KEYS = (
    "dataURI",
    "description",
    "obs_collection",
    "productFilename",
    "productGroupDescription",
    "productSubGroupDescription",
    "project",
    "proposal_type",
    "instrument_name",
)

_PROVENANCE_LABELS = {
    VisualQualityTier.OUTREACH_RELEASE: "outreach/release image",
    VisualQualityTier.ASTROLENS_RENDERED: "AstroLens rendered asset",
    VisualQualityTier.HLA_HLSP_HAP_COLOR_COMPOSITE: "HLA/HLSP/HAP color composite",
    VisualQualityTier.PROCESSED_ARCHIVE_PRODUCT: "processed archive product",
    VisualQualityTier.RAW_PREVIEW: "raw archive preview",
}


def assess_visual_quality(
    product: object | None = None,
    **fields: object,
) -> VisualQualityAssessment:
    """Classify and score one visual product candidate.

    Higher scores are better. The coarse tier ladder intentionally dominates
    small feature bonuses so a public outreach/release image beats AstroLens
    renders, AstroLens renders beat HLA/HLSP/HAP composites, and so on.
    """

    metadata = _coerce_metadata(product, fields)
    text = _metadata_text(metadata)
    reasons: list[str] = []
    penalties: list[str] = []

    is_outreach = _has_outreach_marker(text)
    is_astrolens_rendered = _has_astrolens_rendered_marker(text)
    is_color_or_composite = _has_color_or_composite_marker(text)
    is_archive_program = _has_archive_program_marker(text)
    is_processed = _has_processed_marker(text) or _calibration_level(metadata) >= 2
    is_raw = _has_raw_marker(text)
    is_preview = _has_preview_marker(text, metadata)
    is_single_filter_jwst_preview = _is_single_filter_jwst_preview(text, metadata)
    is_detector_panel_preview = _is_detector_panel_preview(text, is_single_filter_jwst_preview)

    if is_outreach:
        tier = VisualQualityTier.OUTREACH_RELEASE
        reasons.append("outreach_release")
    elif is_astrolens_rendered:
        tier = VisualQualityTier.ASTROLENS_RENDERED
        reasons.append("astrolens_rendered")
    elif is_archive_program and is_color_or_composite:
        tier = VisualQualityTier.HLA_HLSP_HAP_COLOR_COMPOSITE
        reasons.append("hla_hlsp_hap_color_composite")
    elif (is_processed or is_archive_program) and not is_raw:
        tier = VisualQualityTier.PROCESSED_ARCHIVE_PRODUCT
        reasons.append("processed_archive_product")
    else:
        tier = VisualQualityTier.RAW_PREVIEW
        reasons.append("raw_preview")

    score = int(tier)
    if is_color_or_composite:
        score += 35
        reasons.append("color_or_composite")
    if is_archive_program:
        score += 20
        reasons.append("hla_hlsp_hap_provenance")
    if is_processed:
        score += 15
        reasons.append("processed_product_marker")
    if is_preview:
        score += 3
        reasons.append("renderable_preview")

    calibration = _calibration_level(metadata)
    if calibration >= 3:
        score += 8
        reasons.append("high_calibration_level")
    elif calibration >= 2:
        score += 4
        reasons.append("calibrated_product")

    if is_raw:
        score -= 40
        penalties.append("raw_product_marker")
    if is_single_filter_jwst_preview:
        score -= 60
        penalties.append("jwst_single_filter_preview")
    if is_detector_panel_preview:
        score -= 35
        penalties.append("detector_panel_preview")

    return VisualQualityAssessment(
        tier=tier,
        score=max(score, 0),
        provenance_label=_PROVENANCE_LABELS[tier],
        reasons=tuple(dict.fromkeys(reasons)),
        penalties=tuple(dict.fromkeys(penalties)),
        is_color_or_composite=is_color_or_composite,
        is_single_filter_jwst_preview=is_single_filter_jwst_preview,
        is_detector_panel_preview=is_detector_panel_preview,
    )


def visual_quality_sort_key(product: object) -> tuple[int, int, str]:
    """Return a stable key where larger values indicate better visual candidates."""

    assessment = assess_visual_quality(product)
    metadata = _coerce_metadata(product, {})
    return (assessment.score, int(assessment.tier), _stable_product_name(metadata))


def choose_preferred_visual_product[T](products: Iterable[T]) -> T | None:
    """Return the highest-quality product candidate, preserving the original object."""

    best_product: T | None = None
    best_key: tuple[int, int, str] | None = None
    for product in products:
        key = visual_quality_sort_key(product)
        if best_key is None or key > best_key:
            best_key = key
            best_product = product
    return best_product


def _coerce_metadata(
    product: object | None,
    fields: Mapping[str, object],
) -> VisualProductMetadata:
    if isinstance(product, VisualProductMetadata) and not fields:
        return product

    raw_metadata = _read_field(product, fields, "raw_metadata")
    raw_mapping = raw_metadata if isinstance(raw_metadata, Mapping) else None
    return VisualProductMetadata(
        product_filename=_string_field(
            _read_field(product, fields, "product_filename")
            or _raw_value(raw_mapping, "productFilename")
        ),
        project=_string_field(
            _read_field(product, fields, "project") or _raw_value(raw_mapping, "project")
        ),
        description=_string_field(
            _read_field(product, fields, "description") or _raw_value(raw_mapping, "description")
        ),
        product_type=_string_field(_read_field(product, fields, "product_type")),
        file_format=_string_field(_read_field(product, fields, "file_format")),
        calibration_level=_string_field(_read_field(product, fields, "calibration_level")),
        data_uri=_string_field(
            _read_field(product, fields, "data_uri") or _raw_value(raw_mapping, "dataURI")
        ),
        source=_string_field(_read_field(product, fields, "source")),
        raw_metadata=raw_mapping,
    )


def _read_field(product: object | None, fields: Mapping[str, object], name: str) -> object | None:
    if name in fields:
        return fields[name]
    if product is None:
        return None
    if isinstance(product, Mapping):
        return product.get(name)
    return getattr(product, name, None)


def _string_field(value: object | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _raw_value(raw_metadata: Mapping[str, Any] | None, key: str) -> object | None:
    if raw_metadata is None:
        return None
    return raw_metadata.get(key)


def _metadata_text(metadata: VisualProductMetadata) -> str:
    pieces: list[str] = [
        item
        for item in (
            metadata.product_filename,
            metadata.project,
            metadata.description,
            metadata.product_type,
            metadata.file_format,
            metadata.calibration_level,
            metadata.data_uri,
            metadata.source,
        )
        if item
    ]
    if metadata.raw_metadata:
        pieces.extend(
            str(metadata.raw_metadata[key]) for key in _RAW_KEYS if key in metadata.raw_metadata
        )
    return " ".join(pieces).lower()


def _stable_product_name(metadata: VisualProductMetadata) -> str:
    return metadata.product_filename or metadata.data_uri or metadata.description or ""


def _has_outreach_marker(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "apod",
            "esa hubble image",
            "hubble heritage",
            "image release",
            "news release",
            "outreach",
            "photo release",
            "press release",
            "release image",
            "stsci image release",
        )
    )


def _has_astrolens_rendered_marker(text: str) -> bool:
    return "astrolens" in text and any(
        marker in text for marker in ("generated", "render", "rendered", "science-ready")
    )


def _has_archive_program_marker(text: str) -> bool:
    return bool(
        re.search(r"(?<![a-z0-9])(hla|hlsp|hap)(?![a-z0-9])", text)
        or "high level science product" in text
        or "high-level science product" in text
        or "hubble advanced product" in text
    )


def _has_color_or_composite_marker(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "3-color",
            "color",
            "colour",
            "composite",
            "drc_color",
            "rgb",
            "three-color",
            "tricolor",
        )
    )


def _has_processed_marker(text: str) -> bool:
    return bool(
        re.search(
            r"(?<![a-z0-9])(calibrated|coadd|combined|drc|drw|drz|i2d|mosaic|total)"
            r"(?![a-z0-9])",
            text,
        )
        or "caljwst" in text
        or "level 3" in text
        or "level-3" in text
    )


def _has_raw_marker(text: str) -> bool:
    return bool(re.search(r"(?<![a-z0-9])(raw|uncal)(?![a-z0-9])", text))


def _has_preview_marker(text: str, metadata: VisualProductMetadata) -> bool:
    product_type = str(metadata.product_type or "").lower()
    file_format = str(metadata.file_format or "").lower()
    return (
        "preview" in product_type
        or "preview" in text
        or file_format in {"gif", "jpeg", "jpg", "png"}
    )


def _calibration_level(metadata: VisualProductMetadata) -> float:
    if metadata.calibration_level is None:
        return 0.0
    try:
        return float(metadata.calibration_level)
    except ValueError:
        return 0.0


def _is_single_filter_jwst_preview(text: str, metadata: VisualProductMetadata) -> bool:
    if not _has_preview_marker(text, metadata):
        return False
    if not any(marker in text for marker in ("jwst", "nircam", "niriss", "miri", "caljwst")):
        return False
    if _has_color_or_composite_marker(text):
        return False
    return len(set(re.findall(r"(?<![a-z0-9])f\d{3,4}[a-z]?(?![a-z0-9])", text))) == 1


def _is_detector_panel_preview(text: str, is_single_filter_jwst_preview: bool) -> bool:
    if not is_single_filter_jwst_preview:
        return False
    return any(
        marker in text
        for marker in (
            "_nrca",
            "_nrcb",
            "detector",
            "nircam",
            "nrcalong",
            "nrcblong",
            "panel",
        )
    )
