"""Hero orchestration for the two-job API: best picture and compiled facts.

All narrative fields (headline, why_interesting) are deterministic templates
over compiled ``Fact`` objects — never free-form model output.
"""

from __future__ import annotations

from typing import Any

from astrolens.connectors.simbad_tap import (
    SimbadTapConnector,
    otype_for_category,
    simbad_tap_connector,
)
from astrolens.core.enums import BandFamily, ErrorCode
from astrolens.core.errors import AstroLensError
from astrolens.core.models import CelestialObject, Fact, View
from astrolens.services.facts import (
    FactsCompilerService,
    ObjectFactsResult,
    facts_compiler_service,
)
from astrolens.services.live_ingestion import LiveIngestionService, live_ingestion_service
from astrolens.services.live_sources import (
    LiveSourceEvidenceService,
    live_source_evidence_service,
)
from astrolens.services.repository import repository

# How many candidate views to fetch/rank (the band recipe needs several to
# build a composite) versus how many images the widget actually shows.
MAX_PANELS = 4
MAX_SHOWN_IMAGES = 2
MAX_FIND_RESULTS = 10
MAX_FIND_RADIUS_DEG = 15.0


class ShowcaseService:
    """Orchestrates show_object / explain_object / find_objects."""

    def __init__(
        self,
        live_sources: LiveSourceEvidenceService = live_source_evidence_service,
        facts: FactsCompilerService = facts_compiler_service,
        simbad: SimbadTapConnector = simbad_tap_connector,
        resolver: LiveIngestionService = live_ingestion_service,
    ) -> None:
        self.live_sources = live_sources
        self.facts = facts
        self.simbad = simbad
        self.resolver = resolver

    async def show_object(
        self,
        query: str,
        *,
        bands: list[BandFamily] | None = None,
        pixels: int | None = None,
    ) -> dict[str, Any]:
        """Best real picture: cross-source composite plus per-band panels and facts."""

        bundle = await self.live_sources.bundle_for_query(
            query,
            bands=bands,
            max_views=MAX_PANELS + 2,
            sources=("mast", "skyview"),
            # 512px cutouts generate much faster on SkyView's side than the
            # 1024px preset and match the thumbnail render size below.
            pixels=pixels if pixels is not None else 512,
            composite=True,
            include_facts=True,
            # SkyView cutouts are ~512px native; rendering at thumbnail size
            # skips pointless upscaling and keeps hero calls fast enough for
            # proxy time limits on small instances.
            size="thumbnail",
        )
        hero = _prefer_color_hero(bundle.views)
        remaining = [view for view in bundle.views if view is not hero]
        # Show only the two best images: the hero plus the best genuinely
        # different supporting view (distinct band and distinct image), so the
        # two slots never duplicate the same observation.
        panels = _distinct_panels(hero, remaining)[: MAX_SHOWN_IMAGES - 1]
        shown_views = ([hero] if hero else []) + panels
        return {
            "object": bundle.object.model_dump(mode="json"),
            "headline": _headline(bundle.object, bundle.object_facts),
            "why_interesting": _why_interesting(bundle.object_facts),
            "hero_view": hero.model_dump(mode="json") if hero else None,
            "panels": [panel.model_dump(mode="json") for panel in panels],
            "views": [view.model_dump(mode="json") for view in shown_views],
            "object_facts": [fact.model_dump(mode="json") for fact in bundle.object_facts],
            "fact_citations": [
                citation.model_dump(mode="json") for citation in bundle.fact_citations
            ],
            "credits": _credits(shown_views),
            "suggested_followups": _followups(bundle.object),
            "warnings": [warning.model_dump(mode="json") for warning in bundle.warnings],
            "meta": bundle.meta.model_dump(mode="json"),
        }

    async def explain_object(self, query: str) -> dict[str, Any]:
        """Compiled, cited numeric facts for one object; no imaging."""

        obj = await self._resolve(query)
        result: ObjectFactsResult = await self.facts.facts_for_object(obj)
        return {
            "object": obj.model_dump(mode="json"),
            "headline": _headline(obj, result.facts),
            "object_facts": [fact.model_dump(mode="json") for fact in result.facts],
            "fact_citations": [
                citation.model_dump(mode="json") for citation in result.citations
            ],
            "suggested_followups": _followups(obj),
            "warnings": [warning.model_dump(mode="json") for warning in result.warnings],
        }

    async def find_objects(
        self,
        category: str,
        *,
        near_object: str | None = None,
        radius_deg: float | None = None,
        magnitude_limit: float | None = None,
        limit: int = 5,
        random_sample: bool = False,
    ) -> dict[str, Any]:
        """Category/region search over the SIMBAD catalog, optionally sampled."""

        otype = otype_for_category(category)
        cone: tuple[float, float, float] | None = None
        if near_object:
            center = await self._resolve(near_object)
            if center.ephemeris_object:
                raise AstroLensError(
                    ErrorCode.VALIDATION_ERROR,
                    f"{center.name} is a moving target and cannot anchor a sky region.",
                    retryable=False,
                    details={"near_object": near_object},
                )
            cone = (
                center.coordinates.ra_deg,
                center.coordinates.dec_deg,
                min(radius_deg or 5.0, MAX_FIND_RADIUS_DEG),
            )
        try:
            result = await self.simbad.search_category(
                otype=otype,
                cone=cone,
                magnitude_limit=magnitude_limit,
                limit=max(1, min(limit, MAX_FIND_RESULTS)),
                random_sample=random_sample,
            )
        except AstroLensError as exc:
            if exc.code not in {
                ErrorCode.SOURCE_TIMEOUT,
                ErrorCode.SOURCE_UNAVAILABLE,
                ErrorCode.RATE_LIMITED,
            }:
                raise
            return self._curated_category_fallback(category, otype, exc, limit=limit)
        return {
            "category": category,
            "otype": otype,
            "hits": [
                {
                    **hit.model_dump(mode="json"),
                    "followup": f'show_object {{"object": "{hit.main_id}"}}',
                }
                for hit in result.hits
            ],
            "query_adql": result.query_adql,
            "warnings": result.warnings,
        }

    def _curated_category_fallback(
        self,
        category: str,
        otype: str,
        exc: AstroLensError,
        *,
        limit: int,
    ) -> dict[str, Any]:
        """Serve curated seed objects of the category when the live catalog is down."""

        matches = repository.find_objects(category, limit=max(1, min(limit, MAX_FIND_RESULTS)))
        return {
            "category": category,
            "otype": otype,
            "hits": [
                {
                    "main_id": obj.name,
                    "otype": obj.type,
                    "ra_deg": obj.coordinates.ra_deg,
                    "dec_deg": obj.coordinates.dec_deg,
                    "followup": f'show_object {{"object": "{obj.name}"}}',
                }
                for obj in matches
                if not obj.ephemeris_object
            ],
            "query_adql": None,
            "warnings": [
                (
                    "Live SIMBAD catalog search is unavailable "
                    f"({exc.message}); returned curated well-known examples instead of a "
                    "live catalog result. Random sampling was not applied."
                ),
            ],
        }

    async def _resolve(self, query: str) -> CelestialObject:
        matches = repository.find_objects(query, limit=1)
        if matches:
            return matches[0]
        live_object, _cache_status = await self.resolver.object_live(query)
        return live_object


