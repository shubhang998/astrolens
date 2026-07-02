"""Small JSON-RPC MCP-style endpoint for read-only AstroLens tools."""

import json
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from astrolens import __version__
from astrolens.core.enums import ErrorCode
from astrolens.core.errors import AstroLensError
from astrolens.mcp.gallery_component import GALLERY_HTML, GALLERY_RESOURCE, GALLERY_RESOURCE_META
from astrolens.mcp.hardening import (
    MCP_MAX_RESPONSE_BYTES,
    MCP_RESPONSE_PROFILE,
    MCP_SCHEMA_VERSION,
    compact_mcp_payload,
)
from astrolens.mcp.tools import TOOL_DEFINITIONS, UnknownMcpToolError, call_tool

router = APIRouter(tags=["mcp"])


def _mcp_tool_result(payload: Any, *, base_url: str | None = None) -> dict[str, Any]:
    """Wrap service JSON in a ChatGPT-compatible MCP tool result."""

    structured = payload if isinstance(payload, dict) else {"result": payload}
    if base_url:
        structured = _absolutize_relative_asset_urls(structured, base_url=base_url)
    structured = compact_mcp_payload(structured)
    structured_json = json.dumps(structured, separators=(",", ":"), default=str)
    if len(structured_json.encode("utf-8")) > MCP_MAX_RESPONSE_BYTES:
        structured = _strip_raw_metadata(structured)
        structured_json = json.dumps(structured, separators=(",", ":"), default=str)
    if len(structured_json.encode("utf-8")) > MCP_MAX_RESPONSE_BYTES:
        raise AstroLensError(
            ErrorCode.PRODUCT_TOO_LARGE,
            "MCP tool response exceeds the response size limit even after compaction; "
            "retry with fewer views, bands, or observations.",
            retryable=False,
            details={
                "structured_content_bytes": len(structured_json.encode("utf-8")),
                "max_structured_content_bytes": MCP_MAX_RESPONSE_BYTES,
            },
        )
    return {
        "structuredContent": structured,
        "content": [{"type": "text", "text": _summary_for_payload(structured)}],
        "_meta": {
            "astrolens/schemaVersion": MCP_SCHEMA_VERSION,
            "astrolens/responseProfile": MCP_RESPONSE_PROFILE,
            "astrolens/structuredContentBytes": len(structured_json.encode("utf-8")),
            "astrolens/maxStructuredContentBytes": MCP_MAX_RESPONSE_BYTES,
        },
    }


def _strip_raw_metadata(value: Any) -> Any:
    """Drop bulky raw metadata blocks when a payload exceeds the size cap."""

    if isinstance(value, dict):
        return {
            key: _strip_raw_metadata(item)
            for key, item in value.items()
            if key != "raw_metadata"
        }
    if isinstance(value, list):
        return [_strip_raw_metadata(item) for item in value]
    return value


def _summary_for_payload(payload: dict[str, Any]) -> str:
    if "object" in payload and "views" in payload:
        obj = payload.get("object") or {}
        name = obj.get("name") or obj.get("id") or "the object"
        view_count = len(payload.get("views") or [])
        warning_count = len(payload.get("warnings") or [])
        images = _markdown_images_for_views(payload.get("views") or [])
        preview_text = f"\n\nPreview images:\n{images}" if images else ""
        return (
            f"Returned AstroLens evidence for {name}: "
            f"{view_count} view(s), {warning_count} warning(s).{preview_text}"
        )
    if "observations" in payload:
        observations = payload.get("observations") or []
        images = _markdown_images_for_observations(observations)
        preview_text = f"\n\nPreview images:\n{images}" if images else ""
        return f"Returned {len(observations)} AstroLens observation record(s).{preview_text}"
    if "views" in payload:
        return f"Returned {len(payload.get('views') or [])} ranked AstroLens view(s)."
    if "comparison" in payload:
        return f"Returned {len(payload.get('comparison') or [])} wavelength comparison row(s)."
    if "object_id" in payload or "coordinates" in payload:
        name = payload.get("name") or payload.get("object_id") or "the target"
        return f"Resolved astronomical target {name}."
    if "results" in payload:
        return f"Returned {len(payload.get('results') or [])} search result(s)."
    text = json.dumps(payload, separators=(",", ":"), default=str)
    return text[:800]


def _markdown_images_for_views(views: list[Any]) -> str:
    lines: list[str] = []
    for view in views[:4]:
        if not isinstance(view, dict):
            continue
        asset = view.get("asset") or {}
        url = asset.get("asset_url") or asset.get("thumbnail_url")
        if not url:
            continue
        line = _markdown_image(view.get("label"), url)
        if line:
            lines.append(line)
    return "\n".join(lines)


def _markdown_images_for_observations(observations: list[Any]) -> str:
    lines: list[str] = []
    for observation in observations[:4]:
        if not isinstance(observation, dict):
            continue
        url = observation.get("asset_url")
        if not url:
            continue
        line = _markdown_image(observation.get("label"), url)
        if line:
            lines.append(line)
    return "\n".join(lines)


def _markdown_image(label: Any, url: Any) -> str | None:
    """Build a markdown image where upstream labels/URLs cannot break the syntax."""

    safe_url = str(url)
    if not safe_url.startswith(("http://", "https://", "/")):
        return None
    safe_url = safe_url.replace("(", "%28").replace(")", "%29").replace(" ", "%20")
    safe_label = " ".join(str(label or "AstroLens preview").split())[:120]
    safe_label = safe_label.replace("[", "(").replace("]", ")")
    return f"![{safe_label}]({safe_url})"


