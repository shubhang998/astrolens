"""Cross-source multi-wavelength composites driven by object-type band recipes."""

from __future__ import annotations

import asyncio

from pydantic import Field

from astrolens.core.enums import (
    BandFamily,
    ReuseStatus,
    TargetValidationStatus,
    VisualAssetTier,
)
from astrolens.core.models import (
    Asset,
    AstroLensModel,
    CelestialObject,
    Citation,
    DataProduct,
    ImageProvenance,
    ReusePolicy,
    TargetValidation,
    View,
    ViewScores,
)
from astrolens.services.fits_renderer import (
    FitsRenderer,
    FitsRenderRequest,
    FitsRenderResult,
    SourceFitsProduct,
    product_eligibility,
)
from astrolens.services.repository import normalize_query

COMPOSITE_REUSE = ReusePolicy(
    id="reuse:astrolens:composite",
    status=ReuseStatus.CHECK_SOURCE_POLICY,
    commercial_use="check_source_policy",
    credit_required=True,
    credit_text=(
        "Credit each contributing archive and survey named in the composite provenance."
    ),
    notes=[
        "AstroLens rendered this composite from public archive data across sources; "
        "each channel inherits its own survey's acknowledgement language.",
        "Do not treat generated composites as official press or outreach imagery.",
    ],
)

MANDATORY_COMPOSITE_CAVEAT = (
    "AstroLens rendered this multi-wavelength composite from public archive FITS "
    "data; colors are representative channel mappings, not natural human vision."
)


class BandRecipe(AstroLensModel):
    """Ordered band intent for one object category, with citable rationale."""

    id: str
    object_categories: list[str] = Field(default_factory=list)
    bands: list[BandFamily] = Field(min_length=1)
    rationale: str


BAND_RECIPES: tuple[BandRecipe, ...] = (
    BandRecipe(
        id="recipe:agn",
        object_categories=["agn", "quasar", "seyfert", "blazar", "radio galaxy", "active"],
        bands=[BandFamily.RADIO, BandFamily.XRAY, BandFamily.VISIBLE],
        rationale=(
            "Active galaxies are shaped by their jets and hot accretion environments: "
            "radio traces the jet, X-ray the energetic core, visible the host galaxy."
        ),
    ),
    BandRecipe(
        id="recipe:snr",
        object_categories=["supernova remnant", "snr", "pulsar", "neutron star"],
        bands=[BandFamily.XRAY, BandFamily.RADIO, BandFamily.VISIBLE],
        rationale=(
            "Supernova remnants glow in X-rays from shocked gas and in radio from "
            "accelerated particles; visible light shows surviving filaments."
        ),
    ),
    BandRecipe(
        id="recipe:star-forming",
        object_categories=[
            "hii",
            "star-forming",
            "star formation",
            "nebula",
            "emission",
            "molecular cloud",
        ],
        bands=[BandFamily.INFRARED, BandFamily.VISIBLE],
        rationale=(
            "Star-forming regions hide young stars inside dust: infrared reveals the "
            "embedded stars and warm dust that visible light cannot penetrate."
        ),
    ),
    BandRecipe(
        id="recipe:default",
        object_categories=[],
        bands=[BandFamily.VISIBLE],
        rationale="Visible light is the most broadly interpretable default view.",
    ),
)


def recipe_for_object_type(object_type: str) -> BandRecipe:
    """Pick the band recipe whose category substrings match the object type."""

    normalized = object_type.strip().lower()
    for recipe in BAND_RECIPES:
        if any(category in normalized for category in recipe.object_categories):
            return recipe
    return BAND_RECIPES[-1]


