"""Live evidence bundle assembly for a narrow MAST-backed ingestion slice."""

import asyncio
import re
from typing import Any
from uuid import uuid4

from astrolens.connectors.mast import (
    MAST_SOURCE_URL,
    MastConnector,
    MastImageSearchResult,
    MastObservationSummary,
    MastProductSummary,
    mast_connector,
)
from astrolens.core.enums import (
    BandFamily,
    CacheStatus,
    ReuseStatus,
    TargetValidationStatus,
    VisualAssetTier,
)
from astrolens.core.models import (
    Asset,
    CacheMeta,
    CelestialObject,
    Citation,
    CrossWavelengthNote,
    DataProduct,
    EvidenceBundle,
    Fact,
    ImageProvenance,
    ResponseMeta,
    ReusePolicy,
    TargetValidation,
    View,
    ViewScores,
    WarningMessage,
)
from astrolens.data.seed import BAND_NOTES
from astrolens.services.live_ingestion import LiveIngestionService, live_ingestion_service
from astrolens.services.preview_image_quality import (
    PreviewImageQuality,
    PreviewImageQualityAnalyzer,
    preview_image_quality_analyzer,
)
from astrolens.services.preview_normalizer import (
    NormalizedResult,
    PreviewNormalizerService,
    preview_normalizer_service,
)
from astrolens.services.repository import normalize_query
from astrolens.services.target_validation import validate_observation_target
from astrolens.services.visual_quality import VisualQualityTier, assess_visual_quality

MAST_LIVE_CITATION = Citation(
    id="citation:mast:live:caom",
    title="MAST CAOM public observation and product metadata",
    source="MAST",
    url=MAST_SOURCE_URL,
    credit_text="MAST/STScI",
)

MAST_LIVE_REUSE = ReusePolicy(
    id="reuse:mast:live:public",
    status=ReuseStatus.CHECK_SOURCE_POLICY,
    commercial_use="check_source_policy",
    credit_required=True,
    credit_text=(
        "Credit MAST/STScI and the source mission; JWST products may require "
        "NASA/ESA/CSA credit."
    ),
    policy_url="https://www.stsci.edu/copyright",
    notes=[
        "Check source-product records for mission-specific credit language.",
        "Use archive metadata and source links for final reuse decisions.",
    ],
)

# Representative wavelengths used only to pick the observatory-conventional
# single-band tint for effectively grayscale archive previews. Visible and
# unknown bands map to None: no tint, grayscale stays honest there.
BAND_TINT_WAVELENGTH_NM: dict[BandFamily, float] = {
    BandFamily.XRAY: 1.2,
    BandFamily.ULTRAVIOLET: 230.0,
    BandFamily.INFRARED: 2200.0,
    BandFamily.MILLIMETER: 1_382_000.0,
    BandFamily.RADIO: 214_000_000.0,
}


