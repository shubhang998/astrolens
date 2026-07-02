"""Small production-safety helpers for MCP tool inputs and outputs."""

from __future__ import annotations

from typing import Any

MCP_SCHEMA_VERSION = "astrolens.mcp.v1"
MCP_RESPONSE_PROFILE = "compact-v1"
MCP_MAX_RESPONSE_BYTES = 120_000

MCP_SEARCH_LIMIT = 10
MCP_OBSERVATION_LIMIT = 20
MCP_MAX_VIEWS = 6
MCP_MAX_COMPARE_VIEWS_PER_BAND = 3
MCP_MAX_FIND_RESULTS = 10
MCP_MAX_FIND_RADIUS_DEG = 15.0

RAW_METADATA_VALUE_MAX_CHARS = 300
RAW_METADATA_OMITTED_KEY_LIMIT = 20

RAW_METADATA_ALLOWLIST = frozenset(
    {
        "calib_level",
        "collection",
        "dataRights",
        "dataURI",
        "dataproduct_type",
        "dec_deg",
        "description",
        "distance",
        "em_max",
        "em_min",
        "filename",
        "filter",
        "filters",
        "instrument",
        "instrument_name",
        "obs_collection",
        "obs_id",
        "obsid",
        "productFilename",
        "productGroupDescription",
        "productSubGroupDescription",
        "project",
        "ra_deg",
        "s_dec",
        "s_ra",
        "skyview_query_url",
        "source_archive",
        "survey",
        "target_name",
        "wavelength_nm",
        "wave_region",
    }
)

LIST_LIMITS_BY_KEY = {
    "candidate_views": MCP_MAX_VIEWS,
    "caveats": 8,
    "citations": 8,
    "comparison": 12,
    "credits": 8,
    "fact_citations": 16,
    "facts": 4,
    "hits": MCP_MAX_FIND_RESULTS,
    "object_facts": 12,
    "observations": MCP_OBSERVATION_LIMIT,
    "panels": 4,
    "provenance": MCP_MAX_VIEWS,
    "raw_products": 4,
    "results": MCP_SEARCH_LIMIT,
    "source_products": 4,
    "suggested_followups": 4,
    "views": MCP_MAX_VIEWS,
    "warnings": 8,
}


def bounded_int(
    value: object,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    """Parse and clamp an MCP integer argument."""

    try:
        if value is None:
            parsed = default
        elif isinstance(value, int | float | str | bytes | bytearray):
            parsed = int(value)
        else:
            parsed = default
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def compact_mcp_payload(value: Any, *, key: str | None = None) -> Any:
    """Return a compact MCP-safe copy of a tool payload.

    Public API models keep preserving source `raw_metadata`. MCP outputs default
    to a compact profile because agent callers pay for every nested source field.
    """

    if isinstance(value, dict):
        if key == "raw_metadata":
            return compact_raw_metadata(value)
        return {
            str(item_key): compact_mcp_payload(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        limit = LIST_LIMITS_BY_KEY.get(key or "")
        items = value[:limit] if limit is not None else value
        return [compact_mcp_payload(item) for item in items]
    return value


def compact_raw_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Keep stable, useful source fields and omit bulky archive-specific extras."""

    compact: dict[str, Any] = {}
    omitted: list[str] = []
    for key, value in metadata.items():
        normalized_key = str(key)
        if normalized_key in RAW_METADATA_ALLOWLIST:
            compact[normalized_key] = _compact_raw_metadata_value(value)
        else:
            omitted.append(normalized_key)
    if omitted:
        compact["_omitted_keys"] = sorted(omitted)[:RAW_METADATA_OMITTED_KEY_LIMIT]
    return compact


def _compact_raw_metadata_value(value: Any) -> Any:
    if isinstance(value, str):
        return _truncate(value)
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, list):
        return [_compact_raw_metadata_value(item) for item in value[:5]]
    if isinstance(value, dict):
        return {
            str(key): _compact_raw_metadata_value(item)
            for key, item in list(value.items())[:8]
        }
    return _truncate(str(value))


def _truncate(value: str) -> str:
    if len(value) <= RAW_METADATA_VALUE_MAX_CHARS:
        return value
    return value[: RAW_METADATA_VALUE_MAX_CHARS - 3] + "..."
