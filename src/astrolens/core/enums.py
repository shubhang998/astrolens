"""Shared enum values for public AstroLens contracts."""

from enum import StrEnum


class BandFamily(StrEnum):
    """Broad wavelength families used for agent-facing view selection."""

    RADIO = "radio"
    MILLIMETER = "millimeter"
    INFRARED = "infrared"
    VISIBLE = "visible"
    ULTRAVIOLET = "ultraviolet"
    XRAY = "xray"
    GAMMA = "gamma"
    MULTIWAVELENGTH = "multiwavelength"
    UNKNOWN = "unknown"


class AccessStatus(StrEnum):
    """Source product access state."""

    PUBLIC = "public"
    PROPRIETARY = "proprietary"
    RESTRICTED = "restricted"
    UNKNOWN = "unknown"


class ReuseStatus(StrEnum):
    """Conservative public reuse status for assets and facts."""

    USABLE_WITH_CREDIT = "usable_with_credit"
    PUBLIC_DOMAIN_OR_OPEN = "public_domain_or_open"
    CHECK_SOURCE_POLICY = "check_source_policy"
    RESTRICTED_OR_UNKNOWN = "restricted_or_unknown"
    TEMPORARY_PROPRIETARY = "temporary_proprietary"


class VisualAssetTier(StrEnum):
    """Trust/quality tier for an agent-facing image asset."""

    OUTREACH_RELEASE = "outreach_release"
    ASTROLENS_RENDERED = "astrolens_rendered"
    PROCESSED_ARCHIVE = "processed_archive"
    RAW_ARCHIVE_PREVIEW = "raw_archive_preview"
    UNKNOWN = "unknown"


class TargetValidationStatus(StrEnum):
    """How confidently an image product matches the requested sky target."""

    CENTERED = "centered"
    IN_FRAME = "in_frame"
    NEARBY_OFFSET = "nearby_offset"
    OUT_OF_FRAME = "out_of_frame"
    UNVERIFIED = "unverified"


class SourceHealthStatus(StrEnum):
    """Connector health state exposed to agents and API clients."""

    OK = "ok"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class CacheStatus(StrEnum):
    """Evidence/cache status for a response."""

    HIT = "hit"
    MISS = "miss"
    STALE = "stale"
    PARTIAL = "partial"


class ErrorCode(StrEnum):
    """Stable public error codes from the PRD."""

    OBJECT_NOT_FOUND = "OBJECT_NOT_FOUND"
    OBJECT_AMBIGUOUS = "OBJECT_AMBIGUOUS"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_TIMEOUT = "SOURCE_TIMEOUT"
    PRODUCT_NOT_PUBLIC = "PRODUCT_NOT_PUBLIC"
    PRODUCT_TOO_LARGE = "PRODUCT_TOO_LARGE"
    RENDER_NOT_SUPPORTED = "RENDER_NOT_SUPPORTED"
    RATE_LIMITED = "RATE_LIMITED"
    INVALID_COORDINATES = "INVALID_COORDINATES"
    UNSUPPORTED_BAND = "UNSUPPORTED_BAND"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    UNSUPPORTED_CONNECTOR_OPERATION = "UNSUPPORTED_CONNECTOR_OPERATION"


class JobStatus(StrEnum):
    """Async job lifecycle states."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"
