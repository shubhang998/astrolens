"""Search route."""

from uuid import uuid4

from fastapi import APIRouter, Query

from astrolens.core.enums import CacheStatus
from astrolens.core.models import CacheMeta, ResponseMeta, SearchResponse, SearchResult
from astrolens.services.repository import repository

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(min_length=1), limit: int = Query(default=10, ge=1, le=25)
) -> SearchResponse:
    objects = repository.find_objects(q, limit=limit)
    results = [
        SearchResult(
            id=obj.id,
            type="celestial_object",
            title=obj.name,
            url=f"/v1/objects/{obj.id}",
            snippet=(
                f"{obj.name} is curated as a {obj.type}; "
                f"aliases include {', '.join(obj.aliases[:3])}."
            ),
        )
        for obj in objects
    ]
    return SearchResponse(
        results=results,
        meta=ResponseMeta(
            request_id=f"req_{uuid4().hex}",
            cache=CacheMeta(status=CacheStatus.HIT, stale=False),
        ),
    )
