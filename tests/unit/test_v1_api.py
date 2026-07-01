from fastapi.testclient import TestClient

from astrolens.api.main import app
from astrolens.api.routes import evidence as evidence_route
from astrolens.core.enums import CacheStatus, VisualMode
from astrolens.core.models import CacheMeta, EvidenceBundle, ResponseMeta
from astrolens.mcp import tools as mcp_tools
from astrolens.services.repository import repository

client = TestClient(app)


def _fake_live_bundle() -> EvidenceBundle:
    return EvidenceBundle(
        object=repository.get_object("astro:object:m87"),
        views=[],
        warnings=[],
        meta=ResponseMeta(request_id="req_test", cache=CacheMeta(status=CacheStatus.MISS)),
    )


def test_resolve_m87_returns_identity_and_provenance() -> None:
    response = client.get("/v1/resolve", params={"q": "M87"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["object_id"] == "astro:object:m87"
    assert "Messier 87" in payload["aliases"]
    assert payload["sources"]


def test_search_returns_curated_objects() -> None:
    response = client.get("/v1/search", params={"q": "Crab", "limit": 5})

    assert response.status_code == 200
    results = response.json()["results"]
    assert results[0]["id"] == "astro:object:crab_nebula"


def test_evidence_bundle_has_views_assets_citations_reuse_and_caveats() -> None:
    response = client.get(
        "/v1/evidence",
        params={"q": "Crab Nebula", "bands": "visible,infrared,xray,radio", "max_views": 6},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["object"]["id"] == "astro:object:crab_nebula"
    assert len(payload["views"]) >= 4
    for view in payload["views"]:
        assert view["asset"]
        assert view["citations"]
        assert view["reuse"]["status"]
        assert view["caveats"]


def test_object_views_endpoint_filters_bands() -> None:
    response = client.get(
        "/v1/objects/astro:object:m87/views",
        params={"bands": "xray,radio", "max": 4},
    )

    assert response.status_code == 200
    bands = {view["band_family"] for view in response.json()["views"]}
    assert bands == {"xray", "radio"}


def test_compare_returns_one_entry_per_requested_band() -> None:
    response = client.post(
        "/v1/compare",
        json={"object": "M87", "bands": ["visible", "xray", "radio"], "max_views_per_band": 1},
    )

    assert response.status_code == 200
    comparison = response.json()["comparison"]
    assert [entry["band_family"] for entry in comparison] == ["visible", "xray", "radio"]


def test_asset_citations_and_raw_links_are_available() -> None:
    asset_response = client.get("/v1/assets/asset:m87:visible:preview")
    assert asset_response.status_code == 200
    assert asset_response.json()["citations"]

    citation_response = client.get("/v1/assets/asset:m87:visible:preview/citations")
    assert citation_response.status_code == 200
    assert citation_response.json()["citations"]

    raw_response = client.get("/v1/products/product:mast:m87:visible:preview/raw-links")
    assert raw_response.status_code == 200
    assert raw_response.json()["raw_links"]


def test_render_returns_cached_asset_for_seed_product() -> None:
    response = client.post(
        "/v1/render",
        json={"product_id": "product:mast:m87:visible:preview", "output_format": "png"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "complete"
    assert payload["asset"]["id"] == "asset:m87:visible:preview"


def test_mcp_lists_and_calls_read_only_tools() -> None:
    listed = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert listed.status_code == 200
    tools = {tool["name"] for tool in listed.json()["result"]["tools"]}
    assert "get_object_evidence" in tools
    assert "create_lesson" not in tools

    called = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "get_object_evidence",
                "arguments": {"object": "M87", "bands": ["visible", "xray"], "max_views": 2},
            },
        },
    )
    assert called.status_code == 200
    tool_result = called.json()["result"]
    assert tool_result["content"][0]["type"] == "text"
    result = tool_result["structuredContent"]
    assert result["object"]["id"] == "astro:object:m87"
    assert len(result["views"]) == 2


def test_live_evidence_route_uses_live_service(monkeypatch) -> None:
    seen = {}

    async def fake_bundle_for_query(
        query: str,
        *,
        bands=None,
        max_views: int = 6,
        visual_mode: VisualMode = VisualMode.CONTEXT,
        radius_deg: float | None = None,
        missions=("HST", "JWST"),
        rank_mode: str = "best_visual",
        sources=("mast",),
        skyview_surveys=None,
        pixels: int | None = None,
    ) -> EvidenceBundle:
        seen["query"] = query
        seen["max_views"] = max_views
        seen["visual_mode"] = visual_mode
        seen["radius_deg"] = radius_deg
        seen["missions"] = missions
        seen["rank_mode"] = rank_mode
        seen["sources"] = sources
        seen["skyview_surveys"] = skyview_surveys
        seen["pixels"] = pixels
        return _fake_live_bundle()

    monkeypatch.setattr(
        evidence_route.live_source_evidence_service,
        "bundle_for_query",
        fake_bundle_for_query,
    )

    response = client.get(
        "/v1/evidence",
        params={"q": "M87", "live": "true", "max_views": 2, "visual_mode": "wide"},
    )

    assert response.status_code == 200
    assert response.json()["object"]["id"] == "astro:object:m87"
    assert seen == {
        "query": "M87",
        "max_views": 2,
        "visual_mode": VisualMode.WIDE,
        "radius_deg": None,
        "missions": ("HST", "JWST"),
        "rank_mode": "best_visual",
        "sources": ("mast",),
        "skyview_surveys": None,
        "pixels": None,
    }


def test_mcp_get_object_evidence_supports_live_argument(monkeypatch) -> None:
    seen = {}

    async def fake_bundle_for_query(
        query: str,
        *,
        bands=None,
        max_views: int = 6,
        visual_mode: VisualMode = VisualMode.CONTEXT,
        radius_deg: float | None = None,
        missions=("HST", "JWST"),
        rank_mode: str = "best_visual",
        sources=("mast",),
        skyview_surveys=None,
        pixels: int | None = None,
    ) -> EvidenceBundle:
        seen["query"] = query
        seen["bands"] = bands
        seen["max_views"] = max_views
        seen["visual_mode"] = visual_mode
        seen["radius_deg"] = radius_deg
        seen["missions"] = missions
        seen["rank_mode"] = rank_mode
        seen["sources"] = sources
        seen["skyview_surveys"] = skyview_surveys
        seen["pixels"] = pixels
        return _fake_live_bundle()

    monkeypatch.setattr(
        mcp_tools.live_source_evidence_service,
        "bundle_for_query",
        fake_bundle_for_query,
    )

    called = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "get_object_evidence",
                "arguments": {
                    "object": "M87",
                    "bands": ["infrared"],
                    "max_views": 2,
                    "live": True,
                    "visual_mode": "wide",
                    "radius_deg": 0.02,
                    "sources": ["skyview"],
                    "skyview_surveys": ["DSS2 Red"],
                    "pixels": 256,
                },
            },
        },
    )

    assert called.status_code == 200
    tool_result = called.json()["result"]
    assert tool_result["content"][0]["type"] == "text"
    assert tool_result["structuredContent"]["object"]["id"] == "astro:object:m87"
    assert seen["query"] == "M87"
    assert seen["bands"] == ["infrared"]
    assert seen["max_views"] == 2
    assert seen["visual_mode"] == VisualMode.WIDE
    assert seen["radius_deg"] == 0.02
    assert seen["missions"] == ("HST", "JWST")
    assert seen["rank_mode"] == "best_visual"
    assert seen["sources"] == ("skyview",)
    assert seen["skyview_surveys"] == ["DSS2 Red"]
    assert seen["pixels"] == 256


def test_mcp_exposes_gallery_resource_for_chatgpt_apps() -> None:
    listed = client.post("/mcp", json={"jsonrpc": "2.0", "id": 10, "method": "tools/list"})
    tools = {tool["name"]: tool for tool in listed.json()["result"]["tools"]}
    evidence_tool = tools["get_object_evidence"]

    assert "make_best_visual" in tools
    assert "render_fits_composite" in tools
    assert "get_visual_provenance" in tools
    assert evidence_tool["_meta"]["openai/outputTemplate"] == "ui://astrolens/gallery.html"
    assert evidence_tool["_meta"]["ui"]["resourceUri"] == "ui://astrolens/gallery.html"

    resource_response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 11,
            "method": "resources/read",
            "params": {"uri": "ui://astrolens/gallery.html"},
        },
    )

    assert resource_response.status_code == 200
    content = resource_response.json()["result"]["contents"][0]
    assert content["mimeType"] == "text/html"
    assert "window.openai.toolOutput" in content["text"]
    assert content["_meta"]["openai/widgetPrefersBorder"] is True
