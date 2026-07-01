"""Typed public domain models for the AstroLens Evidence API."""

from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from astrolens.core.enums import (
    AccessStatus,
    BandFamily,
    CacheStatus,
    JobStatus,
    ReuseStatus,
    SourceHealthStatus,
    TargetValidationStatus,
    VisualAssetTier,
)

PublicUrl = Annotated[str, Field(pattern=r"^https?://")]


class AstroLensModel(BaseModel):
    """Base model with strict-ish API behavior and JSON-safe enum output."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class SourceReference(AstroLensModel):
    """Provenance pointer for a source record or policy page."""

    name: str
    url: PublicUrl | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Coordinates(AstroLensModel):
    """ICRS sky coordinates in degrees."""

    ra_deg: float = Field(ge=0.0, lt=360.0)
    dec_deg: float = Field(ge=-90.0, le=90.0)
    frame: str = "ICRS"


class ObjectAlias(AstroLensModel):
    """Known alias for a celestial object."""

    alias: str
    source: str
    confidence: float = Field(ge=0.0, le=1.0)


class CelestialObject(AstroLensModel):
    """Canonical resolved astronomical object."""

    id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    type: str = "unknown"
    coordinates: Coordinates
    identity_sources: list[SourceReference] = Field(default_factory=list)


class Observation(AstroLensModel):
    """Normalized telescope/archive observation record."""

    id: str
    object_id: str | None = None
    source_archive: str
    facility: str | None = None
    instrument: str | None = None
    band_family: BandFamily = BandFamily.UNKNOWN
    wavelength_min_nm: float | None = None
    wavelength_max_nm: float | None = None
    observation_date: datetime | None = None
    access_status: AccessStatus = AccessStatus.UNKNOWN
    proprietary_until: datetime | None = None
    source_url: PublicUrl | None = None
    source_record_id: str
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class Citation(AstroLensModel):
    """Citation and credit record for a public fact, asset, or source product."""

    id: str
    title: str
    source: str
    url: PublicUrl | None = None
    credit_text: str | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReusePolicy(AstroLensModel):
    """Conservative reuse and credit policy for an asset or source."""

    id: str
    status: ReuseStatus = ReuseStatus.RESTRICTED_OR_UNKNOWN
    commercial_use: str = "check_source_policy"
    credit_required: bool = True
    credit_text: str | None = None
    do_not_imply_endorsement: bool = True
    policy_url: PublicUrl | None = None
    notes: list[str] = Field(default_factory=list)


class TargetValidation(AstroLensModel):
    """Image/object alignment assessment used to avoid misleading visuals."""

    status: TargetValidationStatus = TargetValidationStatus.UNVERIFIED
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    distance_arcsec: float | None = Field(default=None, ge=0.0)
    target_in_frame: bool | None = None
    center_offset_fraction: float | None = Field(default=None, ge=0.0)
    notes: list[str] = Field(default_factory=list)


class ImageProvenance(AstroLensModel):
    """Traceability record for a selected or generated visual asset."""

    visual_tier: VisualAssetTier = VisualAssetTier.UNKNOWN
    source_archive: str | None = None
    facility: str | None = None
    instrument: str | None = None
    observation_id: str | None = None
    source_product_id: str | None = None
    source_record_id: str | None = None
    proposal_id: str | None = None
    filters: str | None = None
    calibration_level: str | None = None
    product_project: str | None = None
    product_description: str | None = None
    render_recipe_id: str | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    notes: list[str] = Field(default_factory=list)


class DataProduct(AstroLensModel):
    """A concrete source product such as a FITS file, spectrum, catalog row, or preview."""

    id: str
    observation_id: str | None = None
    product_type: str
    file_format: str | None = None
    calibration_level: str | None = None
    download_url: PublicUrl | None = None
    preview_url: PublicUrl | None = None
    file_size_mb: float | None = Field(default=None, ge=0.0)
    renderability_score: float | None = Field(default=None, ge=0.0, le=1.0)
    source_record_id: str | None = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class Asset(AstroLensModel):
    """Agent-usable preview, thumbnail, rendered image, or externally hosted asset."""

    id: str
    source_product_ids: list[str] = Field(default_factory=list)
    format: str
    visual_tier: VisualAssetTier = VisualAssetTier.UNKNOWN
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    asset_url: PublicUrl | None = None
    thumbnail_url: PublicUrl | None = None
    false_color: bool | None = None
    processing_note: str | None = None
    selection_reason: str | None = None
    target_validation: TargetValidation | None = None
    provenance: ImageProvenance | None = None
    credit_text: str | None = None
    reuse_policy_id: str
    citations: list[Citation] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Fact(AstroLensModel):
    """Small source-grounded claim that an agent can cite."""

    id: str
    entity_type: str
    entity_id: str
    claim: str
    scope: str
    confidence: float = Field(ge=0.0, le=1.0)
    citation_ids: list[str] = Field(default_factory=list)


class ViewScores(AstroLensModel):
    """Ranking components for a selected view."""

    object_match: float | None = Field(default=None, ge=0.0, le=1.0)
    public_access: float | None = Field(default=None, ge=0.0, le=1.0)
    asset_availability: float | None = Field(default=None, ge=0.0, le=1.0)
    preview_quality: float | None = Field(default=None, ge=0.0, le=1.0)
    science_ready: float | None = Field(default=None, ge=0.0, le=1.0)
    provenance_quality: float | None = Field(default=None, ge=0.0, le=1.0)
    citation_quality: float | None = Field(default=None, ge=0.0, le=1.0)
    renderability: float | None = Field(default=None, ge=0.0, le=1.0)
    source_reliability: float | None = Field(default=None, ge=0.0, le=1.0)
    overall: float = Field(ge=0.0)


class View(AstroLensModel):
    """Agent-facing evidence view for one wavelength/facility perspective."""

    id: str
    label: str
    band_family: BandFamily
    facility: str | None = None
    instrument: str | None = None
    source_archive: str
    asset: Asset | None = None
    raw_products: list[DataProduct] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    reuse: ReusePolicy
    citations: list[Citation] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    scores: ViewScores | None = None


class CrossWavelengthNote(AstroLensModel):
    """Compact interpretation helper for a wavelength family."""

    band_family: BandFamily
    general_meaning: str
    confidence: float = Field(ge=0.0, le=1.0)


class WarningMessage(AstroLensModel):
    """Structured warning for stale, partial, or source-degraded responses."""

    code: str
    message: str
    source: str | None = None
    stale: bool = False
    retryable: bool = False


class CacheMeta(AstroLensModel):
    """Cache metadata attached to API responses."""

    status: CacheStatus
    refreshed_at: datetime | None = None
    stale: bool = False


class ResponseMeta(AstroLensModel):
    """Common response metadata."""

    request_id: str
    cache: CacheMeta | None = None


class EvidenceBundle(AstroLensModel):
    """Main one-call evidence payload for agents and apps."""

    object: CelestialObject
    views: list[View] = Field(default_factory=list)
    cross_wavelength_notes: list[CrossWavelengthNote] = Field(default_factory=list)
    warnings: list[WarningMessage] = Field(default_factory=list)
    meta: ResponseMeta


class HealthResponse(AstroLensModel):
    """Basic service health response."""

    status: str = "ok"


class SourceHealth(AstroLensModel):
    """Per-source connector health exposed by `/v1/sources/health`."""

    name: str
    status: SourceHealthStatus = SourceHealthStatus.UNKNOWN
    last_success_at: datetime | None = None
    last_error_at: datetime | None = None
    latency_ms: int | None = Field(default=None, ge=0)


class SourceHealthResponse(AstroLensModel):
    """Container for source health records."""

    sources: list[SourceHealth] = Field(default_factory=list)
    meta: ResponseMeta


class Ambiguity(AstroLensModel):
    """Object resolution ambiguity status."""

    status: str = "resolved"
    alternatives: list[CelestialObject] = Field(default_factory=list)


class ResolveResponse(AstroLensModel):
    """Object resolution response."""

    object_id: str | None = None
    name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    coordinates: Coordinates | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    ambiguity: Ambiguity = Field(default_factory=Ambiguity)
    sources: list[SourceReference] = Field(default_factory=list)
    meta: ResponseMeta


class SearchResult(AstroLensModel):
    """Compact search result for objects, views, assets, or products."""

    id: str
    type: str
    title: str
    url: str | None = None
    snippet: str


class SearchResponse(AstroLensModel):
    """Search response."""

    results: list[SearchResult]
    meta: ResponseMeta


class ObjectDetailResponse(AstroLensModel):
    """Object detail response."""

    object: CelestialObject
    observations: list[Observation] = Field(default_factory=list)
    views: list[View] = Field(default_factory=list)
    meta: ResponseMeta


class ObservationsResponse(AstroLensModel):
    """Observation list response."""

    object: CelestialObject
    observations: list[Observation]
    meta: ResponseMeta


class ViewsResponse(AstroLensModel):
    """Ranked views response."""

    object: CelestialObject
    views: list[View]
    meta: ResponseMeta


class AssetResponse(AstroLensModel):
    """Asset detail response."""

    asset: Asset
    reuse: ReusePolicy
    citations: list[Citation]
    caveats: list[str] = Field(default_factory=list)
    meta: ResponseMeta


class CitationsResponse(AstroLensModel):
    """Citation list response."""

    citations: list[Citation]
    meta: ResponseMeta


class RawLink(AstroLensModel):
    """Raw archive/source link for a product."""

    label: str
    url: PublicUrl
    source: str
    product_id: str
    citation_ids: list[str] = Field(default_factory=list)


class RawLinksResponse(AstroLensModel):
    """Raw-link response for a product."""

    product: DataProduct
    raw_links: list[RawLink]
    citations: list[Citation]
    meta: ResponseMeta


class CompareRequest(AstroLensModel):
    """Request to compare selected wavelength families for an object."""

    object: str
    bands: list[BandFamily]
    max_views_per_band: int = Field(default=1, ge=1, le=3)


class WavelengthComparison(AstroLensModel):
    """One band comparison entry."""

    band_family: BandFamily
    view_id: str | None = None
    facility: str | None = None
    asset_id: str | None = None
    general_interpretation: str
    citations: list[Citation] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


class CompareResponse(AstroLensModel):
    """Wavelength comparison response."""

    object: CelestialObject
    comparison: list[WavelengthComparison]
    caveats: list[str] = Field(default_factory=list)
    meta: ResponseMeta


class RenderRequest(AstroLensModel):
    """Request to render or fetch a cached asset for a product."""

    product_id: str
    output_format: str = "png"
    size: str = "thumbnail"


class RenderJob(AstroLensModel):
    """Render job status."""

    id: str
    status: JobStatus
    product_id: str
    asset: Asset | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RenderResponse(AstroLensModel):
    """Render endpoint response."""

    status: str
    asset: Asset | None = None
    job_id: str | None = None
    poll_url: str | None = None
    error: str | None = None


class JobResponse(AstroLensModel):
    """Async job response."""

    job: RenderJob
    meta: ResponseMeta
