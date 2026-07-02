"""Limited live ingestion services."""

from typing import Protocol
from uuid import uuid4

from astrolens.connectors.base import ResolvedObjectCandidate
from astrolens.connectors.sesame import sesame_connector
from astrolens.core.enums import CacheStatus, ErrorCode
from astrolens.core.errors import AstroLensError
from astrolens.core.models import (
    Ambiguity,
    CacheMeta,
    CelestialObject,
    Coordinates,
    ResolveResponse,
    ResponseMeta,
    SourceReference,
)
from astrolens.services.repository import EvidenceRepository, normalize_query, repository


class LiveResolverConnector(Protocol):
    name: str

    async def resolve_object(self, query: str) -> list[ResolvedObjectCandidate]:
        """Resolve a query to live candidates."""
        ...


class LiveIngestionService:
    """Explicit opt-in live ingestion for object identity."""

    def __init__(
        self,
        repo: EvidenceRepository = repository,
        connector: LiveResolverConnector = sesame_connector,
    ) -> None:
        self.repo = repo
        self.connector = connector
        self.live_cache: dict[str, CelestialObject] = {}

    async def object_live(self, query: str) -> tuple[CelestialObject, CacheStatus]:
        cached = self.live_cache.get(normalize_query(query))
        if cached:
            return cached, CacheStatus.HIT

        candidates = await self.connector.resolve_object(query)
        if not candidates:
            raise AstroLensError(
                ErrorCode.OBJECT_NOT_FOUND,
                f"CDS Sesame did not resolve '{query}'.",
                details={"query": query, "source": self.connector.name},
            )
        candidate = candidates[0]
        live_object = self._candidate_to_object(candidate)
        self.live_cache[normalize_query(query)] = live_object
        return live_object, CacheStatus.MISS

    async def resolve_live(self, query: str) -> ResolveResponse:
        live_object, cache_status = await self.object_live(query)
        return self._response_for_object(live_object, cache_status=cache_status)

    def _candidate_to_object(self, candidate: ResolvedObjectCandidate) -> CelestialObject:
        source_url = str(candidate.source_url) if candidate.source_url else None
        slug = normalize_query(candidate.name) or candidate.raw_metadata.get("oid") or uuid4().hex
        # SIMBAD canonical names pad with alignment spaces ("M   1"); collapse
        # for display. Identity lookups already whitespace-collapse on retry.
        display_name = " ".join(candidate.name.split())
        return CelestialObject(
            id=f"astro:object:live:{slug}",
            name=display_name,
            aliases=candidate.aliases,
            type=candidate.object_type,
            coordinates=Coordinates(ra_deg=candidate.ra_deg, dec_deg=candidate.dec_deg),
            identity_sources=[
                SourceReference(name=candidate.source, url=source_url),
            ],
        )

    def _response_for_object(
        self,
        obj: CelestialObject,
        cache_status: CacheStatus,
    ) -> ResolveResponse:
        return ResolveResponse(
            object_id=obj.id,
            name=obj.name,
            aliases=obj.aliases,
            coordinates=obj.coordinates,
            confidence=0.95,
            ambiguity=Ambiguity(status="resolved", alternatives=[]),
            sources=obj.identity_sources,
            meta=ResponseMeta(
                request_id=f"req_{uuid4().hex}",
                cache=CacheMeta(status=cache_status, stale=False),
            ),
        )


live_ingestion_service = LiveIngestionService()
