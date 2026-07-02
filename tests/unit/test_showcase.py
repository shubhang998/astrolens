import asyncio
from typing import Any

import pytest

from astrolens.api.routes.mcp import _mcp_tool_result
from astrolens.connectors.simbad_tap import (
    SimbadCategoryHit,
    SimbadCategorySearchResult,
)
from astrolens.core.enums import (
    BandFamily,
    CacheStatus,
    ErrorCode,
    TargetValidationStatus,
    VisualAssetTier,
)
from astrolens.core.errors import AstroLensError
from astrolens.core.models import (
    Asset,
    CacheMeta,
    CelestialObject,
    Citation,
    Coordinates,
    EvidenceBundle,
    Fact,
    ImageProvenance,
    ResponseMeta,
    ReusePolicy,
    TargetValidation,
    View,
    ViewScores,
)
from astrolens.mcp.hardening import MCP_MAX_RESPONSE_BYTES
from astrolens.services.facts import ObjectFactsResult
from astrolens.services.showcase import ShowcaseService

_REUSE = ReusePolicy(id="reuse:test", credit_text="Credit the test archive")
_OBJECT = CelestialObject(
    id="astro:object:m87",
    name="M87",
    type="AGN",
    coordinates=Coordinates(ra_deg=187.70593, dec_deg=12.39112),
)

_FACTS = [
    Fact(
        id="fact:m87:classification",
        entity_type="object",
        entity_id=_OBJECT.id,
        claim="M87 is classified as an active galactic nucleus in the SIMBAD database.",
        scope="catalog_measurement",
        confidence=0.8,
        citation_ids=["citation:simbad:tap"],
        quantity_kind="classification",
        source_fields=["basic.otype"],
    ),
    Fact(
        id="fact:m87:distance",
        entity_type="object",
        entity_id=_OBJECT.id,
        claim="From its redshift, M87 lies about 62 million light-years away.",
        scope="derived_measurement",
        confidence=0.7,
        citation_ids=["citation:simbad:tap"],
        value=62_000_000.0,
        unit="light-years",
        quantity_kind="distance",
        source_fields=["basic.rvz_redshift"],
        derivation="astropy.cosmology.Planck18.luminosity_distance(z)",
        scale_comparison="about 620 times the diameter of the Milky Way away",
    ),
    Fact(
        id="fact:m87:lookback_time",
        entity_type="object",
        entity_id=_OBJECT.id,
        claim="The light from M87 seen today left it about 62 million years ago.",
        scope="derived_measurement",
        confidence=0.7,
        citation_ids=["citation:simbad:tap"],
        value=0.062,
        unit="Gyr",
        quantity_kind="lookback_time",
        source_fields=["basic.rvz_redshift"],
        derivation="astropy.cosmology.Planck18.lookback_time(z)",
    ),
]


def _view(label: str, band: BandFamily, *, with_asset: bool = True) -> View:
    asset = None
    if with_asset:
        asset = Asset(
            id=f"asset:{label}",
            source_product_ids=[f"product:{label}"],
            format="png",
            visual_tier=VisualAssetTier.ASTROLENS_RENDERED,
            asset_url=f"/v1/rendered/{label}.png",
            target_validation=TargetValidation(status=TargetValidationStatus.CENTERED),
            provenance=ImageProvenance(visual_tier=VisualAssetTier.ASTROLENS_RENDERED),
            credit_text="Credit the test archive",
            reuse_policy_id=_REUSE.id,
        )
    return View(
        id=f"view:{label}",
        label=label,
        band_family=band,
        source_archive="MAST",
        asset=asset,
        reuse=_REUSE,
        citations=[Citation(id=f"cite:{label}", title=label, source="MAST")],
        scores=ViewScores(overall=0.8),
    )


def _bundle(views: list[View]) -> EvidenceBundle:
    return EvidenceBundle(
        object=_OBJECT,
        views=views,
        object_facts=_FACTS,
        fact_citations=[Citation(id="citation:simbad:tap", title="SIMBAD", source="SIMBAD")],
        meta=ResponseMeta(
            request_id="req_test",
            cache=CacheMeta(status=CacheStatus.MISS, stale=False),
        ),
    )


class FakeLiveSources:
    def __init__(self, bundle: EvidenceBundle) -> None:
        self.bundle = bundle
        self.calls: list[dict[str, Any]] = []

    async def bundle_for_query(self, query: str, **kwargs: Any) -> EvidenceBundle:
        self.calls.append({"query": query, **kwargs})
        return self.bundle


class FakeFacts:
    async def facts_for_object(self, obj: CelestialObject) -> ObjectFactsResult:
        return ObjectFactsResult(
            facts=_FACTS,
            citations=[Citation(id="citation:simbad:tap", title="SIMBAD", source="SIMBAD")],
        )