class LiveEvidenceService:
    """Build source-grounded live evidence bundles for selected archives."""

    def __init__(
        self,
        resolver: LiveIngestionService = live_ingestion_service,
        mast: MastConnector = mast_connector,
        preview_quality: PreviewImageQualityAnalyzer | None = None,
        preview_normalizer: PreviewNormalizerService | None = None,
    ) -> None:
        self.resolver = resolver
        self.mast = mast
        self.preview_quality = preview_quality
        self.preview_normalizer = preview_normalizer
        self.cache: dict[str, EvidenceBundle] = {}

    async def bundle_for_query(
        self,
        query: str,
        *,
        bands: list[BandFamily] | None = None,
        max_views: int = 6,
        radius_deg: float = 0.03,
        missions: tuple[str, ...] = ("HST", "JWST"),
        rank_mode: str = "best_visual",
    ) -> EvidenceBundle:
        """Resolve a target and return live MAST HST/JWST evidence."""

        key = self._cache_key(
            query,
            bands=bands,
            max_views=max_views,
            radius_deg=radius_deg,
            missions=missions,
            rank_mode=rank_mode,
        )
        cached = self.cache.get(key)
        if cached:
            return cached.model_copy(
                update={
                    "meta": ResponseMeta(
                        request_id=f"req_{uuid4().hex}",
                        cache=CacheMeta(status=CacheStatus.HIT, stale=False),
                    )
                },
                deep=True,
            )

        live_object, _resolve_cache_status = await self.resolver.object_live(query)
        search_limit = min(max(max_views * 4, max_views), 24)
        mast_result = await self.mast.search_public_images(
            ra_deg=live_object.coordinates.ra_deg,
            dec_deg=live_object.coordinates.dec_deg,
            radius_deg=radius_deg,
            missions=missions,
            limit=search_limit,
            product_limit=8,
            product_observation_limit=search_limit,
            rank_mode=rank_mode,
        )
        bundle = await self._bundle_from_mast_result(
            live_object,
            mast_result,
            bands=bands,
            max_views=max_views,
            rank_mode=rank_mode,
            validate_coordinates=True,
        )
        self.cache[key] = bundle
        return bundle

    async def bundle_for_target_name(
        self,
        obj: CelestialObject,
        *,
        bands: list[BandFamily] | None = None,
        max_views: int = 6,
        missions: tuple[str, ...] = ("HST", "JWST"),
        rank_mode: str = "best_visual",
    ) -> EvidenceBundle:
        """Return live MAST evidence via archive target-name matching.

        Used for moving targets (planets, moons) whose stored coordinates are
        placeholders; coordinate-based target validation is skipped.
        """

        search_limit = min(max(max_views * 4, max_views), 24)
        mast_result = await self.mast.search_public_images_by_target_name(
            obj.name,
            missions=missions,
            limit=search_limit,
            product_limit=8,
            product_observation_limit=search_limit,
            rank_mode=rank_mode,
        )
        return await self._bundle_from_mast_result(
            obj,
            mast_result,
            bands=bands,
            max_views=max_views,
            rank_mode=rank_mode,
            validate_coordinates=False,
        )

    async def _bundle_from_mast_result(
        self,
        live_object: CelestialObject,
        mast_result: MastImageSearchResult,
        *,
        bands: list[BandFamily] | None,
        max_views: int,
        rank_mode: str,
        validate_coordinates: bool,
    ) -> EvidenceBundle:
        selected_bands = set(bands or [])
        observations = [
            observation
            for observation in mast_result.observations
            if not selected_bands or observation.band_family in selected_bands
        ]
        products_by_obsid = {
            product_set.obsid: product_set.products
            for product_set in mast_result.products_by_observation
        }

        candidate_views = [
            self._view_for_observation(
                object_name=live_object.name,
                object_slug=normalize_query(live_object.name) or "liveobject",
                object_coordinates=(
                    live_object.coordinates if validate_coordinates else None
                ),
                observation=observation,
                products=products_by_obsid.get(observation.obsid, []),
            )
            for observation in observations
        ]
        candidate_views = _sort_views_for_rank_mode(candidate_views, rank_mode)
        if rank_mode == "best_visual":
            await self._apply_preview_quality_scores(
                candidate_views[: max(max_views * 2, max_views)]
            )
            candidate_views = _sort_views_for_rank_mode(candidate_views, rank_mode)
        views = _select_views_for_rank_mode(
            candidate_views,
            rank_mode=rank_mode,
            max_views=max_views,
        )
        # Normalize only the previews that will actually be returned; the
        # candidate pool is larger and normalization downloads pixels.
        await self._normalize_selected_previews(views)
        warnings = self._warnings_for_result(mast_result.warnings, views)
        status = (
            CacheStatus.PARTIAL
            if warnings and not all(view.asset for view in views)
            else CacheStatus.MISS
        )
        return EvidenceBundle(
            object=live_object,
            views=views,
            cross_wavelength_notes=self._notes_for_views(views, bands),
            warnings=warnings,
            meta=ResponseMeta(
                request_id=f"req_{uuid4().hex}",
                cache=CacheMeta(status=status, stale=False),
            ),
        )

    def _view_for_observation(
        self,
        *,
        object_name: str,
        object_slug: str,
        object_coordinates: object,
        observation: MastObservationSummary,
        products: list[MastProductSummary],
    ) -> View:
        observation_id = f"obs:mast:live:{observation.obsid}"
        normalized_products = [
            self._data_product_for_mast_product(observation_id, product)
            for product in products
        ]
        best_preview = self._best_preview_product(normalized_products)
        validation_result = validate_observation_target(object_coordinates, observation)
        target_validation = _target_validation_model(validation_result)
        asset = (
            self._asset_for_preview(
                object_slug,
                observation,
                best_preview,
                target_validation=target_validation,
            )
            if best_preview is not None
            else None
        )
        fact = self._fact_for_observation(object_slug, object_name, observation)
        facility = _facility_for_collection(observation.collection)
        return View(
            id=f"view:{object_slug}:mast-live:{observation.obsid}",
            label=_view_label(object_name, observation),
            band_family=observation.band_family,
            facility=facility,
            instrument=observation.instrument,
            source_archive="MAST",
            asset=asset,
            raw_products=normalized_products,
            facts=[fact],
            reuse=MAST_LIVE_REUSE,
            citations=[MAST_LIVE_CITATION],
            caveats=[
                "Target match is estimated from archive coordinates; inspect the source "
                "record for exact footprint context.",
                "Preview color and stretch can differ from mission release images.",
            ],
            scores=ViewScores(
                object_match=0.82,
                public_access=1.0,
                asset_availability=0.95 if asset else 0.25,
                preview_quality=0.82 if asset else 0.25,
                science_ready=0.72 if normalized_products else 0.55,
                provenance_quality=0.92,
                citation_quality=0.85,
                renderability=0.9 if asset else 0.35,
                source_reliability=0.92,
                overall=0.86 if asset else 0.64,
            ),
        )

    def _data_product_for_mast_product(
        self,
        observation_id: str,
        product: MastProductSummary,
    ) -> DataProduct:
        product_slug = normalize_query(
            product.product_filename or product.data_uri or uuid4().hex
        )[:64]
        is_preview = str(product.product_type or "").upper() == "PREVIEW"
        is_renderable_preview = is_preview and product.file_format in {"jpg", "jpeg", "png", "gif"}
        return DataProduct(
            id=f"product:mast:live:{observation_id.rsplit(':', maxsplit=1)[-1]}:{product_slug}",
            observation_id=observation_id,
            product_type=(product.product_type or "product").lower(),
            file_format=product.file_format,
            calibration_level=product.calibration_level,
            download_url=product.download_url,
            preview_url=product.download_url if is_renderable_preview else None,
            file_size_mb=(
                product.size_bytes / (1024 * 1024) if product.size_bytes is not None else None
            ),
            renderability_score=_renderability_score(product),
            source_record_id=product.data_uri or product.product_filename,
            raw_metadata=product.raw_metadata,
        )

    def _asset_for_preview(
        self,
        object_slug: str,
        observation: MastObservationSummary,
        product: DataProduct,
        *,
        target_validation: TargetValidation,
    ) -> Asset:
        return Asset(
            id=f"asset:{object_slug}:mast-live:{observation.obsid}:preview",
            source_product_ids=[product.id],
            format=product.file_format or "external_preview",
            visual_tier=_visual_tier_for_product(product),
            asset_url=product.preview_url,
            thumbnail_url=product.preview_url,
            false_color=observation.band_family != BandFamily.VISIBLE,
            processing_note=_processing_note_for_product(product),
            selection_reason=_selection_reason_for_product(product),
            target_validation=target_validation,
            provenance=_image_provenance_for_product(
                observation=observation,
                product=product,
            ),
            credit_text=MAST_LIVE_REUSE.credit_text,
            reuse_policy_id=MAST_LIVE_REUSE.id,
            citations=[MAST_LIVE_CITATION],
        )

    def _fact_for_observation(
        self,
        object_slug: str,
        object_name: str,
        observation: MastObservationSummary,
    ) -> Fact:
        collection = observation.collection or "MAST"
        instrument = observation.instrument or "unknown instrument"
        filters = f" with filter(s) {observation.filters}" if observation.filters else ""
        claim = (
            f"MAST lists a public {collection} image observation of {object_name} "
            f"using {instrument}{filters}."
        )
        return Fact(
            id=f"fact:{object_slug}:mast-live:{observation.obsid}",
            entity_type="observation",
            entity_id=f"obs:mast:live:{observation.obsid}",
            claim=claim,
            scope="live_archive_observation_metadata",
            confidence=0.9,
            citation_ids=[MAST_LIVE_CITATION.id],
        )

    def _warnings_for_result(
        self,
        connector_warnings: list[str],
        views: list[View],
    ) -> list[WarningMessage]:
        warnings = [
            WarningMessage(
                code="LIVE_MAST_WARNING",
                message=message,
                source="MAST",
                retryable=True,
            )
            for message in connector_warnings
        ]
        if not views:
            warnings.append(
                WarningMessage(
                    code="NO_LIVE_MAST_IMAGES",
                    message=(
                        "No public HST/JWST image observations were found in this limited "
                        "MAST live-ingestion cone."
                    ),
                    source="MAST",
                    retryable=False,
                )
            )
        elif any(view.asset is None for view in views):
            warnings.append(
                WarningMessage(
                    code="PARTIAL_LIVE_PRODUCTS",
                    message=(
                        "Some live observations did not include a renderable preview product "
                        "in the limited product manifest."
                    ),
                    source="MAST",
                    retryable=False,
                )
            )
        return warnings

    def _notes_for_views(
        self,
        views: list[View],
        bands: list[BandFamily] | None,
    ) -> list[CrossWavelengthNote]:
        note_bands = set(bands or [view.band_family for view in views])
        return [BAND_NOTES[band] for band in note_bands if band in BAND_NOTES]

    def _cache_key(
        self,
        query: str,
        *,
        bands: list[BandFamily] | None,
        max_views: int,
        radius_deg: float,
        missions: tuple[str, ...],
        rank_mode: str,
    ) -> str:
        band_key = ",".join(sorted(str(band) for band in bands or []))
        mission_key = ",".join(sorted(mission.upper() for mission in missions))
        return (
            f"{normalize_query(query)}:{mission_key}:{band_key}:"
            f"{max_views}:{radius_deg:.5f}:{rank_mode}"
        )

    def _best_preview_product(self, products: list[DataProduct]) -> DataProduct | None:
        renderable = [
            product
            for product in products
            if product.preview_url and product.file_format in {"jpg", "jpeg", "png", "gif"}
        ]
        if renderable:
            return sorted(renderable, key=_preview_sort_key)[0]
        previews = [product for product in products if product.preview_url]
        return previews[0] if previews else None

    async def _apply_preview_quality_scores(self, views: list[View]) -> None:
        if not self.preview_quality:
            return
        score_targets = [
            (view, view.asset.asset_url)
            for view in views
            if view.asset and view.asset.asset_url
        ]
        if not score_targets:
            return
        analyzer = self.preview_quality
        # Bounded fan-out: each assessment downloads and decodes an image, so
        # unbounded gather can spike memory on small instances.
        semaphore = asyncio.Semaphore(4)

        async def assess(url: str) -> Any:
            async with semaphore:
                return await asyncio.to_thread(analyzer.assess_url, url)

        results = await asyncio.gather(
            *[assess(url) for _view, url in score_targets],
            return_exceptions=True,
        )
        for (view, _url), result in zip(score_targets, results, strict=False):
            if not isinstance(result, PreviewImageQuality) or result.status != "ok":
                continue
            if view.scores:
                view.scores.preview_quality = result.score
                view.scores.renderability = min(
                    1.0,
                    max(0.0, (view.scores.renderability or 0.0) * 0.75 + result.score * 0.25),
                )
                view.scores.overall = min(
                    1.0,
                    max(0.0, (view.scores.overall * 0.78) + (result.score * 0.22)),
                )

    async def _normalize_selected_previews(self, views: list[View]) -> None:
        """Swap ugly archive previews for cropped/de-tilted/tinted derivatives.

        Runs only on the final selected views. The original archive preview
        stays reachable through the view's raw product links; only the asset
        display URLs move to the normalized `/v1/rendered/...` derivative.
        """

        normalizer = self.preview_normalizer
        if not normalizer:
            return
        targets = [
            (view, view.asset)
            for view in views
            if view.asset and view.asset.asset_url
        ]
        if not targets:
            return
        # Bounded fan-out: each normalization downloads and decodes an image,
        # so unbounded gather can spike memory on small instances.
        semaphore = asyncio.Semaphore(2)

        async def normalize(view: View, url: str) -> Any:
            async with semaphore:
                return await asyncio.to_thread(
                    normalizer.normalized_asset_url,
                    url,
                    wavelength_nm=BAND_TINT_WAVELENGTH_NM.get(view.band_family),
                )

        results = await asyncio.gather(
            *[normalize(view, str(asset.asset_url)) for view, asset in targets],
            return_exceptions=True,
        )
        for (_view, asset), result in zip(targets, results, strict=False):
            if not isinstance(result, NormalizedResult):
                continue
            asset.asset_url = result.asset_url
            asset.thumbnail_url = result.asset_url
            asset.width = result.width
            asset.height = result.height
            if result.tinted_band:
                asset.false_color = True
            note = _normalization_note(result)
            asset.processing_note = (
                f"{asset.processing_note} {note}" if asset.processing_note else note
            )


