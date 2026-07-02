"""Tests for live source dispatch, visual modes, and quality-ranked merging."""

import asyncio
from typing import Any

from astrolens.core.enums import (
    BandFamily,
    CacheStatus,
    TargetValidationStatus,
    VisualAssetTier,
    VisualMode,
)
from astrolens.core.models import (
    Asset,
    CacheMeta,
    CelestialObject,
    Coordinates,
    CrossWavelengthNote,
    EvidenceBundle,
    ImageProvenance,
    ResponseMeta,
    ReusePolicy,
    TargetValidation,
    View,
    ViewScores,
    WarningMessage,
)
from astrolens.services.live_sources import LiveSourceEvidenceService

_REUSE = ReusePolicy(id="reuse:test")
_OBJECT = CelestialObject(
    id="astro:object:m87",
    name="M87",
    coordinates=Coordinates(ra_deg=187.70593, dec_deg=12.39112),
)


class _FakeSource:
    def __init__(self, bundle: EvidenceBundle) -> None:
        self.bundle = bundle
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def bundle_for_query(self, query: str, **kwargs: Any) -> EvidenceBundle:
        self.calls.append((query, kwargs))
        return self.bundle


def _service(mast: _FakeSource, skyview: _FakeSource) -> LiveSourceEvidenceService:
    # Fakes stand in for the concrete source services so merge behavior can be
    # exercised without network I/O.
    return LiveSourceEvidenceService(mast=mast, skyview=skyview)  # type: ignore[arg-type]


def _view(
    label: str,
    tier: VisualAssetTier,
    band: BandFamily,
    source_archive: str,
    *,
    n_products: int = 1,
) -> View:
    return View(
        id=f"view:{label}",
        label=label,
        band_family=band,
        source_archive=source_archive,
        asset=Asset(
            id=f"asset:{label}",
            source_product_ids=[f"product:{label}:{index}" for index in range(n_products)],
            format="png",
            visual_tier=tier,
            asset_url="https://example.test/a.png",
            target_validation=TargetValidation(status=TargetValidationStatus.CENTERED),
            provenance=ImageProvenance(visual_tier=tier, source_record_id=f"rec:{label}"),
            reuse_policy_id=_REUSE.id,
        ),
        reuse=_REUSE,
        scores=ViewScores(overall=0.8),
    )


def _bundle(
    views: list[View],
    warnings: list[WarningMessage] | None = None,
    notes: list[CrossWavelengthNote] | None = None,
) -> EvidenceBundle:
    return EvidenceBundle(
        object=_OBJECT,
        views=views,
        cross_wavelength_notes=notes or [],
        warnings=warnings or [],
        meta=ResponseMeta(request_id="req_test", cache=CacheMeta(status=CacheStatus.MISS)),
    )


def _visible_note() -> CrossWavelengthNote:
    return CrossWavelengthNote(
        band_family=BandFamily.VISIBLE,
        general_meaning="Visible light traces starlight.",
        confidence=0.9,
    )


def _infrared_note() -> CrossWavelengthNote:
    return CrossWavelengthNote(
        band_family=BandFamily.INFRARED,
        general_meaning="Infrared traces dust and cooler material.",
        confidence=0.9,
    )


def test_merge_ranks_sdss_rgb_above_mast_raw_preview_and_keeps_provenance() -> None:
    mast_raw = _view("mast_raw", VisualAssetTier.RAW_ARCHIVE_PREVIEW, BandFamily.VISIBLE, "MAST")
    sdss_rgb = _view(
        "sdss_rgb",
        VisualAssetTier.ASTROLENS_RENDERED,
        BandFamily.VISIBLE,
        "SkyView",
        n_products=3,
    )
    sky_ir = _view("sky_ir", VisualAssetTier.ASTROLENS_RENDERED, BandFamily.INFRARED, "SkyView")

    mast = _FakeSource(
        _bundle([mast_raw], [WarningMessage(code="W_MAST", message="mast note")], [_visible_note()])
    )
    skyview = _FakeSource(
        _bundle(
            [sdss_rgb, sky_ir],
            [WarningMessage(code="W_SKY", message="skyview note")],
            [_visible_note(), _infrared_note()],
        )
    )
    service = _service(mast, skyview)

    bundle = asyncio.run(service.bundle_for_query("M87", sources=("mast", "skyview"), max_views=3))

    labels = [view.label for view in bundle.views]
    assert labels[0] == "sdss_rgb"
    assert set(labels) == {"sdss_rgb", "sky_ir", "mast_raw"}
    top_asset = bundle.views[0].asset
    assert top_asset is not None
    assert top_asset.visual_tier == VisualAssetTier.ASTROLENS_RENDERED
    assert top_asset.provenance is not None
    assert top_asset.provenance.source_record_id == "rec:sdss_rgb"
    assert {warning.code for warning in bundle.warnings} == {"W_MAST", "W_SKY"}
    note_bands = [note.band_family for note in bundle.cross_wavelength_notes]
    assert len(note_bands) == len(set(note_bands))
    assert set(note_bands) <= {view.band_family for view in bundle.views}
    assert mast.calls and skyview.calls


