"""Object resolution service."""

from uuid import uuid4

from astrolens.core.enums import CacheStatus, ErrorCode
from astrolens.core.errors import AstroLensError
from astrolens.core.models import Ambiguity, CacheMeta, ResolveResponse, ResponseMeta
from astrolens.data.seed import DEFAULT_CACHE
from astrolens.services.repository import EvidenceRepository, repository


class ResolverService:
    """Resolve user names/aliases to curated AstroLens objects."""

    def __init__(self, repo: EvidenceRepository = repository) -> None:
        self.repo = repo

    def resolve(self, query: str) -> ResolveResponse:
        matches = self.repo.find_objects(query, limit=6)
        meta = ResponseMeta(request_id=f"req_{uuid4().hex}", cache=DEFAULT_CACHE)
        if not matches:
            raise AstroLensError(
                ErrorCode.OBJECT_NOT_FOUND,
                f"No curated AstroLens object matched '{query}'.",
                details={"query": query},
            )
        if len(matches) > 1:
            exact = [obj for obj in matches if obj.name.lower() == query.strip().lower()]
            if len(exact) != 1:
                return ResolveResponse(
                    object_id=None,
                    confidence=0.0,
                    ambiguity=Ambiguity(status="ambiguous", alternatives=matches),
                    sources=[],
                    meta=ResponseMeta(
                        request_id=meta.request_id,
                        cache=CacheMeta(status=CacheStatus.HIT, stale=False),
                    ),
                )
            resolved = exact[0]
        else:
            resolved = matches[0]
        return ResolveResponse(
            object_id=resolved.id,
            name=resolved.name,
            aliases=resolved.aliases,
            coordinates=resolved.coordinates,
            confidence=0.99,
            ambiguity=Ambiguity(status="resolved", alternatives=[]),
            sources=resolved.identity_sources,
            meta=meta,
        )


resolver_service = ResolverService()