def _normalization_note(result: NormalizedResult) -> str:
    """Describe only the normalization steps that actually happened."""

    parts: list[str] = []
    if result.cropped:
        parts.append("auto-cropped")
    if result.rotated_deg is not None:
        parts.append("de-tilted")
    if result.tinted_band:
        parts.append(f"{result.tinted_band}-band-tinted")
    text = "/".join(parts)
    return f"{text[:1].upper()}{text[1:]} by AstroLens from the archive preview."


def _facility_for_collection(collection: str | None) -> str | None:
    if collection == "JWST":
        return "James Webb Space Telescope"
    if collection == "HST":
        return "Hubble Space Telescope"
    return collection


def _view_label(object_name: str, observation: MastObservationSummary) -> str:
    collection = observation.collection or "MAST"
    instrument = observation.instrument or "image"
    filters = f" {observation.filters}" if observation.filters else ""
    return f"{object_name} {collection} {instrument}{filters}"


def _renderability_score(product: MastProductSummary) -> float:
    if product.file_format in {"jpg", "jpeg", "png", "gif"}:
        return 0.92
    if product.file_format in {"fits", "fit", "fits.gz"}:
        return 0.65
    return 0.45


def _preview_sort_key(product: DataProduct) -> tuple[int, str]:
    assessment = assess_visual_quality(product)
    filename = str(product.raw_metadata.get("productFilename") or product.source_record_id or "")
    return (-assessment.score, filename)


