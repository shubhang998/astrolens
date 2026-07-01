"""Source health service."""

import asyncio
from uuid import uuid4

from astrolens.connectors.registry import CONNECTORS
from astrolens.core.enums import CacheStatus, SourceHealthStatus
from astrolens.core.models import CacheMeta, ResponseMeta, SourceHealth, SourceHealthResponse


class SourceHealthService:
    """Aggregate source connector health."""

    async def source_health(self) -> SourceHealthResponse:
        health_records: list[SourceHealth] = []
        for connector in CONNECTORS:
            try:
                health_records.append(await connector.healthcheck())
            except Exception:  # pragma: no cover - defensive boundary
                health_records.append(
                    SourceHealth(name=connector.name, status=SourceHealthStatus.UNAVAILABLE)
                )
        return SourceHealthResponse(
            sources=health_records,
            meta=ResponseMeta(
                request_id=f"req_{uuid4().hex}",
                cache=CacheMeta(status=CacheStatus.HIT, stale=False),
            ),
        )

    def source_health_sync(self) -> SourceHealthResponse:
        return asyncio.run(self.source_health())


source_health_service = SourceHealthService()
