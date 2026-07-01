"""V1 connector registry with deterministic health and fixture-backed shells."""

from datetime import UTC, datetime

from astrolens.connectors.base import ArchiveConnector
from astrolens.core.enums import SourceHealthStatus
from astrolens.core.models import SourceHealth


class SeedConnector(ArchiveConnector):
    """Read-only connector shell for a source represented by curated V1 seed data."""

    def __init__(self, name: str) -> None:
        self.name = name

    async def healthcheck(self) -> SourceHealth:
        return SourceHealth(
            name=self.name,
            status=SourceHealthStatus.OK,
            last_success_at=datetime.now(UTC),
            last_error_at=None,
            latency_ms=0,
        )


CONNECTORS: list[ArchiveConnector] = [
    SeedConnector("SIMBAD"),
    SeedConnector("NED"),
    SeedConnector("MAST"),
    SeedConnector("IRSA"),
    SeedConnector("SkyView"),
    SeedConnector("HEASARC"),
    SeedConnector("Chandra"),
    SeedConnector("ADS"),
]
