import asyncio

from astrolens.core.enums import BandFamily, TargetValidationStatus, VisualAssetTier
from astrolens.core.models import (
    Asset,
    CelestialObject,
    Citation,
    Coordinates,
    DataProduct,
    ImageProvenance,
    ReusePolicy,
    TargetValidation,
    View,
    ViewScores,
)
from astrolens.services.composites import (
    BAND_RECIPES,
    MANDATORY_COMPOSITE_CAVEAT,
    CompositeService,
    recipe_for_object_type,
)
from astrolens.services.fits_renderer import FitsRenderRequest, FitsRenderResult

_REUSE = ReusePolicy(id="reuse:test")
_OBJECT = CelestialObject(
    id="astro:object:m87",
    name="M87",
    type="AGN",
    coordinates=Coordinates(ra_deg=187.70593, dec_deg=12.39112),
)


def _fits_view(
    label: str,
    band: BandFamily,
    source_archive: str,
    *,
    citation_id: str,
    renderable: bool = True,
) -> View:
    product = DataProduct(
        id=f"product:{label}",
        observation_id=f"obs:{label}",
        product_type="SCIENCE" if renderable else "PREVIEW",
        file_format="fits" if renderable else "jpg",
        calibration_level="3",
        download_url=f"https://mast.stsci.edu/{label}_drc.fits",
        source_record_id=f"rec:{label}",
        raw_metadata={"filters": label.upper(), "wavelength_nm": 500.0},
    )
    return View(
        id=f"view:{label}",
        label=label,
        band_family=band,
        instrument=label.upper(),
        source_archive=source_archive,
        asset=Asset(
            id=f"asset:{label}",
            source_product_ids=[product.id],
            format="png",
            visual_tier=VisualAssetTier.PROCESSED_ARCHIVE,
            asset_url="https://example.test/a.png",
            target_validation=TargetValidation(status=TargetValidationStatus.CENTERED),
            provenance=ImageProvenance(
                visual_tier=VisualAssetTier.PROCESSED_ARCHIVE,
                source_record_id=f"rec:{label}",
            ),
            reuse_policy_id=_REUSE.id,
        ),
        raw_products=[product],
        reuse=_REUSE,
        citations=[Citation(id=citation_id, title=label, source=source_archive)],
        scores=ViewScores(overall=0.8),
    )


class FakeRenderer:
    def __init__(self, status: str = "complete") -> None:
        self.status = status
        self.requests: list[FitsRenderRequest] = []

    def render(self, request: FitsRenderRequest) -> FitsRenderResult:
        self.requests.append(request)
        return FitsRenderResult(
            status=self.status,  # type: ignore[arg-type]
            asset_id="asset:test:composite",
            asset_url="/v1/rendered/composite.png" if self.status == "complete" else None,
            cache_key="render:test:composite",
        )


def test_recipe_resolution_matches_object_categories() -> None:
    assert recipe_for_object_type("AGN").id == "recipe:agn"
    assert recipe_for_object_type("Seyfert 2 galaxy").id == "recipe:agn"
    assert recipe_for_object_type("supernova remnant").id == "recipe:snr"
    assert recipe_for_object_type("HII region nebula").id == "recipe:star-forming"
    assert recipe_for_object_type("spiral galaxy").id == "recipe:default"
    assert recipe_for_object_type("").id == "recipe:default"
    assert BAND_RECIPES[-1].id == "recipe:default"


def test_composite_mixes_archives_and_marks_provenance() -> None:
    renderer = FakeRenderer()
    service = CompositeService(renderer=renderer)  # type: ignore[arg-type]
    views = [
        _fits_view("nvss", BandFamily.RADIO, "SkyView", citation_id="cite:skyview"),
        _fits_view("rass", BandFamily.XRAY, "SkyView", citation_id="cite:skyview"),
        _fits_view("hst", BandFamily.VISIBLE, "MAST", citation_id="cite:mast"),
    ]

    view = asyncio.run(
        service.composite_view(
            obj=_OBJECT,
            views=views,
            recipe=recipe_for_object_type("AGN"),
        )
    )

    assert view is not None
    assert view.band_family == BandFamily.MULTIWAVELENGTH
    assert view.source_archive == "AstroLens composite"
    assert renderer.requests[0].preselected is True
    assert len(renderer.requests[0].products) == 3
    assert MANDATORY_COMPOSITE_CAVEAT in view.caveats
    assert any("radio" in caveat.lower() or "jet" in caveat.lower() for caveat in view.caveats)
    assert {citation.id for citation in view.citations} == {"cite:skyview", "cite:mast"}
    assert view.asset is not None
    assert view.asset.visual_tier == VisualAssetTier.ASTROLENS_RENDERED
    assert view.asset.false_color is True
    assert view.asset.provenance is not None
    assert any("MAST" in note for note in view.asset.provenance.notes)


def test_composite_returns_none_with_fewer_than_two_channels() -> None:
    renderer = FakeRenderer()
    service = CompositeService(renderer=renderer)  # type: ignore[arg-type]
    views = [
        _fits_view("hst", BandFamily.VISIBLE, "MAST", citation_id="cite:mast"),
        _fits_view("bad", BandFamily.RADIO, "SkyView", citation_id="cite:sv", renderable=False),
    ]

    view = asyncio.run(
        service.composite_view(
            obj=_OBJECT,
            views=views,
            recipe=recipe_for_object_type("AGN"),
        )
    )

    assert view is None
    assert renderer.requests == []


def test_composite_returns_none_when_render_fails() -> None:
    renderer = FakeRenderer(status="failed")
    service = CompositeService(renderer=renderer)  # type: ignore[arg-type]
    views = [
        _fits_view("nvss", BandFamily.RADIO, "SkyView", citation_id="cite:skyview"),
        _fits_view("hst", BandFamily.VISIBLE, "MAST", citation_id="cite:mast"),
    ]

    view = asyncio.run(
        service.composite_view(
            obj=_OBJECT,
            views=views,
            recipe=recipe_for_object_type("AGN"),
        )
    )

    assert view is None
    assert len(renderer.requests) == 1
