import json

from fastapi.testclient import TestClient

from astrolens.api.main import app
from astrolens.api.routes import evidence as evidence_route
from astrolens.core.enums import CacheStatus, ErrorCode, VisualMode
from astrolens.core.errors import AstroLensError
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


def _fake_live_bundle_with_heavy_raw_metadata() -> EvidenceBundle:
    view = repository.views_for_object("astro:object:m87")[0].model_copy(deep=True)
    product = view.raw_products[0].model_copy(deep=True)
    product.raw_metadata = {
        "productFilename": "kept-preview.jpg",
        "dataURI": "mast:HST/product/kept-preview.jpg",
        "description": "stable source field",
        "giant_field": "x" * 20_000,
        "nested_archive_dump": {"unused": "y" * 5_000},
    }
    view.raw_products = [product]
    return EvidenceBundle(
        object=repository.get_object("astro:object:m87"),
        views=[view],
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


def test_search_never_matches_across_word_boundaries() -> None:
    # "vega" is a substring of the normalized concatenation "activegalaxy";
    # it must not match Centaurus A (or anything else in the seed).
    assert repository.find_objects("Vega") == []
    # Word-level and whole-field matching still work.
    assert [obj.name for obj in repository.find_objects("Cen A")] == ["Centaurus A"]
    assert "M87" in [obj.name for obj in repository.find_objects("NGC 4486")]


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
    assert tool_result["_meta"]["astrolens/schemaVersion"] == "astrolens.mcp.v1"


def test_mcp_tool_schemas_publish_response_bounds() -> None:
    listed = client.post("/mcp", json={"jsonrpc": "2.0", "id": 20, "method": "tools/list"})
    tools = {tool["name"]: tool for tool in listed.json()["result"]["tools"]}

    evidence_schema = tools["get_object_evidence"]["inputSchema"]["properties"]
    search_schema = tools["search"]["inputSchema"]["properties"]

    assert evidence_schema["max_views"]["maximum"] == 6
    assert search_schema["limit"]["maximum"] == 10


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


def test_mcp_compacts_raw_metadata_in_structured_content(monkeypatch) -> None:
    async def fake_bundle_for_query(*args, **kwargs) -> EvidenceBundle:
        return _fake_live_bundle_with_heavy_raw_metadata()

    monkeypatch.setattr(
        mcp_tools.live_source_evidence_service,
        "bundle_for_query",
        fake_bundle_for_query,
    )

    called = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "get_object_evidence",
                "arguments": {"object": "M87", "live": True, "max_views": 99},
            },
        },
    )

    assert called.status_code == 200
    tool_result = called.json()["result"]
    product = tool_result["structuredContent"]["views"][0]["raw_products"][0]
    raw_metadata = product["raw_metadata"]
    assert raw_metadata["productFilename"] == "kept-preview.jpg"
    assert "giant_field" not in raw_metadata
    assert "giant_field" in raw_metadata["_omitted_keys"]
    assert len(json.dumps(tool_result["structuredContent"])) < 25_000
    assert tool_result["_meta"]["astrolens/responseProfile"] == "compact-v1"


def test_mcp_maps_source_errors_to_json_rpc_error(monkeypatch) -> None:
    async def failing_bundle_for_query(*args, **kwargs) -> EvidenceBundle:
        raise AstroLensError(
            ErrorCode.SOURCE_TIMEOUT,
            "MAST did not respond before the timeout.",
            retryable=True,
            details={"source": "MAST", "error": "hidden source detail"},
        )

    monkeypatch.setattr(
        mcp_tools.live_source_evidence_service,
        "bundle_for_query",
        failing_bundle_for_query,
    )

    called = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "get_object_evidence",
                "arguments": {"object": "M87", "live": True},
            },
        },
    )

    assert called.status_code == 200
    payload = called.json()
    assert payload["error"]["code"] == -32002
    assert payload["error"]["data"]["code"] == "SOURCE_TIMEOUT"
    assert payload["error"]["data"]["retryable"] is True
    assert "Traceback" not in json.dumps(payload)


def test_mcp_unsupported_band_returns_structured_error() -> None:
    called = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "get_object_evidence",
                "arguments": {"object": "M87", "bands": ["microwave"]},
            },
        },
    )

    assert called.status_code == 200
    payload = called.json()
    assert payload["error"]["code"] == -32602
    assert payload["error"]["data"]["code"] == "UNSUPPORTED_BAND"


def test_rest_source_errors_use_gateway_status_codes(monkeypatch) -> None:
    async def failing_bundle_for_query(*args, **kwargs) -> EvidenceBundle:
        raise AstroLensError(
            ErrorCode.SOURCE_TIMEOUT,
            "MAST did not respond before the timeout.",
            retryable=True,
            details={"source": "MAST"},
        )

    monkeypatch.setattr(
        evidence_route.live_source_evidence_service,
        "bundle_for_query",
        failing_bundle_for_query,
    )

    response = client.get("/v1/evidence", params={"q": "M87", "live": "true"})

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "SOURCE_TIMEOUT"


def test_mcp_exposes_gallery_resource_for_chatgpt_apps() -> None:
    listed = client.post("/mcp", json={"jsonrpc": "2.0", "id": 10, "method": "tools/list"})
    tools = {tool["name"]: tool for tool in listed.json()["result"]["tools"]}
    evidence_tool = tools["get_object_evidence"]

    assert "make_best_visual" in tools
    assert "render_fits_composite" in tools
    assert "get_visual_provenance" in tools
    from astrolens.mcp.gallery_component import GALLERY_URI

    assert evidence_tool["_meta"]["openai/outputTemplate"] == GALLERY_URI
    assert evidence_tool["_meta"]["ui"]["resourceUri"] == GALLERY_URI
    assert GALLERY_URI.startswith("ui://astrolens/gallery-")  # content-hashed

    resource_response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 11,
            "method": "resources/read",
            "params": {"uri": GALLERY_URI},
        },
    )

    assert resource_response.status_code == 200
    content = resource_response.json()["result"]["contents"][0]
    assert content["mimeType"] == "text/html"
    assert "window.openai.toolOutput" in content["text"]
    assert content["_meta"]["openai/widgetPrefersBorder"] is True