def test_single_source_mast_delegates_without_calling_skyview() -> None:
    mast_view = _view("m", VisualAssetTier.OUTREACH_RELEASE, BandFamily.VISIBLE, "MAST")
    mast = _FakeSource(_bundle([mast_view]))
    skyview = _FakeSource(_bundle([]))
    service = _service(mast, skyview)

    bundle = asyncio.run(service.bundle_for_query("M87", sources=("mast",)))

    assert bundle is mast.bundle
    assert skyview.calls == []


def test_single_source_skyview_delegates_without_calling_mast() -> None:
    skyview_view = _view("s", VisualAssetTier.ASTROLENS_RENDERED, BandFamily.XRAY, "SkyView")
    mast = _FakeSource(_bundle([]))
    skyview = _FakeSource(_bundle([skyview_view]))
    service = _service(mast, skyview)

    bundle = asyncio.run(service.bundle_for_query("M87", sources=("skyview",)))

    assert bundle is skyview.bundle
    assert mast.calls == []


def test_visual_mode_presets_fan_out_to_source_specific_radius_and_pixels() -> None:
    mast = _FakeSource(_bundle([]))
    skyview = _FakeSource(_bundle([]))
    service = _service(mast, skyview)

    asyncio.run(
        service.bundle_for_query(
            "M87",
            visual_mode=VisualMode.WIDE,
            sources=("mast", "skyview"),
        )
    )

    assert mast.calls[0][1]["radius_deg"] == 0.08
    assert skyview.calls[0][1]["radius_deg"] == 0.20
    assert skyview.calls[0][1]["pixels"] == 1536
    assert skyview.calls[0][1]["visual_mode"] == VisualMode.WIDE


def test_explicit_radius_and_pixels_override_visual_mode_presets() -> None:
    skyview = _FakeSource(_bundle([]))
    service = _service(_FakeSource(_bundle([])), skyview)

    asyncio.run(
        service.bundle_for_query(
            "M87",
            visual_mode=VisualMode.WIDE,
            radius_deg=0.04,
            pixels=768,
            sources=("skyview",),
        )
    )

    assert skyview.calls[0][1]["radius_deg"] == 0.04
    assert skyview.calls[0][1]["pixels"] == 768
    assert skyview.calls[0][1]["visual_mode"] == VisualMode.WIDE


class _FakeResolver:
    async def object_live(self, query: str) -> tuple[CelestialObject, CacheStatus]:
        return _OBJECT, CacheStatus.HIT


class _FakeFactsService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def facts_for_object(self, obj: CelestialObject) -> Any:
        from astrolens.core.models import Fact
        from astrolens.services.facts import ObjectFactsResult

        self.calls.append(obj.name)
        return ObjectFactsResult(
            facts=[
                Fact(
                    id="fact:m87:redshift",
                    entity_type="object",
                    entity_id=obj.id,
                    claim="M87 has a measured redshift of z = 0.00428.",
                    scope="catalog_measurement",
                    confidence=0.9,
                    citation_ids=["citation:simbad:tap"],
                    value=0.00428,
                    unit="dimensionless",
                    quantity_kind="redshift",
                    source_fields=["basic.rvz_redshift"],
                )
            ]
        )


class _FakeTargetNameMast(_FakeSource):
    def __init__(self, bundle: EvidenceBundle) -> None:
        super().__init__(bundle)
        self.target_calls: list[tuple[str, dict[str, Any]]] = []

    async def bundle_for_target_name(self, obj: CelestialObject, **kwargs: Any) -> EvidenceBundle:
        self.target_calls.append((obj.name, kwargs))
        return self.bundle


def test_ephemeris_target_routes_to_mast_target_name_search() -> None:
    saturn_view = _view("hst-saturn", VisualAssetTier.PROCESSED_ARCHIVE, BandFamily.VISIBLE, "MAST")
    mast = _FakeTargetNameMast(_bundle([saturn_view]))
    service = LiveSourceEvidenceService(
        mast=mast,  # type: ignore[arg-type]
        skyview=_FakeSource(_bundle([])),  # type: ignore[arg-type]
    )

    bundle = asyncio.run(
        service.bundle_for_query("Saturn", sources=("mast", "skyview"))
    )

    assert mast.target_calls and mast.target_calls[0][0] == "Saturn"
    assert mast.calls == []  # never cone-searched
    assert any(w.code == "EPHEMERIS_TARGET_NAME_SEARCH" for w in bundle.warnings)
    assert any(w.code == "EPHEMERIS_SKYVIEW_EXCLUDED" for w in bundle.warnings)


