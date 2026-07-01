"""Wavelength comparison route."""

from fastapi import APIRouter

from astrolens.core.models import CompareRequest, CompareResponse
from astrolens.services.evidence import evidence_service

router = APIRouter(tags=["compare"])


@router.post("/compare", response_model=CompareResponse)
async def compare(request: CompareRequest) -> CompareResponse:
    return evidence_service.compare(
        request.object,
        bands=request.bands,
        max_views_per_band=request.max_views_per_band,
    )
