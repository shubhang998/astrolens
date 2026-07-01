"""Small JSON-RPC MCP-style endpoint for read-only AstroLens tools."""

import json
from typing import Any

from fastapi import APIRouter, Request

from astrolens import __version__
from astrolens.mcp.gallery_component import GALLERY_HTML, GALLERY_RESOURCE, GALLERY_RESOURCE_META
from astrolens.mcp.tools import TOOL_DEFINITIONS, call_tool

router = APIRouter(tags=["mcp"])


def _mcp_tool_result(payload: Any, *, base_url: str | None = None) -> dict[str, Any]:
    """Wrap service JSON in a ChatGPT-compatible MCP tool result."""

    structured = payload if isinstance(payload, dict) else {"result": payload}
    if base_url:
        structured = _absolutize_relative_asset_urls(structured, base_url=base_url)
    return {
        "structuredContent": structured,
        "content": [{"type": "text", "text": _summary_for_payload(structured)}],
    }


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
        label = str(view.get("label") or "AstroLens preview").replace("[", "(").replace("]", ")")
        lines.append(f"![{label}]({url})")
    return "\n".join(lines)


def _markdown_images_for_observations(observations: list[Any]) -> str:
    lines: list[str] = []
    for observation in observations[:4]:
        if not isinstance(observation, dict):
            continue
        url = observation.get("asset_url")
        if not url:
            continue
        label = str(observation.get("label") or "AstroLens preview")
        label = label.replace("[", "(").replace("]", ")")
        lines.append(f"![{label}]({url})")
    return "\n".join(lines)


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
async def mcp_endpoint(payload: dict[str, Any], request: Request) -> dict[str, Any]:
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
        result = await call_tool(str(params["name"]), dict(params.get("arguments", {})))
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": _mcp_tool_result(result, base_url=str(request.base_url)),
        }
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Unsupported method: {method}"},
    }
