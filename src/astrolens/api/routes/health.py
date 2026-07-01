"""Health routes for the AstroLens API."""

from fastapi import APIRouter

from astrolens.core.models import HealthResponse, SourceHealthResponse
from astrolens.services.sources import source_health_service

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Return basic API health."""

    return HealthResponse(status="ok")


@router.get("/sources/health", response_model=SourceHealthResponse)
async def sources_health() -> SourceHealthResponse:
    """Return configured source health."""

    return await source_health_service.source_health()
