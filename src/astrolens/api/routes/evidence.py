"""Evidence routes."""

from fastapi import APIRouter, Query

from astrolens.core.enums import BandFamily
from astrolens.core.models import EvidenceBundle
from astrolens.services.evidence import evidence_service
from astrolens.services.live_evidence import live_evidence_service

router = APIRouter(tags=["evidence"])


def parse_bands(bands: str | None) -> list[BandFamily] | None:
    if not bands:
        return None
    return [BandFamily(item.strip()) for item in bands.split(",") if item.strip()]


def parse_missions(missions: str | None) -> tuple[str, ...]:
    if not missions:
        return ("HST", "JWST")
    parsed = tuple(item.strip().upper() for item in missions.split(",") if item.strip())
    return parsed or ("HST", "JWST")


@router.get("/evidence", response_model=EvidenceBundle)
async def get_evidence(
    q: str = Query(min_length=1),
    bands: str | None = None,
    max_views: int = Query(default=6, ge=1, le=12),
    live: bool = False,
    radius_deg: float = Query(default=0.03, gt=0.0, le=0.25),
    missions: str | None = None,
    rank_mode: str = Query(default="best_visual"),
) -> EvidenceBundle:
    if live:
        return await live_evidence_service.bundle_for_query(
            q,
            bands=parse_bands(bands),
            max_views=max_views,
            radius_deg=radius_deg,
            missions=parse_missions(missions),
            rank_mode=rank_mode,
        )
    return evidence_service.bundle_for_query(q, bands=parse_bands(bands), max_views=max_views)


@router.get("/objects/{object_id}/evidence", response_model=EvidenceBundle)
async def get_object_evidence(
    object_id: str,
    bands: str | None = None,
    max_views: int = Query(default=6, ge=1, le=12),
) -> EvidenceBundle:
    return evidence_service.bundle_for_object(
        object_id, bands=parse_bands(bands), max_views=max_views
    )
