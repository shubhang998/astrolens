"""Asset and raw-link routes."""

from fastapi import APIRouter

from astrolens.core.models import AssetResponse, CitationsResponse, RawLinksResponse
from astrolens.services.assets import asset_service

router = APIRouter(tags=["assets"])


@router.get("/assets/{asset_id}", response_model=AssetResponse)
async def get_asset(asset_id: str) -> AssetResponse:
    return asset_service.get_asset(asset_id)


@router.get("/assets/{asset_id}/citations", response_model=CitationsResponse)
async def get_asset_citations(asset_id: str) -> CitationsResponse:
    return asset_service.get_asset_citations(asset_id)


@router.get("/products/{product_id}/raw-links", response_model=RawLinksResponse)
async def get_raw_links(product_id: str) -> RawLinksResponse:
    return asset_service.get_product_raw_links(product_id)