def _band_panels(views: list[View]) -> list[View]:
    """Keep at most one panel per band family, up to MAX_PANELS."""

    panels: list[View] = []
    seen_bands: set[str] = set()
    for view in views:
        band = str(view.band_family)
        if band in seen_bands:
            continue
        seen_bands.add(band)
        panels.append(view)
        if len(panels) >= MAX_PANELS:
            break
    return panels


def _prefer_color_hero(views: list[View]) -> View | None:
    """Pick the hero: the first color image among the top-ranked views.

    Archive previews of single-filter exposures are often grayscale; when a
    color view (multi-channel composite or tinted render) exists anywhere in
    the returned set, it makes the better lead image. Ranking is otherwise
    respected — panels keep ranked order; this is presentation policy only.
    """

    if not views:
        return None
    for view in views:
        if _is_color_view(view) and not _is_low_detail(view):
            return view
    return views[0]


def _is_low_detail(view: View) -> bool:
    """Views down-scored for having almost no real pixels (blob renders)."""

    scores = view.scores
    return (
        scores is not None
        and scores.preview_quality is not None
        and scores.preview_quality < 0.3
    )


def _is_color_view(view: View) -> bool:
    asset = view.asset
    if asset is None:
        return False
    if str(view.band_family) == str(BandFamily.MULTIWAVELENGTH):
        return True
    if len(asset.source_product_ids) >= 3:
        return True  # three-channel composite (e.g. SDSS/DSS2 RGB)
    # false_color is only a reliable color signal on images AstroLens rendered
    # itself (band-tinted single-channel renders). Archive previews set the
    # flag by band, and a non-visible archive preview is usually grayscale.
    return (
        str(asset.visual_tier) == "astrolens_rendered" and asset.false_color is True
    )


