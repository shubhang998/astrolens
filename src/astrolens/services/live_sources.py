"""Source selection and bundle merging for live evidence requests."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from astrolens.core.enums import BandFamily, CacheStatus, VisualMode
from astrolens.core.errors import AstroLensError
from astrolens.core.models import (
    CacheMeta,
    CelestialObject,
    Coordinates,
    CrossWavelengthNote,
    EvidenceBundle,
    ResponseMeta,
    View,
    WarningMessage,
)
from astrolens.services.composites import (
    CompositeService,
    composite_service,
    recipe_for_object_type,
)
from astrolens.services.facts import (
    FactsCompilerService,
    ObjectFactsResult,
    facts_compiler_service,
)
from astrolens.services.live_evidence import LiveEvidenceService, live_evidence_service
from astrolens.services.live_ingestion import LiveIngestionService, live_ingestion_service
from astrolens.services.ranking import rank_views_by_source_quality
from astrolens.services.repository import repository
from astrolens.services.skyview_evidence import SkyViewEvidenceService, skyview_evidence_service
from astrolens.services.target_validation import is_ephemeris_target
from astrolens.services.visual_modes import visual_mode_preset

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
        facts: FactsCompilerService = facts_compiler_service,
        resolver: LiveIngestionService = live_ingestion_service,
        composites: CompositeService = composite_service,
    ) -> None:
        self.mast = mast
        self.skyview = skyview
        self.facts = facts
        self.resolver = resolver
        self.composites = composites

    async def bundle_for_query(
        self,
        query: str,
        *,
        bands: list[BandFamily] | None = None,
        max_views: int = 6,
        visual_mode: VisualMode | str | None = VisualMode.CONTEXT,
        radius_deg: float | None = None,
        missions: tuple[str, ...] = ("HST", "JWST"),
        rank_mode: str = "best_visual",
        sources: tuple[str, ...] = DEFAULT_LIVE_SOURCES,
        skyview_surveys: list[str] | None = None,
        pixels: int | None = None,
        include_facts: bool = False,
        composite: bool = False,
        size: str = "standard",
    ) -> EvidenceBundle:
        facts_task = (
            asyncio.ensure_future(self._facts_for_query(query)) if include_facts else None
        )
        try:
            bundle = await self._source_bundle(
                query,
                bands=bands,
                max_views=max_views,
                visual_mode=visual_mode,
                radius_deg=radius_deg,
                missions=missions,
                rank_mode=rank_mode,
                sources=sources,
                skyview_surveys=skyview_surveys,
                pixels=pixels,
                size=size,
            )
            if composite:
                bundle = await self._with_composite_view(bundle, size=size)
        except BaseException:
            if facts_task is not None:
                facts_task.cancel()
            raise
        if facts_task is None:
            return bundle
        facts_result = await facts_task
        return bundle.model_copy(
            update={
                "object_facts": facts_result.facts,
                "fact_citations": facts_result.citations,
                "warnings": [*bundle.warnings, *facts_result.warnings],
            }
        )

    async def _ephemeris_bundle(
        self,
        query: str,
        *,
        bands: list[BandFamily] | None,
        max_views: int,
        missions: tuple[str, ...],
        rank_mode: str,
        skyview_requested: bool,
    ) -> EvidenceBundle:
        """Route moving targets through MAST target-name matching.

        Fixed-coordinate sky surveys cannot be cone-searched for solar-system
        bodies, so SkyView is excluded with a teaching warning instead of
        returning imagery of the wrong star field.
        """

        matches = repository.find_objects(query, limit=1)
        obj = (
            matches[0]
            if matches and matches[0].ephemeris_object
            else _minimal_ephemeris_object(query)
        )
        bundle = await self.mast.bundle_for_target_name(
            obj,
            bands=bands,
            max_views=max_views,
            missions=missions,
            rank_mode=rank_mode,
        )
        warnings = list(bundle.warnings)
        warnings.append(
            WarningMessage(
                code="EPHEMERIS_TARGET_NAME_SEARCH",
                message=(
                    f"{obj.name} is a moving target with no fixed sky coordinates; "
                    "observations were matched by archive target name instead of a "
                    "coordinate cone search."
                ),
                source="AstroLens",
                retryable=False,
            )
        )
        if skyview_requested:
            warnings.append(
                WarningMessage(
                    code="EPHEMERIS_SKYVIEW_EXCLUDED",
                    message=(
                        "SkyView survey cutouts were skipped: fixed-sky surveys "
                        f"cannot image the moving target {obj.name}."
                    ),
                    source="SkyView",
                    retryable=False,
                )
            )
        return bundle.model_copy(update={"warnings": warnings})

    async def _with_composite_view(
        self, bundle: EvidenceBundle, *, size: str = "standard"
    ) -> EvidenceBundle:
        """Prepend a cross-source composite view when the recipe can be filled."""

        recipe = recipe_for_object_type(bundle.object.type)
        try:
            composite_view = await self.composites.composite_view(
                obj=bundle.object,
                views=bundle.views,
                recipe=recipe,
                size=size,
            )
        except AstroLensError as exc:
            return bundle.model_copy(
                update={
                    "warnings": [
                        *bundle.warnings,
                        WarningMessage(
                            code="COMPOSITE_RENDER_FAILED",
                            message=f"Cross-source composite failed: {exc.message}",
                            source="AstroLens composite",
                            retryable=exc.retryable,
                        ),
                    ]
                }
            )
        if composite_view is None:
            return bundle.model_copy(
                update={
                    "warnings": [
                        *bundle.warnings,
                        WarningMessage(
                            code="COMPOSITE_UNAVAILABLE",
                            message=(
                                "Not enough renderable FITS bands were available for a "
                                f"cross-source composite (recipe {recipe.id})."
                            ),
                            source="AstroLens composite",
                            retryable=True,
                        ),
                    ]
                }
            )
        return bundle.model_copy(update={"views": [composite_view, *bundle.views]})

    async def _facts_for_query(self, query: str) -> ObjectFactsResult:
        """Resolve and compile facts; failures degrade to warnings, never errors."""

        # Curated objects (including solar-system bodies with curated fact
        # sheets) must not depend on live Sesame resolution.
        matches = repository.find_objects(query, limit=1)
        if matches:
            return await self.facts.facts_for_object(matches[0])
        try:
            live_object, _cache_status = await self.resolver.object_live(query)
        except AstroLensError as exc:
            return ObjectFactsResult(
                warnings=[
                    WarningMessage(
                        code="FACTS_RESOLUTION_FAILED",
                        message=f"Could not resolve '{query}' for fact compilation: "
                        f"{exc.message}",
                        source="CDS Sesame",
                        retryable=exc.retryable,
                    )
                ]
            )
        return await self.facts.facts_for_object(live_object)

    async def _source_bundle(
        self,
        query: str,
        *,
        bands: list[BandFamily] | None,
        max_views: int,
        visual_mode: VisualMode | str | None,
        radius_deg: float | None,
        missions: tuple[str, ...],
        rank_mode: str,
        sources: tuple[str, ...],
        skyview_surveys: list[str] | None,
        pixels: int | None,
        size: str = "standard",
    ) -> EvidenceBundle:
        normalized_sources = normalize_live_sources(sources)
        if is_ephemeris_target(query):
            return await self._ephemeris_bundle(
                query,
                bands=bands,
                max_views=max_views,
                missions=missions,
                rank_mode=rank_mode,
                skyview_requested="skyview" in normalized_sources,
            )
        preset = visual_mode_preset(visual_mode)
        mast_radius_deg = radius_deg if radius_deg is not None else preset.mast_radius_deg
        skyview_radius_deg = radius_deg if radius_deg is not None else preset.skyview_radius_deg
        skyview_pixels = pixels if pixels is not None else preset.pixels
        if normalized_sources == ("mast",):
            return await self.mast.bundle_for_query(
                query,
                bands=bands,
                max_views=max_views,
                radius_deg=mast_radius_deg,
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
                pixels=skyview_pixels,
                visual_mode=preset.mode,
                size=size,
            )

        mast_task = self.mast.bundle_for_query(
            query,
            bands=bands,
            max_views=max_views,
            radius_deg=mast_radius_deg,
            missions=missions,
            rank_mode=rank_mode,
        )
        skyview_task = self.skyview.bundle_for_query(
            query,
            bands=bands,
            max_views=max_views,
            radius_deg=skyview_radius_deg,
            surveys=skyview_surveys,
            pixels=skyview_pixels,
            visual_mode=preset.mode,
            size=size,
        )
        mast_result, skyview_result = await asyncio.gather(
            mast_task, skyview_task, return_exceptions=True
        )
        # One flaky archive must not zero out the whole bundle: keep whatever
        # source succeeded and report the other as a warning.
        bundles: list[EvidenceBundle] = []
        warnings: list[WarningMessage] = []
        for source_name, result in (("MAST", mast_result), ("SkyView", skyview_result)):
            if isinstance(result, EvidenceBundle):
                bundles.append(result)
                warnings.extend(result.warnings)
                continue
            if isinstance(result, AstroLensError):
                warnings.append(
                    WarningMessage(
                        code="LIVE_SOURCE_FAILED",
                        message=f"{source_name} evidence was skipped: {result.message}",
                        source=source_name,
                        retryable=result.retryable,
                    )
                )
                continue
            if isinstance(result, BaseException):
                raise result
        if not bundles:
            first_error = next(
                r for r in (mast_result, skyview_result) if isinstance(r, AstroLensError)
            )
            raise first_error
        views = rank_views_by_source_quality(
            [view for bundle in bundles for view in bundle.views],
            bands=bands,
            max_views=max_views,
        )
        notes = _notes_for_selected_views(
            [note for bundle in bundles for note in bundle.cross_wavelength_notes],
            views,
        )
        return EvidenceBundle(
            object=bundles[0].object,
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


def _minimal_ephemeris_object(query: str) -> CelestialObject:
    name = query.strip().title() or query
    slug = "".join(ch.lower() for ch in query.strip() if ch.isalnum()) or "ephemeris"
    return CelestialObject(
        id=f"astro:object:{slug}",
        name=name,
        type="solar system body",
        coordinates=Coordinates(ra_deg=0.0, dec_deg=0.0),
        ephemeris_object=True,
    )


def normalize_live_sources(sources: tuple[str, ...] | list[str] | str | None) -> tuple[str, ...]:
    if sources is None:
        return DEFAULT_LIVE_SOURCES
    if isinstance(sources, str):
        requested = [item.strip().lower() for item in sources.split(",") if item.strip()]
    else:
        requested = [str(item).strip().lower() for item in sources if str(item).strip()]
    normalized = tuple(source for source in requested if source in LIVE_SOURCES)
    return normalized or DEFAULT_LIVE_SOURCES


live_source_evidence_service = LiveSourceEvidenceService()
