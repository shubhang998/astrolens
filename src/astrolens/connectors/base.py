"""Common connector protocol for source archive adapters.

Connectors isolate AstroLens from archive-specific APIs. They normalize source
records into typed candidates, preserve raw source metadata, and never write to
the database or decide final ranking.
"""

from datetime import datetime
from typing import Any, Protocol

from pydantic import Field

from astrolens.core.enums import AccessStatus, BandFamily
from astrolens.core.errors import UnsupportedConnectorOperation
from astrolens.core.models import AstroLensModel, Citation, Coordinates, PublicUrl, SourceHealth


class SkyRegion(AstroLensModel):
    """Simple circular sky region for V1 connector search contracts."""

    center: Coordinates
    radius_arcmin: float = Field(gt=0.0)


class ObservationFilters(AstroLensModel):
    """Common filters passed to source observation searches."""

    bands: list[BandFamily] = Field(default_factory=list)
    public_only: bool = True
    limit: int = Field(default=20, ge=1, le=100)


class ResolvedObjectCandidate(AstroLensModel):
    """Normalized object-resolution candidate from an identity source."""

    name: str
    aliases: list[str] = Field(default_factory=list)
    object_type: str = "unknown"
    ra_deg: float = Field(ge=0.0, lt=360.0)
    dec_deg: float = Field(ge=-90.0, le=90.0)
    frame: str = "ICRS"
    source: str
    source_url: PublicUrl | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class ObservationCandidate(AstroLensModel):
    """Normalized observation candidate from an archive connector."""

    source_archive: str
    facility: str | None = None
    instrument: str | None = None
    band_family: BandFamily = BandFamily.UNKNOWN
    observation_date: datetime | None = None
    access_status: AccessStatus = AccessStatus.UNKNOWN
    source_record_id: str
    source_url: PublicUrl | None = None
    region: SkyRegion | None = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class ProductCandidate(AstroLensModel):
    """Normalized source product candidate."""

    product_type: str
    file_format: str | None = None
    download_url: PublicUrl | None = None
    preview_url: PublicUrl | None = None
    calibration_level: str | None = None
    file_size_mb: float | None = Field(default=None, ge=0.0)
    source_record_id: str
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class ArchiveConnector(Protocol):
    """Common protocol every archive connector should satisfy."""

    name: str

    async def healthcheck(self) -> SourceHealth:
        """Return connector health without raising raw source errors."""
        ...

    async def resolve_object(self, query: str) -> list[ResolvedObjectCandidate]:
        """Resolve an object query when meaningful for this source."""
        raise UnsupportedConnectorOperation(self.name, "resolve_object")

    async def search_observations(
        self,
        region: SkyRegion,
        filters: ObservationFilters,
    ) -> list[ObservationCandidate]:
        """Search observations in a sky region when meaningful for this source."""
        raise UnsupportedConnectorOperation(self.name, "search_observations")

    async def list_products(self, observation_id: str) -> list[ProductCandidate]:
        """List products for a source observation ID."""
        raise UnsupportedConnectorOperation(self.name, "list_products")

    async def get_citation(self, source_record_id: str) -> Citation:
        """Fetch or construct citation metadata for a source record."""
        raise UnsupportedConnectorOperation(self.name, "get_citation")