def _processing_note_for_product(product: DataProduct) -> str:
    assessment = assess_visual_quality(product)
    if assessment.tier == VisualQualityTier.HLA_HLSP_HAP_COLOR_COMPOSITE:
        return "Processed color/composite MAST visual from HLA/HLSP/HAP-style archive products."
    if assessment.tier == VisualQualityTier.PROCESSED_ARCHIVE_PRODUCT:
        return "Processed or combined archive visual, preferred over raw detector previews."
    return "Live MAST archive preview selected for display."


def _visual_tier_for_product(product: DataProduct) -> VisualAssetTier:
    tier = assess_visual_quality(product).tier
    if tier == VisualQualityTier.OUTREACH_RELEASE:
        return VisualAssetTier.OUTREACH_RELEASE
    if tier == VisualQualityTier.ASTROLENS_RENDERED:
        return VisualAssetTier.ASTROLENS_RENDERED
    if tier in {
        VisualQualityTier.HLA_HLSP_HAP_COLOR_COMPOSITE,
        VisualQualityTier.PROCESSED_ARCHIVE_PRODUCT,
    }:
        return VisualAssetTier.PROCESSED_ARCHIVE
    if tier == VisualQualityTier.RAW_PREVIEW:
        return VisualAssetTier.RAW_ARCHIVE_PREVIEW
    return VisualAssetTier.UNKNOWN


