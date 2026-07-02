"""Evidence bundle assembly for SkyView generated survey cutouts."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from astrolens.connectors.skyview import (
    SKYVIEW_DOCS_URL,
    SKYVIEW_SOURCE_URL,
    SkyViewConnector,
    SkyViewProductSummary,
    skyview_connector,
)
from astrolens.core.enums import (
    BandFamily,
    CacheStatus,
    ReuseStatus,
    TargetValidationStatus,
    VisualAssetTier,
    VisualMode,
)
from astrolens.core.models import (
    Asset,
    CacheMeta,
    Citation,
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
from astrolens.services.fits_renderer import (
    FitsRenderer,
    FitsRenderRequest,
    FitsRenderResult,
    SourceFitsProduct,
)
from astrolens.services.live_ingestion import LiveIngestionService, live_ingestion_service
from astrolens.services.repository import normalize_query
from astrolens.services.visual_modes import coerce_visual_mode

SKYVIEW_CITATION = Citation(
    id="citation:skyview:generated-fits",
    title="NASA SkyView generated FITS survey cutouts",
    source="SkyView",
    url=SKYVIEW_SOURCE_URL,
    credit_text="NASA SkyView and the source survey",
)

SKYVIEW_REUSE = ReusePolicy(
    id="reuse:skyview:generated-fits",
    status=ReuseStatus.CHECK_SOURCE_POLICY,
    commercial_use="check_source_policy",
    credit_required=True,
    credit_text="Credit NASA SkyView and the underlying survey named in the product metadata.",
    policy_url=SKYVIEW_DOCS_URL,
    notes=[
        "SkyView generates cutouts from public survey data; the underlying survey may have "
        "its own acknowledgement language.",
        "Do not treat generated cutouts as official press or outreach imagery.",
    ],
)


class SkyViewEvidenceService:
    """Build agent-facing views from public SkyView generated FITS cutouts."""

    def __init__(
        self,
        resolver: LiveIngestionService = live_ingestion_service,
        skyview: SkyViewConnector = skyview_connector,
        renderer: FitsRenderer | None = None,
    ) -> None:
        self.resolver = resolver
        self.skyview = skyview
        self.renderer = renderer or FitsRenderer()
        self.cache: dict[str, EvidenceBundle] = {}

    async def bundle_for_query(
        self,
        query: str,
        *,
        bands: list[BandFamily] | None = None,
        max_views: int = 6,
        radius_deg: float = 0.03,
        surveys: list[str] | None = None,
        pixels: int = 512,
        visual_mode: VisualMode | str | None = VisualMode.CONTEXT,
        size: str = "standard",
        stretch: str = "asinh",
    ) -> EvidenceBundle:
        """Resolve a target and return rendered SkyView survey views."""

        resolved_visual_mode = coerce_visual_mode(visual_mode)
        bounded_pixels = max(64, min(int(pixels), 2048))
        live_object, _resolve_cache_status = await self.resolver.object_live(query)
        result = await self.skyview.search_generated_fits(
            ra_deg=live_object.coordinates.ra_deg,
            dec_deg=live_object.coordinates.dec_deg,
            radius_deg=radius_deg,
            bands=bands,
            surveys=surveys,
            pixels=bounded_pixels,
            visual_mode=resolved_visual_mode,
        )
        object_slug = normalize_query(live_object.name) or "liveobject"
        views = await self._views_for_products(
            object_slug=object_slug,
            object_name=live_object.name,
            products=result.products,
            size=size,
            stretch=stretch,
            max_views=max_views,
        )
        warnings = [
            WarningMessage(
                code="LIVE_SKYVIEW_WARNING",
                message=message,
                source="SkyView",
                retryable=True,
            )
            for message in result.warnings
        ]
        if not views:
            warnings.append(
                WarningMessage(
                    code="NO_LIVE_SKYVIEW_CUTOUTS",
                    message="No generated SkyView FITS cutouts were returned for this target.",
                    source="SkyView",
                    retryable=False,
                )
            )
        elif any(view.asset is None for view in views):
            warnings.append(
                WarningMessage(
                    code="PARTIAL_SKYVIEW_RENDERS",
                    message=(
                        "Some SkyView FITS cutouts were found but could not be rendered "
                        "into AstroLens preview assets."
                    ),
                    source="SkyView",
                    retryable=True,
                )
            )

        bundle = EvidenceBundle(
            object=live_object,
            views=views,
            cross_wavelength_notes=[
                BAND_NOTES[band]
                for band in {view.band_family for view in views}
                if band in BAND_NOTES
            ],
            warnings=warnings,
            meta=ResponseMeta(
                request_id=f"req_{uuid4().hex}",
                cache=CacheMeta(
                    status=CacheStatus.PARTIAL if warnings else CacheStatus.MISS,
                    stale=False,
                ),
            ),
        )
        return bundle

    async def _views_for_products(
        self,
        *,
        object_slug: str,
        object_name: str,
        products: list[SkyViewProductSummary],
        size: str,
        stretch: str,
        max_views: int,
    ) -> list[View]:
        builders = []
        composite_products = _visible_composite_products(products)
        used_source_record_ids: set[str] = set()
        if len(composite_products) >= 3:
            builders.append(
                self._composite_view_for_products(
                    object_slug=object_slug,
                    object_name=object_name,
                    products=composite_products,
                    size=size,
                    stretch=stretch,
                )
            )
            used_source_record_ids.update(
                product.source_record_id for product in composite_products
            )
        for product in products:
            if product.source_record_id in used_source_record_ids:
                continue
            builders.append(
                self._view_for_product(
                    object_slug=object_slug,
                    object_name=object_name,
                    product=product,
                    size=size,
                    stretch=stretch,
                )
            )
        # Only render views that will be returned; renders run concurrently in
        # worker threads so they never block the event loop.
        return list(await asyncio.gather(*builders[:max_views]))

    async def _composite_view_for_products(
        self,
        *,
        object_slug: str,
        object_name: str,
        products: list[SkyViewProductSummary],
        size: str,
        stretch: str,
    ) -> View:
        observation_id = f"obs:skyview:{object_slug}:visible-rgb"
        data_products = [
            self._data_product_for_skyview_product(observation_id, product)
            for product in products
        ]
        render_result = await asyncio.to_thread(
            self.renderer.render,
            FitsRenderRequest(
                object_id=f"skyview:{object_slug}:visible-rgb",
                products=[
                    SourceFitsProduct.from_data_product(product)
                    for product in data_products
                ],
                size=size,  # type: ignore[arg-type]
                stretch=stretch,  # type: ignore[arg-type]
                max_source_file_mb=180.0,
            )
        )
        asset = self._asset_for_composite_render(
            object_slug=object_slug,
            data_products=data_products,
            products=products,
            render_result=render_result,
            size=size,
            stretch=stretch,
        )
        surveys = ", ".join(product.survey for product in products)
        return View(
            id=f"view:{object_slug}:skyview:visible-rgb",
            label=f"{object_name} SkyView visible RGB composite",
            band_family=BandFamily.VISIBLE,
            facility="NASA SkyView",
            instrument=surveys,
            source_archive="SkyView",
            asset=asset,
            raw_products=data_products,
            facts=[self._fact_for_composite(object_slug, object_name, products)],
            reuse=SKYVIEW_REUSE,
            citations=[SKYVIEW_CITATION],
            caveats=[
                "AstroLens rendered this RGB composite from multiple SkyView survey FITS "
                "cutouts; it is not an official outreach image.",
                "Visible-band colors are representative channel mappings and depend on "
                "stretch, survey depth, and WCS reprojection.",
                "SkyView survey coverage varies; outside SDSS coverage, use DSS fallback "
                "surveys or another archive.",
            ],
            scores=ViewScores(
                object_match=0.9,
                public_access=1.0,
                asset_availability=0.98 if asset else 0.45,
                preview_quality=0.84 if asset else 0.3,
                science_ready=0.8,
                provenance_quality=0.92,
                citation_quality=0.84,
                renderability=0.95 if asset else 0.55,
                source_reliability=0.86,
                overall=0.9 if asset else 0.62,
            ),
        )

    async def _view_for_product(
        self,
        *,
        object_slug: str,
        object_name: str,
        product: SkyViewProductSummary,
        size: str,
        stretch: str,
    ) -> View:
        observation_id = f"obs:skyview:{object_slug}:{normalize_query(product.survey)}"
        data_product = self._data_product_for_skyview_product(observation_id, product)
        render_result = await asyncio.to_thread(
            self.renderer.render,
            FitsRenderRequest(
                object_id=f"skyview:{object_slug}",
                products=[SourceFitsProduct.from_data_product(data_product)],
                size=size,  # type: ignore[arg-type]
                stretch=stretch,  # type: ignore[arg-type]
                max_source_file_mb=80.0,
            )
        )
        asset = self._asset_for_render(
            object_slug=object_slug,
            product=product,
            data_product=data_product,
            render_result=render_result,
            size=size,
            stretch=stretch,
        )
        return View(
            id=f"view:{object_slug}:skyview:{normalize_query(product.survey)}",
            label=f"{object_name} SkyView {product.survey}",
            band_family=product.band_family,
            facility="NASA SkyView",
            instrument=product.survey,
            source_archive="SkyView",
            asset=asset,
            raw_products=[data_product],
            facts=[self._fact_for_product(object_slug, object_name, product)],
            reuse=SKYVIEW_REUSE,
            citations=[SKYVIEW_CITATION],
            caveats=[
                "SkyView generates this cutout from public survey data around the resolved "
                "coordinates; it is not an official outreach image.",
                "Survey resolution, depth, epoch, and sky coverage vary by wavelength.",
                "AstroLens rendering choices such as stretch and color mapping affect the "
                "preview appearance.",
            ],
            scores=ViewScores(
                object_match=0.9,
                public_access=1.0,
                asset_availability=0.95 if asset else 0.45,
                preview_quality=0.7 if asset else 0.3,
                science_ready=0.78,
                provenance_quality=0.9,
                citation_quality=0.82,
                renderability=0.9 if asset else 0.55,
                source_reliability=0.86,
                overall=0.82 if asset else 0.62,
            ),
        )

    def _data_product_for_skyview_product(
        self,
        observation_id: str,
        product: SkyViewProductSummary,
    ) -> DataProduct:
        survey_slug = normalize_query(product.survey)
        return DataProduct(
            id=f"product:skyview:{observation_id.rsplit(':', maxsplit=1)[-1]}:{survey_slug}",
            observation_id=observation_id,
            product_type=product.product_type,
            file_format=product.file_format,
            calibration_level=product.calibration_level,
            download_url=product.download_url,
            preview_url=None,
            file_size_mb=None,
            renderability_score=0.88,
            source_record_id=product.source_record_id,
            raw_metadata={
                **product.raw_metadata,
                "filename": f"skyview_{survey_slug}.fits",
                "filter": product.survey,
                "wavelength_nm": product.wavelength_nm,
                "source_archive": "SkyView",
            },
        )

    def _asset_for_render(
        self,
        *,
        object_slug: str,
        product: SkyViewProductSummary,
        data_product: DataProduct,
        render_result: FitsRenderResult,
        size: str,
        stretch: str,
    ) -> Asset | None:
        if render_result.status != "complete" or not render_result.asset_url:
            return None
        recipe = render_result.recipe
        fallback_asset_id = f"asset:{object_slug}:skyview:{normalize_query(product.survey)}"
        return Asset(
            id=render_result.asset_id or fallback_asset_id,
            source_product_ids=[data_product.id],
            format="png",
            visual_tier=VisualAssetTier.ASTROLENS_RENDERED,
            width=recipe.width if recipe else None,
            height=recipe.height if recipe else None,
            asset_url=render_result.asset_url,
            thumbnail_url=render_result.asset_url,
            false_color=product.band_family != BandFamily.VISIBLE,
            processing_note=(
                f"AstroLens-rendered SkyView FITS cutout using {stretch} stretch "
                f"at {size} size."
            ),
            selection_reason=(
                "Generated from a bounded SkyView survey cutout centered on the resolved "
                "target coordinates."
            ),
            target_validation=TargetValidation(
                status=TargetValidationStatus.CENTERED,
                confidence=0.85,
                distance_arcsec=0.0,
                target_in_frame=True,
                notes=[
                    "SkyView cutouts are requested at the resolved object coordinates.",
                    "Large or extended targets can still span beyond the requested field.",
                ],
            ),
            provenance=ImageProvenance(
                visual_tier=VisualAssetTier.ASTROLENS_RENDERED,
                source_archive="SkyView",
                facility="NASA SkyView",
                instrument=product.survey,
                observation_id=data_product.observation_id,
                source_product_id=data_product.id,
                source_record_id=product.source_record_id,
                filters=product.survey,
                calibration_level=product.calibration_level,
                render_recipe_id=render_result.cache_key,
                notes=[
                    "Generated from a SkyView public survey FITS cutout.",
                    "Rendered locally by AstroLens for agent-facing preview use.",
                ],
            ),
            credit_text=SKYVIEW_REUSE.credit_text,
            reuse_policy_id=SKYVIEW_REUSE.id,
            citations=[SKYVIEW_CITATION],
        )

    def _asset_for_composite_render(
        self,
        *,
        object_slug: str,
        data_products: list[DataProduct],
        products: list[SkyViewProductSummary],
        render_result: FitsRenderResult,
        size: str,
        stretch: str,
    ) -> Asset | None:
        if render_result.status != "complete" or not render_result.asset_url:
            return None
        recipe = render_result.recipe
        fallback_asset_id = f"asset:{object_slug}:skyview:visible-rgb"
        filters = ", ".join(product.survey for product in products)
        return Asset(
            id=render_result.asset_id or fallback_asset_id,
            source_product_ids=[product.id for product in data_products],
            format="png",
            visual_tier=VisualAssetTier.ASTROLENS_RENDERED,
            width=recipe.width if recipe else None,
            height=recipe.height if recipe else None,
            asset_url=render_result.asset_url,
            thumbnail_url=render_result.asset_url,
            false_color=False,
            processing_note=(
                f"AstroLens-rendered visible RGB composite from SkyView FITS cutouts "
                f"using {stretch} stretch at {size} size."
            ),
            selection_reason=(
                "Selected as the highest-legibility SkyView visible view because multiple "
                "aligned optical filters were available."
            ),
            target_validation=TargetValidation(
                status=TargetValidationStatus.CENTERED,
                confidence=0.85,
                distance_arcsec=0.0,
                target_in_frame=True,
                notes=[
                    "SkyView cutouts are requested at the resolved object coordinates.",
                    "RGB alignment depends on WCS metadata in the generated FITS cutouts.",
                ],
            ),
            provenance=ImageProvenance(
                visual_tier=VisualAssetTier.ASTROLENS_RENDERED,
                source_archive="SkyView",
                facility="NASA SkyView",
                instrument=filters,
                observation_id=data_products[0].observation_id if data_products else None,
                source_product_id=data_products[0].id if data_products else None,
                source_record_id=render_result.cache_key,
                filters=filters,
                calibration_level="3",
                render_recipe_id=render_result.cache_key,
                notes=[
                    "Generated from multiple SkyView public survey FITS cutouts.",
                    "Rendered locally by AstroLens as an RGB composite for agent-facing use.",
                ],
            ),
            credit_text=SKYVIEW_REUSE.credit_text,
            reuse_policy_id=SKYVIEW_REUSE.id,
            citations=[SKYVIEW_CITATION],
        )

    def _fact_for_product(
        self,
        object_slug: str,
        object_name: str,
        product: SkyViewProductSummary,
    ) -> Fact:
        return Fact(
            id=f"fact:{object_slug}:skyview:{normalize_query(product.survey)}",
            entity_type="generated_cutout",
            entity_id=product.source_record_id,
            claim=(
                f"SkyView returned a public {product.survey} FITS cutout around "
                f"{object_name}'s resolved coordinates."
            ),
            scope="live_skyview_generated_survey_cutout",
            confidence=0.88,
            citation_ids=[SKYVIEW_CITATION.id],
        )

    def _fact_for_composite(
        self,
        object_slug: str,
        object_name: str,
        products: list[SkyViewProductSummary],
    ) -> Fact:
        surveys = ", ".join(product.survey for product in products)
        return Fact(
            id=f"fact:{object_slug}:skyview:visible-rgb",
            entity_type="generated_composite",
            entity_id=f"view:{object_slug}:skyview:visible-rgb",
            claim=(
                f"SkyView returned public visible-band FITS cutouts ({surveys}) around "
                f"{object_name}'s resolved coordinates, and AstroLens rendered them as "
                "an RGB composite."
            ),
            scope="live_skyview_generated_survey_composite",
            confidence=0.86,
            citation_ids=[SKYVIEW_CITATION.id],
        )

    def _cache_key(
        self,
        query: str,
        *,
        bands: list[BandFamily] | None,
        max_views: int,
        radius_deg: float,
        surveys: list[str] | None,
        pixels: int,
        visual_mode: VisualMode | str | None,
        size: str,
        stretch: str,
    ) -> str:
        resolved_visual_mode = coerce_visual_mode(visual_mode)
        band_key = ",".join(sorted(str(band) for band in bands or []))
        survey_key = ",".join(sorted(normalize_query(survey) for survey in surveys or []))
        return (
            f"skyview:{normalize_query(query)}:{band_key}:{survey_key}:"
            f"{max_views}:{radius_deg:.5f}:{pixels}:{resolved_visual_mode.value}:{size}:{stretch}"
        )


skyview_evidence_service = SkyViewEvidenceService()


def _visible_composite_products(
    products: list[SkyViewProductSummary],
) -> list[SkyViewProductSummary]:
    visible = [
        product
        for product in products
        if product.band_family == BandFamily.VISIBLE and product.wavelength_nm is not None
    ]
    if len(visible) < 3:
        return []
    preferred = [
        product
        for product in visible
        if normalize_query(product.survey) in {"sdssg", "sdssr", "sdssi"}
    ]
    if len(preferred) >= 3:
        return sorted(preferred, key=lambda product: product.wavelength_nm or 0.0)
    return sorted(visible, key=lambda product: product.wavelength_nm or 0.0)[:3]
