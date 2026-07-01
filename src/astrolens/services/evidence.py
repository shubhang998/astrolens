"""Evidence bundle assembly service."""

from uuid import uuid4

from astrolens.core.enums import BandFamily, CacheStatus
from astrolens.core.models import (
    CacheMeta,
    CompareResponse,
    CrossWavelengthNote,
    EvidenceBundle,
    ResponseMeta,
    WavelengthComparison,
)
from astrolens.data.seed import BAND_NOTES, DEFAULT_CACHE
from astrolens.services.ranking import rank_views
from astrolens.services.repository import EvidenceRepository, repository
from astrolens.services.resolver import ResolverService, resolver_service


class EvidenceService:
    """Build compact, source-grounded evidence responses."""

    def __init__(
        self,
        repo: EvidenceRepository = repository,
        resolver: ResolverService = resolver_service,
    ) -> None:
        self.repo = repo
        self.resolver = resolver

    def bundle_for_query(
        self,
        query: str,
        *,
        bands: list[BandFamily] | None = None,
        max_views: int = 6,
    ) -> EvidenceBundle:
        resolved = self.resolver.resolve(query)
        if not resolved.object_id:
            # Ambiguous responses are returned by resolver endpoint; evidence requires certainty.
            first = resolved.ambiguity.alternatives[0] if resolved.ambiguity.alternatives else None
            object_id = first.id if first else query
        else:
            object_id = resolved.object_id
        return self.bundle_for_object(object_id, bands=bands, max_views=max_views)

    def bundle_for_object(
        self,
        object_id: str,
        *,
        bands: list[BandFamily] | None = None,
        max_views: int = 6,
    ) -> EvidenceBundle:
        obj = self.repo.get_object(object_id)
        views = rank_views(
            self.repo.views_for_object(object_id, bands), bands=bands, max_views=max_views
        )
        notes = self._notes_for_views(views, bands)
        return EvidenceBundle(
            object=obj,
            views=views,
            cross_wavelength_notes=notes,
            warnings=[],
            meta=ResponseMeta(request_id=f"req_{uuid4().hex}", cache=DEFAULT_CACHE),
        )

    def compare(
        self,
        query: str,
        *,
        bands: list[BandFamily],
        max_views_per_band: int = 1,
    ) -> CompareResponse:
        bundle = self.bundle_for_query(
            query, bands=bands, max_views=len(bands) * max_views_per_band
        )
        comparison: list[WavelengthComparison] = []
        for band in bands:
            views = [view for view in bundle.views if view.band_family == band]
            if not views:
                note = BAND_NOTES.get(
                    band,
                    CrossWavelengthNote(
                        band_family=band,
                        general_meaning="No curated AstroLens view is available for this band yet.",
                        confidence=0.5,
                    ),
                )
                comparison.append(
                    WavelengthComparison(
                        band_family=band,
                        general_interpretation=note.general_meaning,
                        caveats=["No curated view for this wavelength is currently available."],
                    )
                )
                continue
            for view in views[:max_views_per_band]:
                note = BAND_NOTES.get(view.band_family)
                comparison.append(
                    WavelengthComparison(
                        band_family=view.band_family,
                        view_id=view.id,
                        facility=view.facility,
                        asset_id=view.asset.id if view.asset else None,
                        general_interpretation=note.general_meaning if note else view.label,
                        citations=view.citations,
                        caveats=view.caveats,
                    )
                )
        return CompareResponse(
            object=bundle.object,
            comparison=comparison,
            caveats=[
                "Different wavelength views may not be simultaneous.",
                "Images can use different resolutions, fields of view, and color mappings.",
            ],
            meta=ResponseMeta(
                request_id=f"req_{uuid4().hex}",
                cache=CacheMeta(status=CacheStatus.HIT, stale=False),
            ),
        )

    def _notes_for_views(
        self,
        views: list,
        bands: list[BandFamily] | None,
    ) -> list[CrossWavelengthNote]:
        note_bands = set(bands or [view.band_family for view in views])
        return [BAND_NOTES[band] for band in note_bands if band in BAND_NOTES]


evidence_service = EvidenceService()