def _selection_reason_for_product(product: DataProduct) -> str:
    assessment = assess_visual_quality(product)
    reasons = ", ".join(assessment.reasons) if assessment.reasons else "no explicit marker"
    penalties = (
        f"; penalties: {', '.join(assessment.penalties)}"
        if assessment.penalties
        else ""
    )
    return f"Selected as {assessment.provenance_label} ({reasons}{penalties})."


def _image_provenance_for_product(
    *,
    observation: MastObservationSummary,
    product: DataProduct,
) -> ImageProvenance:
    raw = product.raw_metadata
    return ImageProvenance(
        visual_tier=_visual_tier_for_product(product),
        source_archive="MAST",
        facility=_facility_for_collection(observation.collection),
        instrument=observation.instrument,
        observation_id=observation.obsid,
        source_product_id=product.id,
        source_record_id=product.source_record_id,
        proposal_id=_raw_string(raw, "proposal_id", "proposalId"),
        filters=_raw_string(raw, "filters", "filter"),
        calibration_level=product.calibration_level,
        product_project=_raw_string(raw, "project"),
        product_description=_raw_string(raw, "description"),
        notes=[
            "Selected from live public MAST observation/product metadata.",
        ],
    )


def _target_validation_model(result: object) -> TargetValidation:
    return TargetValidation(
        status=getattr(result, "status", TargetValidationStatus.UNVERIFIED),
        confidence=getattr(result, "confidence", 0.0),
        distance_arcsec=getattr(result, "distance_arcsec", None),
        target_in_frame=getattr(result, "target_in_frame", None),
        notes=list(getattr(result, "notes", ())),
    )


