"""Health routes for the AstroLens API."""

from fastapi import APIRouter

from astrolens.core.models import HealthResponse, SourceHealthResponse, WarmerStatus
from astrolens.services.sources import source_health_service
from astrolens.services.warmer import warm_status, warming_enabled

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Return basic API health and cache-warmer progress."""

    warmer = None
    if warming_enabled() or warm_status.get("enabled"):
        warmer = WarmerStatus.model_validate(warm_status)
    return HealthResponse(status="ok", cache_warmer=warmer)


@router.get("/sources/health", response_model=SourceHealthResponse)
async def sources_health() -> SourceHealthResponse:
    """Return configured source health."""

    return await source_health_service.source_health()
