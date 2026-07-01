"""Source selection and bundle merging for live evidence requests."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from astrolens.core.enums import BandFamily, CacheStatus
from astrolens.core.models import CacheMeta, CrossWavelengthNote, EvidenceBundle, ResponseMeta, View
from astrolens.services.live_evidence import LiveEvidenceService, live_evidence_service
from astrolens.services.ranking import rank_views_by_source_quality
from astrolens.services.skyview_evidence import SkyViewEvidenceService, skyview_evidence_service

LIVE_SOURCES = {"mast", "skyview"}
DEFAULT_LIVE_SOURCES = ("mast",)
DEFAULT_MAST_RADIUS_DEG = 0.03
DEFAULT_SKYVIEW_RADIUS_DEG = 0.08


class LiveSourceEvidenceService:
    """Dispatch live evidence requests to one or more source-backed services."""

    def __init__(
        self,
        mast: LiveEvidenceService = live_evidence_service,
        skyview: SkyViewEvidenceService = skyview_evidence_service,
    ) -> None:
        self.mast = mast
        self.skyview = skyview

    async def bundle_for_query(
        self,
        query: str,
        *,
        bands: list[BandFamily] | None = None,
        max_views: int = 6,
        radius_deg: float = 0.03,
        missions: tuple[str, ...] = ("HST", "JWST"),
        rank_mode: str = "best_visual",
        sources: tuple[str, ...] = DEFAULT_LIVE_SOURCES,
        skyview_surveys: list[str] | None = None,
        pixels: int = 512,
    ) -> EvidenceBundle:
        normalized_sources = normalize_live_sources(sources)
        skyview_radius_deg = _skyview_radius(radius_deg)
        if normalized_sources == ("mast",):
            return await self.mast.bundle_for_query(
                query,
                bands=bands,
                max_views=max_views,
                radius_deg=radius_deg,
                missions=missions,
                rank_mode=rank_mode,
            )
        if normalized_sources == ("skyview",):
            return await self.skyview.bundle_for_query(
                query,
                bands=bands,
                max_views=max_views,
                radius_deg=skyview_radius_deg,
                surveys=skyview_surveys,
                pixels=pixels,
            )

        mast_task = self.mast.bundle_for_query(
            query,
            bands=bands,
            max_views=max_views,
            radius_deg=radius_deg,
            missions=missions,
            rank_mode=rank_mode,
        )
        skyview_task = self.skyview.bundle_for_query(
            query,
            bands=bands,
            max_views=max_views,
            radius_deg=skyview_radius_deg,
            surveys=skyview_surveys,
            pixels=pixels,
        )
        mast_bundle, skyview_bundle = await asyncio.gather(mast_task, skyview_task)
        views = rank_views_by_source_quality(
            [*mast_bundle.views, *skyview_bundle.views],
            bands=bands,
            max_views=max_views,
        )
        notes = _notes_for_selected_views(
            [*mast_bundle.cross_wavelength_notes, *skyview_bundle.cross_wavelength_notes],
            views,
        )
        warnings = [*mast_bundle.warnings, *skyview_bundle.warnings]
        return EvidenceBundle(
            object=mast_bundle.object,
            views=views,
            cross_wavelength_notes=notes,
            warnings=warnings,
            meta=ResponseMeta(
                request_id=f"req_{uuid4().hex}",
                cache=CacheMeta(
                    status=CacheStatus.PARTIAL if warnings else CacheStatus.MISS,
                    stale=False,
                ),
            ),
        )


def _notes_for_selected_views(
    notes: list[CrossWavelengthNote],
    views: list[View],
) -> list[CrossWavelengthNote]:
    """Keep one cross-wavelength note per band that actually survived ranking."""

    shown_bands = {view.band_family for view in views}
    by_band: dict[BandFamily, CrossWavelengthNote] = {}
    for note in notes:
        if note.band_family in shown_bands and note.band_family not in by_band:
            by_band[note.band_family] = note
    return list(by_band.values())


def normalize_live_sources(sources: tuple[str, ...] | list[str] | str | None) -> tuple[str, ...]:
    if sources is None:
        return DEFAULT_LIVE_SOURCES
    if isinstance(sources, str):
        requested = [item.strip().lower() for item in sources.split(",") if item.strip()]
    else:
        requested = [str(item).strip().lower() for item in sources if str(item).strip()]
    normalized = tuple(source for source in requested if source in LIVE_SOURCES)
    return normalized or DEFAULT_LIVE_SOURCES


def _skyview_radius(radius_deg: float) -> float:
    if abs(radius_deg - DEFAULT_MAST_RADIUS_DEG) < 0.000001:
        return DEFAULT_SKYVIEW_RADIUS_DEG
    return radius_deg


live_source_evidence_service = LiveSourceEvidenceService()