class FakeSimbad:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def search_category(self, **kwargs: Any) -> SimbadCategorySearchResult:
        self.calls.append(kwargs)
        return SimbadCategorySearchResult(
            query_adql="SELECT ...",
            hits=[
                SimbadCategoryHit(
                    main_id="3C 273",
                    otype="QSO",
                    ra_deg=187.28,
                    dec_deg=2.05,
                    v_mag=12.85,
                    redshift=0.1583,
                )
            ],
        )


def _service(bundle: EvidenceBundle | None = None, simbad: Any = None) -> ShowcaseService:
    return ShowcaseService(
        live_sources=FakeLiveSources(bundle or _bundle([])),  # type: ignore[arg-type]
        facts=FakeFacts(),  # type: ignore[arg-type]
        simbad=simbad or FakeSimbad(),  # type: ignore[arg-type]
    )


def test_show_object_prefers_composite_hero_and_bands_panels() -> None:
    composite = _view("composite", BandFamily.MULTIWAVELENGTH)
    views = [
        composite,
        _view("visible-a", BandFamily.VISIBLE),
        _view("visible-b", BandFamily.VISIBLE),
        _view("xray", BandFamily.XRAY),
        _view("radio", BandFamily.RADIO),
        _view("ir", BandFamily.INFRARED),
    ]
    bundle = _bundle(views)
    live = FakeLiveSources(bundle)
    service = ShowcaseService(
        live_sources=live,  # type: ignore[arg-type]
        facts=FakeFacts(),  # type: ignore[arg-type]
        simbad=FakeSimbad(),  # type: ignore[arg-type]
    )

    payload = asyncio.run(service.show_object("M87"))

    assert live.calls[0]["composite"] is True
    assert live.calls[0]["include_facts"] is True
    assert live.calls[0]["size"] == "thumbnail"
    assert payload["hero_view"]["id"] == "view:composite"
    # Only the two best images are shown: the composite hero plus one distinct
    # supporting band panel.
    assert len(payload["views"]) == 2
    assert payload["views"][0]["id"] == "view:composite"
    assert len(payload["panels"]) == 1
    assert payload["panels"][0]["band_family"] == "visible"
    assert len(payload["credits"]) == len(payload["views"])
    assert all("Credit" in credit["credit_line"] for credit in payload["credits"])
    assert payload["suggested_followups"]


def test_hero_prefers_a_color_view_over_a_grayscale_archive_preview() -> None:
    # Ranked first: a single-filter archive preview (often grayscale).
    # Ranked second: a three-channel color composite. The hero slot should
    # take the color view; the preview remains available as the panel.
    gray_preview = _view("hst-single", BandFamily.VISIBLE)
    composite = _view("dss2-rgb", BandFamily.VISIBLE)
    composite.asset.source_product_ids = ["p1", "p2", "p3"]  # type: ignore[union-attr]
    service = _service(_bundle([gray_preview, composite]))

    payload = asyncio.run(service.show_object("Crab Nebula"))

    assert payload["hero_view"]["id"] == "view:dss2-rgb"
    assert [v["id"] for v in payload["views"]] == ["view:dss2-rgb", "view:hst-single"]


def test_hero_stays_ranked_first_when_no_color_view_is_near_the_top() -> None:
    views = [_view(f"gray-{i}", BandFamily.VISIBLE) for i in range(4)]
    service = _service(_bundle(views))

    payload = asyncio.run(service.show_object("M87"))

    assert payload["hero_view"]["id"] == "view:gray-0"


def test_show_object_does_not_show_the_same_image_twice() -> None:
    # Two same-band views sharing one asset URL must collapse to a single image.
    dup_a = _view("a", BandFamily.VISIBLE)
    dup_b = _view("b", BandFamily.VISIBLE)
    dup_b.asset.asset_url = dup_a.asset.asset_url  # type: ignore[union-attr]
    service = _service(_bundle([dup_a, dup_b]))

    payload = asyncio.run(service.show_object("Saturn"))

    urls = [(v.get("asset") or {}).get("asset_url") for v in payload["views"]]
    assert len([u for u in urls if u]) == len(set(u for u in urls if u))