def test_ephemeris_target_without_skyview_gets_no_skyview_warning() -> None:
    mast = _FakeTargetNameMast(_bundle([]))
    service = LiveSourceEvidenceService(
        mast=mast,  # type: ignore[arg-type]
        skyview=_FakeSource(_bundle([])),  # type: ignore[arg-type]
    )

    bundle = asyncio.run(service.bundle_for_query("Jupiter", sources=("mast",)))

    assert not any(w.code == "EPHEMERIS_SKYVIEW_EXCLUDED" for w in bundle.warnings)
    assert any(w.code == "EPHEMERIS_TARGET_NAME_SEARCH" for w in bundle.warnings)


def test_seed_planets_are_flagged_as_ephemeris_objects() -> None:
    from astrolens.services.repository import repository

    for object_id in (
        "astro:object:saturn",
        "astro:object:jupiter",
        "astro:object:titan",
    ):
        obj = repository.get_object(object_id)
        assert obj.ephemeris_object is True
        assert all(
            "astrolens:curated" in source.name for source in obj.identity_sources
        )

    assert repository.get_object("astro:object:m87").ephemeris_object is False


class _FakeCompositeService:
    def __init__(self, view: View | None) -> None:
        self.view = view
        self.calls: list[str] = []

    async def composite_view(
        self, *, obj: CelestialObject, views: list[View], recipe: Any, size: str = "standard"
    ) -> View | None:
        self.calls.append(obj.name)
        return self.view


def test_composite_true_prepends_multiwavelength_view() -> None:
    composite_view = _view(
        "composite",
        VisualAssetTier.ASTROLENS_RENDERED,
        BandFamily.MULTIWAVELENGTH,
        "AstroLens composite",
    )
    single = _view("hst", VisualAssetTier.PROCESSED_ARCHIVE, BandFamily.VISIBLE, "MAST")
    composites = _FakeCompositeService(composite_view)
    service = LiveSourceEvidenceService(
        mast=_FakeSource(_bundle([single])),  # type: ignore[arg-type]
        skyview=_FakeSource(_bundle([])),  # type: ignore[arg-type]
        composites=composites,  # type: ignore[arg-type]
    )

    bundle = asyncio.run(
        service.bundle_for_query("M87", sources=("mast", "skyview"), composite=True)
    )

    assert composites.calls == ["M87"]
    assert bundle.views[0].band_family == BandFamily.MULTIWAVELENGTH
    assert bundle.views[1].id == single.id


def test_composite_unavailable_degrades_to_warning() -> None:
    composites = _FakeCompositeService(None)
    service = LiveSourceEvidenceService(
        mast=_FakeSource(_bundle([])),  # type: ignore[arg-type]
        skyview=_FakeSource(_bundle([])),  # type: ignore[arg-type]
        composites=composites,  # type: ignore[arg-type]
    )

    bundle = asyncio.run(
        service.bundle_for_query("M87", sources=("mast", "skyview"), composite=True)
    )

    assert any(warning.code == "COMPOSITE_UNAVAILABLE" for warning in bundle.warnings)


def test_composite_defaults_off_and_bundle_shape_unchanged() -> None:
    composites = _FakeCompositeService(None)
    service = LiveSourceEvidenceService(
        mast=_FakeSource(_bundle([])),  # type: ignore[arg-type]
        skyview=_FakeSource(_bundle([])),  # type: ignore[arg-type]
        composites=composites,  # type: ignore[arg-type]
    )

    bundle = asyncio.run(service.bundle_for_query("M87", sources=("mast", "skyview")))

    assert composites.calls == []
    assert bundle.object_facts == []
    assert not any(warning.code.startswith("COMPOSITE") for warning in bundle.warnings)


def test_include_facts_attaches_object_facts_to_bundle() -> None:
    mast = _FakeSource(
        _bundle([_view("hst", VisualAssetTier.PROCESSED_ARCHIVE, BandFamily.VISIBLE, "MAST")])
    )
    facts = _FakeFactsService()
    service = LiveSourceEvidenceService(
        mast=mast,  # type: ignore[arg-type]
        skyview=_FakeSource(_bundle([])),  # type: ignore[arg-type]
        facts=facts,  # type: ignore[arg-type]
        resolver=_FakeResolver(),  # type: ignore[arg-type]
    )

    bundle = asyncio.run(service.bundle_for_query("M87", include_facts=True))

    assert facts.calls == ["M87"]
    assert len(bundle.object_facts) == 1
    assert bundle.object_facts[0].quantity_kind == "redshift"


def test_facts_are_omitted_by_default() -> None:
    mast = _FakeSource(_bundle([]))
    facts = _FakeFactsService()
    service = LiveSourceEvidenceService(
        mast=mast,  # type: ignore[arg-type]
        skyview=_FakeSource(_bundle([])),  # type: ignore[arg-type]
        facts=facts,  # type: ignore[arg-type]
        resolver=_FakeResolver(),  # type: ignore[arg-type]
    )

    bundle = asyncio.run(service.bundle_for_query("M87"))

    assert facts.calls == []
    assert bundle.object_facts == []