class CompositeService:
    """Build one cross-source multi-wavelength composite view from ranked views."""

    def __init__(self, renderer: FitsRenderer | None = None) -> None:
        self.renderer = renderer or FitsRenderer()

    async def composite_view(
        self,
        *,
        obj: CelestialObject,
        views: list[View],
        recipe: BandRecipe,
        size: str = "standard",
        stretch: str = "asinh",
    ) -> View | None:
        picks = _pick_channel_products(views, recipe)
        if len(picks) < 2:
            return None
        slug = normalize_query(obj.name) or "object"
        render_request = FitsRenderRequest(
            object_id=f"composite:{slug}:{recipe.id.rsplit(':', maxsplit=1)[-1]}",
            products=[fits_product for _view, _product, fits_product in picks],
            size=size,  # type: ignore[arg-type]
            stretch=stretch,  # type: ignore[arg-type]
            max_source_file_mb=180.0,
            preselected=True,
        )
        render_result = await asyncio.to_thread(self.renderer.render, render_request)
        if render_result.status != "complete" or not render_result.asset_url:
            return None
        return self._view_for_render(
            obj=obj,
            slug=slug,
            recipe=recipe,
            picks=picks,
            render_result=render_result,
            stretch=stretch,
        )

    def _view_for_render(
        self,
        *,
        obj: CelestialObject,
        slug: str,
        recipe: BandRecipe,
        picks: list[tuple[View, DataProduct, SourceFitsProduct]],
        render_result: FitsRenderResult,
        stretch: str,
    ) -> View:
        channel_notes = [
            f"{view.band_family}: {view.instrument or view.facility or 'unknown'} "
            f"({view.source_archive})"
            for view, _product, _fits in picks
        ]
        citations = _union_citations([view for view, _product, _fits in picks])
        render_recipe = render_result.recipe
        caveats = [MANDATORY_COMPOSITE_CAVEAT, recipe.rationale]
        if render_recipe is not None:
            caveats.extend(
                caveat for caveat in render_recipe.caveats if caveat not in caveats
            )
        asset = Asset(
            id=render_result.asset_id or f"asset:{slug}:composite",
            source_product_ids=[product.id for _view, product, _fits in picks],
            format="png",
            visual_tier=VisualAssetTier.ASTROLENS_RENDERED,
            width=render_recipe.width if render_recipe else None,
            height=render_recipe.height if render_recipe else None,
            asset_url=render_result.asset_url,
            thumbnail_url=render_result.asset_url,
            false_color=True,
            processing_note=(
                f"AstroLens cross-source composite using {stretch} stretch; channels: "
                + "; ".join(channel_notes)
            ),
            selection_reason=(
                f"Band recipe {recipe.id} selected the highest-ranked FITS product "
                "per wavelength band across archives."
            ),
            target_validation=TargetValidation(
                status=TargetValidationStatus.CENTERED,
                confidence=0.8,
                target_in_frame=True,
                notes=["Channels are reprojected to a common frame centered on the target."],
            ),
            provenance=ImageProvenance(
                visual_tier=VisualAssetTier.ASTROLENS_RENDERED,
                source_archive="AstroLens composite",
                facility="Multiple archives",
                instrument=", ".join(
                    str(view.instrument or view.source_archive) for view, _p, _f in picks
                ),
                source_record_id=render_result.cache_key,
                render_recipe_id=render_result.cache_key,
                notes=channel_notes,
            ),
            credit_text=COMPOSITE_REUSE.credit_text,
            reuse_policy_id=COMPOSITE_REUSE.id,
            citations=citations,
        )
        return View(
            id=f"view:{slug}:composite:{recipe.id.rsplit(':', maxsplit=1)[-1]}",
            label=f"{obj.name} multi-wavelength composite",
            band_family=BandFamily.MULTIWAVELENGTH,
            facility="Multiple archives",
            instrument=", ".join(str(view.band_family) for view, _p, _f in picks),
            source_archive="AstroLens composite",
            asset=asset,
            raw_products=[product for _view, product, _fits in picks],
            facts=[],
            reuse=COMPOSITE_REUSE,
            citations=citations,
            caveats=caveats,
            scores=ViewScores(
                object_match=0.9,
                public_access=1.0,
                asset_availability=0.98,
                preview_quality=0.85,
                science_ready=0.75,
                provenance_quality=0.95,
                citation_quality=0.9,
                renderability=0.95,
                source_reliability=0.85,
                overall=0.92,
            ),
        )


def _pick_channel_products(
    views: list[View],
    recipe: BandRecipe,
) -> list[tuple[View, DataProduct, SourceFitsProduct]]:
    """Choose the best FITS product per recipe band, in ranked view order."""

    picks: list[tuple[View, DataProduct, SourceFitsProduct]] = []
    used_product_ids: set[str] = set()
    for band in recipe.bands:
        for view in views:
            if view.band_family != band:
                continue
            chosen = _first_renderable_product(view, used_product_ids)
            if chosen is None:
                continue
            product, fits_product = chosen
            picks.append((view, product, fits_product))
            used_product_ids.add(product.id)
            break
    return picks


def _first_renderable_product(
    view: View,
    used_product_ids: set[str],
) -> tuple[DataProduct, SourceFitsProduct] | None:
    for product in view.raw_products:
        if product.id in used_product_ids or not product.download_url:
            continue
        fits_product = SourceFitsProduct.from_data_product(product)
        if product_eligibility(fits_product).eligible:
            return product, fits_product
    return None


def _union_citations(views: list[View]) -> list[Citation]:
    seen: dict[str, Citation] = {}
    for view in views:
        for citation in view.citations:
            seen.setdefault(citation.id, citation)
    return list(seen.values())


composite_service = CompositeService()