def test_planet_facts_produce_headline_and_narrative() -> None:
    planet_facts = [
        Fact(
            id="fact:saturn:diameter",
            entity_type="object",
            entity_id="astro:object:saturn",
            claim="Saturn's equatorial diameter is about 120,536 km.",
            scope="curated_planetary_fact",
            confidence=0.9,
            citation_ids=["citation:nssdc:planetary-fact-sheet"],
            value=120_536.0,
            unit="km",
            quantity_kind="diameter",
            source_fields=["nssdc.planetary_fact_sheet"],
            scale_comparison="about 9.4 times the diameter of Earth",
        ),
        Fact(
            id="fact:saturn:density",
            entity_type="object",
            entity_id="astro:object:saturn",
            claim="Saturn's mean density is about 687 kg per cubic meter.",
            scope="curated_planetary_fact",
            confidence=0.9,
            citation_ids=["citation:nssdc:planetary-fact-sheet"],
            quantity_kind="density",
            source_fields=["nssdc.planetary_fact_sheet"],
            scale_comparison="less dense than water",
        ),
    ]
    bundle = _bundle([_view("hst", BandFamily.VISIBLE)]).model_copy(
        update={
            "object": _OBJECT.model_copy(
                update={"name": "Saturn", "type": "solar system planet"}
            ),
            "object_facts": planet_facts,
        }
    )
    service = _service(bundle)

    payload = asyncio.run(service.show_object("Saturn"))

    assert "120,536 km" in payload["headline"]
    assert payload["why_interesting"] is not None
    assert "less dense than water" in payload["why_interesting"]


def test_show_object_headline_and_why_interesting_come_only_from_facts() -> None:
    service = _service(_bundle([_view("visible", BandFamily.VISIBLE)]))

    payload = asyncio.run(service.show_object("M87"))

    assert payload["headline"].startswith(_FACTS[0].claim.rstrip("."))
    assert "620 times the diameter of the Milky Way" in payload["headline"]
    # Every sentence in why_interesting must be a fact claim or scale comparison.
    why = payload["why_interesting"]
    assert why is not None
    for fact in _FACTS:
        if fact.quantity_kind in {"lookback_time", "distance"}:
            assert fact.claim.rstrip(".") in why


def test_explain_object_returns_facts_without_imaging() -> None:
    service = _service()

    payload = asyncio.run(service.explain_object("M87"))

    assert payload["object"]["id"] == _OBJECT.id
    assert len(payload["object_facts"]) == len(_FACTS)
    assert all(fact["source_fields"] for fact in payload["object_facts"])
    assert "views" not in payload


def test_find_objects_maps_category_and_adds_followups() -> None:
    simbad = FakeSimbad()
    service = _service(simbad=simbad)

    payload = asyncio.run(service.find_objects("quasar", limit=50, random_sample=True))

    assert simbad.calls[0]["otype"] == "QSO"
    assert simbad.calls[0]["limit"] == 10  # clamped
    assert simbad.calls[0]["random_sample"] is True
    assert payload["hits"][0]["main_id"] == "3C 273"
    assert payload["hits"][0]["followup"] == 'show_object {"object": "3C 273"}'


def test_find_objects_falls_back_to_curated_examples_when_simbad_is_down() -> None:
    class DownSimbad:
        async def search_category(self, **kwargs: Any) -> None:
            raise AstroLensError(
                ErrorCode.SOURCE_TIMEOUT,
                "SIMBAD TAP query failed on all mirrors.",
                retryable=True,
            )

    service = _service(simbad=DownSimbad())

    payload = asyncio.run(service.find_objects("quasar", random_sample=True))

    assert [hit["main_id"] for hit in payload["hits"]] == ["3C 273"]
    assert payload["hits"][0]["followup"] == 'show_object {"object": "3C 273"}'
    assert any("curated" in warning for warning in payload["warnings"])


def test_find_objects_rejects_unknown_category_with_teaching_error() -> None:
    service = _service()

    with pytest.raises(AstroLensError) as exc_info:
        asyncio.run(service.find_objects("wormhole"))

    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR
    assert "quasar" in exc_info.value.details["supported_categories"]


def test_find_objects_rejects_ephemeris_anchor() -> None:
    service = _service()

    with pytest.raises(AstroLensError) as exc_info:
        asyncio.run(service.find_objects("quasar", near_object="Saturn"))

    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR
    assert "moving target" in exc_info.value.message


def test_show_object_payload_fits_response_byte_budget() -> None:
    # Worst-case shape: composite hero + max panels, all with assets and facts.
    views = [
        _view("composite", BandFamily.MULTIWAVELENGTH),
        _view("visible", BandFamily.VISIBLE),
        _view("xray", BandFamily.XRAY),
        _view("radio", BandFamily.RADIO),
        _view("ir", BandFamily.INFRARED),
        _view("uv", BandFamily.ULTRAVIOLET),
    ]
    service = _service(_bundle(views))

    payload = asyncio.run(service.show_object("M87"))
    result = _mcp_tool_result(payload)

    assert result["_meta"]["astrolens/structuredContentBytes"] <= MCP_MAX_RESPONSE_BYTES