def _distinct_panels(hero: View | None, views: list[View]) -> list[View]:
    """Panels that differ from the hero by band and by image URL."""

    hero_band = str(hero.band_family) if hero else None
    hero_url = _asset_url(hero) if hero else None
    candidates = [
        view
        for view in views
        if _asset_url(view) and _asset_url(view) != hero_url
    ]
    distinct_band = [view for view in candidates if str(view.band_family) != hero_band]
    return _band_panels(distinct_band or candidates)


def _asset_url(view: View | None) -> str | None:
    if view is None or view.asset is None:
        return None
    return view.asset.asset_url or view.asset.thumbnail_url


def _headline(obj: CelestialObject, facts: list[Fact]) -> str:
    by_kind = {fact.quantity_kind: fact for fact in facts}
    classification = by_kind.get("classification")
    if classification is not None:
        headline = classification.claim
    else:
        # No SIMBAD classification (e.g. curated solar-system bodies): lead with
        # the most vivid available measurement instead of a bare "(type)".
        lead = _first_fact(facts, ("diameter", "distance", "physical_size"))
        headline = lead.claim if lead is not None else f"{obj.name} ({obj.type})."
    distance = by_kind.get("distance")
    if distance is not None and distance.scale_comparison:
        headline = f"{headline.rstrip('.')} — {distance.scale_comparison}."
    return headline


def _why_interesting(facts: list[Fact]) -> str | None:
    preferred_order = (
        "lookback_time",
        "distance",
        "physical_size",
        "apparent_magnitude",
        "redshift",
        "diameter",
        "distance_from_sun",
        "orbital_period",
        "density",
    )
    by_kind = {fact.quantity_kind: fact for fact in facts}
    ordered = [by_kind[kind] for kind in preferred_order if kind in by_kind]
    # Fall back to whatever facts exist so every object gets a narrative —
    # except classification, which already leads the headline.
    chosen = ordered or [fact for fact in facts if fact.quantity_kind != "classification"]
    sentences: list[str] = []
    for fact in chosen:
        sentence = fact.claim
        if fact.scale_comparison:
            sentence = f"{sentence.rstrip('.')} — {fact.scale_comparison}."
        sentences.append(sentence)
        if len(sentences) >= 3:
            break
    return " ".join(sentences) or None


def _first_fact(facts: list[Fact], kinds: tuple[str, ...]) -> Fact | None:
    by_kind = {fact.quantity_kind: fact for fact in facts}
    for kind in kinds:
        if kind in by_kind:
            return by_kind[kind]
    return None


def _credits(views: list[View]) -> list[dict[str, str]]:
    credits: list[dict[str, str]] = []
    for view in views:
        if view.asset is None:
            continue
        credit_line = view.asset.credit_text or view.reuse.credit_text
        if not credit_line:
            continue
        credits.append({"view_id": view.id, "credit_line": credit_line})
    return credits


def _followups(obj: CelestialObject) -> list[str]:
    # Phrased as natural questions so the widget can offer them as clickable
    # chips (and the model can relay them verbatim).
    return [
        f"What are the key measurements for {obj.name}?",
        f"Show {obj.name} across different wavelengths",
        f"How were these images of {obj.name} made?",
    ]


showcase_service = ShowcaseService()