def _sort_views_for_rank_mode(views: list[View], rank_mode: str) -> list[View]:
    if rank_mode == "best_visual":
        return sorted(views, key=_view_visual_sort_key)
    return views


def _select_views_for_rank_mode(
    views: list[View],
    *,
    rank_mode: str,
    max_views: int,
) -> list[View]:
    if max_views <= 0:
        return []
    exact_unique = _dedupe_views_by_asset(views)
    if rank_mode != "best_visual":
        return exact_unique[:max_views]
    return _dedupe_views_by_visual_family(exact_unique, max_views=max_views)


def _view_visual_sort_key(view: View) -> tuple[float, str]:
    return (-_view_visual_score(view), view.label)


def _view_visual_score(view: View) -> float:
    score = 0.0
    if view.asset and view.asset.asset_url:
        score += 25.0
    product = _primary_product_for_view(view)
    if product:
        assessment = assess_visual_quality(product)
        score += assessment.score
    if view.band_family == BandFamily.VISIBLE:
        score += 12.0
    if view.band_family == BandFamily.MULTIWAVELENGTH:
        score += 16.0
    if view.asset and view.asset.target_validation:
        validation = view.asset.target_validation
        if validation.status == TargetValidationStatus.CENTERED:
            score += 20.0
        elif validation.status == TargetValidationStatus.IN_FRAME:
            score += 12.0
        elif validation.status == TargetValidationStatus.NEARBY_OFFSET:
            score -= 10.0
        elif validation.status == TargetValidationStatus.OUT_OF_FRAME:
            score -= 60.0
    if view.scores and view.scores.preview_quality is not None:
        score += (view.scores.preview_quality - 0.5) * 120.0
    return score


def _primary_product_for_view(view: View) -> DataProduct | None:
    if not view.raw_products:
        return None
    if not view.asset or not view.asset.source_product_ids:
        return view.raw_products[0]
    source_product_ids = set(view.asset.source_product_ids)
    for product in view.raw_products:
        if product.id in source_product_ids:
            return product
    return view.raw_products[0]


def _product_text(product: DataProduct | None) -> str:
    if product is None:
        return ""
    return " ".join(
        str(item or "")
        for item in [
            product.source_record_id,
            product.download_url,
            product.preview_url,
            product.raw_metadata.get("dataURI"),
            product.raw_metadata.get("productFilename"),
            product.raw_metadata.get("project"),
            product.raw_metadata.get("description"),
            product.raw_metadata.get("productGroupDescription"),
            product.raw_metadata.get("productSubGroupDescription"),
        ]
    ).lower()


