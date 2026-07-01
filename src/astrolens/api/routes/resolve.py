"""Object resolution route."""

from fastapi import APIRouter, Query

from astrolens.core.models import ResolveResponse
from astrolens.services.live_ingestion import live_ingestion_service
from astrolens.services.resolver import resolver_service

router = APIRouter(tags=["resolve"])


@router.get("/resolve", response_model=ResolveResponse)
async def resolve(q: str = Query(min_length=1), live: bool = False) -> ResolveResponse:
    if live:
        return await live_ingestion_service.resolve_live(q)
    return resolver_service.resolve(q)
