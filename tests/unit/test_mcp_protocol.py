"""JSON-RPC protocol conformance tests for the /mcp endpoint."""

import pytest
from fastapi.testclient import TestClient

from astrolens.api.main import app
from astrolens.api.routes.mcp import _mcp_tool_result
from astrolens.core.enums import ErrorCode
from astrolens.core.errors import AstroLensError
from astrolens.mcp.hardening import (
    MCP_MAX_RESPONSE_BYTES,
    RAW_METADATA_ALLOWLIST,
)

client = TestClient(app)


def test_mcp_lists_sixteen_tools_including_heroes() -> None:
    response = client.post("/mcp", json={"jsonrpc": "2.0", "id": 100, "method": "tools/list"})

    tools = {tool["name"]: tool for tool in response.json()["result"]["tools"]}
    assert len(tools) == 16
    assert {"show_object", "explain_object", "find_objects"} <= set(tools)
    find_schema = tools["find_objects"]["inputSchema"]["properties"]
    assert find_schema["limit"]["maximum"] == 10
    assert find_schema["radius_deg"]["maximum"] == 15.0
    assert tools["show_object"]["_meta"]["openai/outputTemplate"]


def test_mcp_notification_gets_no_response_body() -> None:
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
    )

    assert response.status_code == 202
    assert response.content == b""


def test_mcp_batch_request_is_rejected_with_invalid_request() -> None:
    response = client.post(
        "/mcp",
        json=[{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}],
    )

    body = response.json()
    assert body["error"]["code"] == -32600
    assert "batch" in body["error"]["message"].lower()


def test_mcp_malformed_json_returns_parse_error() -> None:
    response = client.post(
        "/mcp",
        content=b'{"jsonrpc": "2.0", "id": 1,',
        headers={"Content-Type": "application/json"},
    )

    body = response.json()
    assert body["error"]["code"] == -32700
    assert body["id"] is None


def test_mcp_missing_jsonrpc_field_is_invalid_request() -> None:
    response = client.post("/mcp", json={"id": 1, "method": "tools/list"})

    body = response.json()
    assert body["error"]["code"] == -32600


def test_mcp_unknown_method_returns_method_not_found() -> None:
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 7, "method": "tools/delete"},
    )

    body = response.json()
    assert body["id"] == 7
    assert body["error"]["code"] == -32601


def test_mcp_unknown_tool_returns_invalid_params_with_tool_list() -> None:
    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {"name": "create_lesson", "arguments": {}},
        },
    )

    body = response.json()
    assert body["error"]["code"] == -32602
    assert body["error"]["data"]["code"] == ErrorCode.VALIDATION_ERROR
    assert "get_object_evidence" in body["error"]["data"]["details"]["available_tools"]


def test_mcp_ambiguous_object_is_surfaced_not_silently_resolved() -> None:
    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "get_best_views", "arguments": {"object": "NGC"}},
        },
    )

    body = response.json()
    assert body["error"]["code"] == -32602
    assert body["error"]["data"]["code"] == ErrorCode.OBJECT_AMBIGUOUS
    alternatives = body["error"]["data"]["details"]["alternatives"]
    assert len(alternatives) > 1
    assert all("id" in alternative and "name" in alternative for alternative in alternatives)


def test_mcp_tool_result_enforces_response_byte_cap() -> None:
    oversized = {"object": {"name": "M87"}, "blob": "x" * (MCP_MAX_RESPONSE_BYTES + 1)}

    with pytest.raises(AstroLensError) as exc_info:
        _mcp_tool_result(oversized)

    assert exc_info.value.code == ErrorCode.PRODUCT_TOO_LARGE
    assert exc_info.value.retryable is False


def test_mcp_tool_result_drops_raw_metadata_before_failing_on_size() -> None:
    # Allowlisted keys under the per-value truncation limit survive compaction,
    # so enough of them across views can still exceed the response cap.
    big_metadata = {key: "x" * 290 for key in RAW_METADATA_ALLOWLIST}
    payload = {
        "object": {"name": "M87"},
        "views": [
            {
                "label": f"view-{index}",
                "raw_products": [
                    {"id": f"prod-{index}-{position}", "raw_metadata": dict(big_metadata)}
                    for position in range(4)
                ],
            }
            for index in range(6)
        ],
    }

    result = _mcp_tool_result(payload)

    first_product = result["structuredContent"]["views"][0]["raw_products"][0]
    assert "raw_metadata" not in first_product
    assert (
        result["_meta"]["astrolens/structuredContentBytes"] <= MCP_MAX_RESPONSE_BYTES
    )