def _absolutize_relative_asset_urls(value: Any, *, base_url: str) -> Any:
    if isinstance(value, dict):
        return {
            key: _absolute_url(item, base_url)
            if key in {"asset_url", "thumbnail_url"} and isinstance(item, str)
            else _absolutize_relative_asset_urls(item, base_url=base_url)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_absolutize_relative_asset_urls(item, base_url=base_url) for item in value]
    return value


def _absolute_url(value: str, base_url: str) -> str:
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if not value.startswith("/"):
        return value
    return f"{base_url.rstrip('/')}{value}"


@router.post("/mcp")
async def mcp_endpoint(request: Request) -> Response:
    try:
        payload = json.loads(await request.body())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Request body is not valid JSON."},
            }
        )
    if isinstance(payload, list):
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32600, "message": "Batch requests are not supported."},
            }
        )
    if (
        not isinstance(payload, dict)
        or payload.get("jsonrpc") != "2.0"
        or not isinstance(payload.get("method"), str)
    ):
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": payload.get("id") if isinstance(payload, dict) else None,
                "error": {
                    "code": -32600,
                    "message": "Request must be a JSON-RPC 2.0 object with a string method.",
                },
            }
        )
    if "id" not in payload:
        # JSON-RPC notifications must not receive a response body.
        return Response(status_code=202)
    return JSONResponse(await _handle_request(payload, request))


async def _handle_request(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    request_id = payload.get("id")
    method = payload.get("method")
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "astrolens", "version": __version__},
                "capabilities": {"tools": {}, "resources": {}},
            },
        }
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOL_DEFINITIONS}}
    if method == "resources/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"resources": [GALLERY_RESOURCE]}}
    if method == "resources/read":
        uri = str(payload.get("params", {}).get("uri", ""))
        if uri == GALLERY_RESOURCE["uri"]:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "contents": [
                        {
                            "uri": GALLERY_RESOURCE["uri"],
                            "mimeType": "text/html",
                            "text": GALLERY_HTML,
                            "_meta": GALLERY_RESOURCE_META,
                        }
                    ]
                },
            }
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32004, "message": f"Unknown resource: {uri}"},
        }
    if method == "tools/call":
        params = payload.get("params", {})
        try:
            tool_name = str(params["name"])
            result = await call_tool(tool_name, dict(params.get("arguments", {})))
            tool_result = _mcp_tool_result(result, base_url=str(request.base_url))
        except AstroLensError as exc:
            return _mcp_error_response(request_id, exc)
        except UnknownMcpToolError as exc:
            return _mcp_error_response(
                request_id,
                AstroLensError(
                    ErrorCode.VALIDATION_ERROR,
                    str(exc),
                    retryable=False,
                    details={"available_tools": [tool["name"] for tool in TOOL_DEFINITIONS]},
                ),
                json_rpc_code=-32602,
            )
        except (KeyError, TypeError, ValueError) as exc:
            return _mcp_error_response(
                request_id,
                AstroLensError(
                    ErrorCode.VALIDATION_ERROR,
                    _safe_invalid_params_message(exc),
                    retryable=False,
                    details={"error_type": type(exc).__name__},
                ),
                json_rpc_code=-32602,
            )
        except Exception as exc:  # pragma: no cover - defensive MCP boundary
            return _mcp_error_response(
                request_id,
                AstroLensError(
                    ErrorCode.INTERNAL_ERROR,
                    "AstroLens MCP tool call failed.",
                    retryable=False,
                    details={"error_type": type(exc).__name__},
                ),
                json_rpc_code=-32603,
            )
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": tool_result,
        }
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Unsupported method: {method}"},
    }


def _mcp_error_response(
    request_id: Any,
    exc: AstroLensError,
    *,
    json_rpc_code: int | None = None,
) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": json_rpc_code if json_rpc_code is not None else _json_rpc_code(exc.code),
            "message": exc.message,
            "data": compact_mcp_payload(
                {
                    "code": exc.code,
                    "retryable": exc.retryable,
                    "details": exc.details,
                    "schema_version": MCP_SCHEMA_VERSION,
                }
            ),
        },
    }


def _json_rpc_code(code: ErrorCode) -> int:
    if code in {
        ErrorCode.INVALID_COORDINATES,
        ErrorCode.VALIDATION_ERROR,
        ErrorCode.UNSUPPORTED_BAND,
        ErrorCode.OBJECT_AMBIGUOUS,
    }:
        return -32602
    if code == ErrorCode.OBJECT_NOT_FOUND:
        return -32004
    if code in {ErrorCode.SOURCE_UNAVAILABLE, ErrorCode.RATE_LIMITED}:
        return -32001
    if code == ErrorCode.SOURCE_TIMEOUT:
        return -32002
    if code in {ErrorCode.PRODUCT_NOT_PUBLIC, ErrorCode.RENDER_NOT_SUPPORTED}:
        return -32003
    return -32603


def _safe_invalid_params_message(exc: Exception) -> str:
    if isinstance(exc, KeyError):
        return "MCP tool call is missing a required parameter."
    message = str(exc)
    if not message:
        return "MCP tool call parameters are invalid."
    return message[:300]