def _raw_string(metadata: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _dedupe_views_by_asset(views: list[View]) -> list[View]:
    unique: list[View] = []
    seen: set[str] = set()
    for view in views:
        product = _primary_product_for_view(view)
        key = _normalized_view_dedupe_key(
            product.source_record_id
            if product and product.source_record_id
            else view.asset.asset_url
            if view.asset and view.asset.asset_url
            else view.id
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(view)
    return unique


def _dedupe_views_by_visual_family(views: list[View], *, max_views: int) -> list[View]:
    selected: list[View] = []
    overflow: list[View] = []
    seen_families: set[str] = set()
    for view in views:
        family_key = _visual_family_key(view)
        if family_key in seen_families:
            overflow.append(view)
            continue
        seen_families.add(family_key)
        selected.append(view)
        if len(selected) >= max_views:
            return selected

    for view in overflow:
        selected.append(view)
        if len(selected) >= max_views:
            break
    return selected


def _visual_family_key(view: View) -> str:
    product = _primary_product_for_view(view)
    text = " ".join([_product_text(product), view.label]).lower()
    facility = _family_token(view.facility or view.source_archive or "unknown")
    instrument = _family_token(_instrument_family(view.instrument, text))
    band = _family_token(str(view.band_family))
    kind = _visual_product_kind(product)
    filters = _filter_family(view, product, text)

    if _looks_like_jwst(view, text):
        return f"jwst:{instrument}:{filters}:{kind}"
    if _looks_like_hst(view, text):
        if kind in {"outreach", "rendered", "processed_archive"}:
            return f"hst:{instrument}:{band}:processed_visual"
        return f"hst:{instrument}:{band}:{filters}:{kind}"
    return f"{facility}:{instrument}:{band}:{filters}:{kind}"


def _visual_product_kind(product: DataProduct | None) -> str:
    assessment = assess_visual_quality(product)
    if assessment.tier == VisualQualityTier.OUTREACH_RELEASE:
        return "outreach"
    if assessment.tier == VisualQualityTier.ASTROLENS_RENDERED:
        return "rendered"
    if assessment.tier in {
        VisualQualityTier.HLA_HLSP_HAP_COLOR_COMPOSITE,
        VisualQualityTier.PROCESSED_ARCHIVE_PRODUCT,
    }:
        return "processed_archive"
    return "raw_preview"


def _looks_like_hst(view: View, text: str) -> bool:
    return (
        "mast:hst" in text
        or "hubble" in str(view.facility or "").lower()
        or _raw_string(_primary_product_raw_metadata(view), "obs_collection") == "HST"
    )


def _looks_like_jwst(view: View, text: str) -> bool:
    return (
        "mast:jwst" in text
        or "webb" in str(view.facility or "").lower()
        or _raw_string(_primary_product_raw_metadata(view), "obs_collection") == "JWST"
    )


def _primary_product_raw_metadata(view: View) -> dict[str, object]:
    product = _primary_product_for_view(view)
    return product.raw_metadata if product else {}


def _instrument_family(instrument: str | None, text: str) -> str:
    instrument_text = str(instrument or "").lower()
    combined = f"{instrument_text} {text}"
    if "nircam" in combined:
        return "nircam"
    if "niriss" in combined:
        return "niriss"
    if "miri" in combined:
        return "miri"
    if "wfc3" in combined and ("uvis" in combined or "/uvis" in combined):
        return "wfc3_uvis"
    if "wfc3" in combined and ("ir" in combined or "/ir" in combined):
        return "wfc3_ir"
    if "acs" in combined and "wfc" in combined:
        return "acs_wfc"
    if "wfpc2" in combined:
        return "wfpc2"
    return instrument or "unknown"


def _filter_family(view: View, product: DataProduct | None, text: str) -> str:
    explicit = None
    if view.asset and view.asset.provenance:
        explicit = view.asset.provenance.filters
    if product:
        explicit = explicit or _raw_string(product.raw_metadata, "filters", "filter")
    if explicit:
        return _family_token(explicit)

    filter_tokens = re.findall(r"\bF\d{3,4}[A-Z]?\b", text.upper())
    if filter_tokens:
        return _family_token("_".join(dict.fromkeys(filter_tokens)))
    if "detection" in text:
        return "detection"
    if "total" in text:
        return "total"
    return _family_token(str(view.band_family))


def _family_token(value: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return token or "unknown"


def _normalized_view_dedupe_key(key: str) -> str:
    if "preview.cgi?dataset=" not in key:
        return key
    return re.sub(r"_\d{2}(?=$|[&#])", "", key)


def _safe_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


live_evidence_service = LiveEvidenceService(
    preview_quality=preview_image_quality_analyzer,
    preview_normalizer=preview_normalizer_service,
)
