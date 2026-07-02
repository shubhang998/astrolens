"""Object, views, and observations routes."""

from uuid import uuid4

from fastapi import APIRouter, Query

from astrolens.api.routes.evidence import parse_bands
from astrolens.core.enums import CacheStatus
from astrolens.core.models import (
    CacheMeta,
    ObjectDetailResponse,
    ObjectFactsResponse,
    ObservationsResponse,
    ResponseMeta,
    ViewsResponse,
)
from astrolens.services.facts import facts_compiler_service
from astrolens.services.ranking import rank_views
from astrolens.services.repository import repository

router = APIRouter(tags=["objects"])


def meta() -> ResponseMeta:
    return ResponseMeta(
        request_id=f"req_{uuid4().hex}", cache=CacheMeta(status=CacheStatus.HIT, stale=False)
    )


@router.get("/objects/{object_id}", response_model=ObjectDetailResponse)
async def get_object(object_id: str) -> ObjectDetailResponse:
    return ObjectDetailResponse(
        object=repository.get_object(object_id),
        observations=repository.observations_for_object(object_id),
        views=rank_views(repository.views_for_object(object_id)),
        meta=meta(),
    )


@router.get("/objects/{object_id}/observations", response_model=ObservationsResponse)
async def get_observations(
    object_id: str,
    bands: str | None = None,
    public_only: bool = True,
    limit: int = Query(default=20, ge=1, le=100),
) -> ObservationsResponse:
    del public_only
    observations = repository.observations_for_object(object_id, parse_bands(bands))[:limit]
    return ObservationsResponse(
        object=repository.get_object(object_id), observations=observations, meta=meta()
    )


@router.get("/objects/{object_id}/facts", response_model=ObjectFactsResponse)
async def get_object_facts(object_id: str) -> ObjectFactsResponse:
    obj = repository.get_object(object_id)
    result = await facts_compiler_service.facts_for_object(obj)
    return ObjectFactsResponse(
        object=obj,
        facts=result.facts,
        citations=result.citations,
        warnings=result.warnings,
        meta=meta(),
    )


@router.get("/objects/{object_id}/views", response_model=ViewsResponse)
async def get_views(
    object_id: str,
    bands: str | None = None,
    max: int = Query(default=6, ge=1, le=12),  # noqa: A002 - API param name from PRD
) -> ViewsResponse:
    parsed_bands = parse_bands(bands)
    views = rank_views(
        repository.views_for_object(object_id, parsed_bands), bands=parsed_bands, max_views=max
    )
    return ViewsResponse(object=repository.get_object(object_id), views=views, meta=meta())
