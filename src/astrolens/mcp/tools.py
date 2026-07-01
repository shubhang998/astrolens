"""Read-only MCP tool implementations backed by AstroLens services."""

from typing import Any

from astrolens.core.enums import BandFamily, VisualMode
from astrolens.mcp.gallery_component import GALLERY_URI
from astrolens.services.assets import asset_service
from astrolens.services.evidence import evidence_service
from astrolens.services.fits_renderer import (
    FitsRenderer,
    FitsRenderRequest,
    SourceFitsProduct,
)
from astrolens.services.live_ingestion import live_ingestion_service
from astrolens.services.live_sources import live_source_evidence_service
from astrolens.services.ranking import rank_views
from astrolens.services.repository import repository
from astrolens.services.resolver import resolver_service


def _bands(value: Any) -> list[BandFamily] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return [_band(item.strip()) for item in value.split(",") if item.strip()]
    return [_band(str(item)) for item in value]


def _band(value: str) -> BandFamily:
    normalized = value.strip().lower().replace("-", "_")
    aliases = {
        "ir": "infrared",
        "optical": "visible",
        "vis": "visible",
        "uv": "ultraviolet",
        "x_ray": "xray",
        "x-ray": "xray",
    }
    return BandFamily(aliases.get(normalized, normalized))


def _missions(value: Any) -> tuple[str, ...]:
    if value is None:
        return ("HST", "JWST")
    if isinstance(value, str):
        missions = [item.strip().upper() for item in value.split(",") if item.strip()]
    else:
        missions = [str(item).strip().upper() for item in value if str(item).strip()]
    return tuple(missions or ["HST", "JWST"])


def _sources(value: Any) -> tuple[str, ...]:
    if value is None:
        return ("mast",)
    if isinstance(value, str):
        sources = [item.strip().lower() for item in value.split(",") if item.strip()]
    else:
        sources = [str(item).strip().lower() for item in value if str(item).strip()]
    return tuple(sources or ["mast"])


def _visual_mode(value: Any) -> VisualMode:
    if value is None:
        return VisualMode.CONTEXT
    return VisualMode(str(value).strip().lower())


def _optional_float(arguments: dict[str, Any], key: str) -> float | None:
    value = arguments.get(key)
    return None if value is None else float(value)


def _optional_int(arguments: dict[str, Any], key: str) -> int | None:
    value = arguments.get(key)
    return None if value is None else int(value)


def _skyview_surveys(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        surveys = [item.strip() for item in value.split(",") if item.strip()]
    else:
        surveys = [str(item).strip() for item in value if str(item).strip()]
    return surveys or None


def _object_id(value: str) -> str:
    if value.startswith("object:"):
        return value.removeprefix("object:")
    return value


READ_ONLY_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
}


GALLERY_TOOL_META = {
    "ui": {"resourceUri": GALLERY_URI},
    "openai/outputTemplate": GALLERY_URI,
    "openai/widgetAccessible": True,
    "openai/toolInvocation/invoking": "Finding astronomy images...",
    "openai/toolInvocation/invoked": "AstroLens gallery ready",
}

fits_renderer = FitsRenderer()


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "search",
        "description": "Find curated AstroLens objects relevant to a query.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
        "annotations": READ_ONLY_ANNOTATIONS,
    },
    {
        "name": "fetch",
        "description": "Fetch compact evidence for a known AstroLens object ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
        "annotations": READ_ONLY_ANNOTATIONS,
    },
    {
        "name": "resolve_object",
        "description": (
            "Resolve an astronomical object name or alias. Use live=true for CDS Sesame."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "live": {"type": "boolean", "default": False},
            },
            "required": ["query"],
        },
        "annotations": READ_ONLY_ANNOTATIONS,
    },
    {
        "name": "search_observations",
        "description": (
            "Return observations for an object. Use live=true for live MAST rows, "
            "or sources=['skyview'] for generated multi-wavelength survey cutouts."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "bands": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "default": 20},
                "live": {"type": "boolean", "default": False},
                "visual_mode": {
                    "type": "string",
                    "enum": ["detail", "context", "wide"],
                    "default": "context",
                },
                "radius_deg": {
                    "type": "number",
                    "description": "Override the visual_mode radius preset.",
                },
                "rank_mode": {
                    "type": "string",
                    "enum": ["best_visual", "latest", "science_ready", "balanced"],
                    "default": "best_visual",
                },
                "missions": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["HST", "JWST"]},
                    "default": ["HST", "JWST"],
                },
                "sources": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["mast", "skyview"]},
                    "default": ["mast"],
                },
                "skyview_surveys": {"type": "array", "items": {"type": "string"}},
                "pixels": {
                    "type": "integer",
                    "minimum": 64,
                    "maximum": 2048,
                    "description": "Override the visual_mode SkyView pixel preset.",
                },
            },
            "required": ["object"],
        },
        "annotations": READ_ONLY_ANNOTATIONS,
        "_meta": GALLERY_TOOL_META,
    },
    {
        "name": "get_object_evidence",
        "description": (
            "Return an AstroLens EvidenceBundle. Use live=true for live source evidence; "
            "sources=['skyview'] returns rendered SkyView survey cutouts."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "bands": {"type": "array", "items": {"type": "string"}},
                "max_views": {"type": "integer", "default": 6},
                "live": {"type": "boolean", "default": False},
                "visual_mode": {
                    "type": "string",
                    "enum": ["detail", "context", "wide"],
                    "default": "context",
                },
                "radius_deg": {
                    "type": "number",
                    "description": "Override the visual_mode radius preset.",
                },
                "rank_mode": {
                    "type": "string",
                    "enum": ["best_visual", "latest", "science_ready", "balanced"],
                    "default": "best_visual",
                },
                "missions": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["HST", "JWST"]},
                    "default": ["HST", "JWST"],
                },
                "sources": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["mast", "skyview"]},
                    "default": ["mast"],
                },
                "skyview_surveys": {"type": "array", "items": {"type": "string"}},
                "pixels": {
                    "type": "integer",
                    "minimum": 64,
                    "maximum": 2048,
                    "description": "Override the visual_mode SkyView pixel preset.",
                },
            },
            "required": ["object"],
        },
        "annotations": READ_ONLY_ANNOTATIONS,
        "_meta": GALLERY_TOOL_META,
    },
    {
        "name": "get_best_views",
        "description": (
            "Return ranked AstroLens views. Use live=true for live MAST or SkyView views."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "bands": {"type": "array", "items": {"type": "string"}},
                "max_views": {"type": "integer", "default": 6},
                "live": {"type": "boolean", "default": False},
                "visual_mode": {
                    "type": "string",
                    "enum": ["detail", "context", "wide"],
                    "default": "context",
                },
                "radius_deg": {
                    "type": "number",
                    "description": "Override the visual_mode radius preset.",
                },
                "rank_mode": {
                    "type": "string",
                    "enum": ["best_visual", "latest", "science_ready", "balanced"],
                    "default": "best_visual",
                },
                "missions": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["HST", "JWST"]},
                    "default": ["HST", "JWST"],
                },
                "sources": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["mast", "skyview"]},
                    "default": ["mast"],
                },
                "skyview_surveys": {"type": "array", "items": {"type": "string"}},
                "pixels": {
                    "type": "integer",
                    "minimum": 64,
                    "maximum": 2048,
                    "description": "Override the visual_mode SkyView pixel preset.",
                },
            },
            "required": ["object"],
        },
        "annotations": READ_ONLY_ANNOTATIONS,
        "_meta": GALLERY_TOOL_META,
    },
    {
        "name": "compare_wavelengths",
        "description": (
            "Compare selected wavelength bands for an object. Use live=true and "
            "sources=['skyview'] for generated survey cutout comparisons."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "bands": {"type": "array", "items": {"type": "string"}},
                "max_views_per_band": {"type": "integer", "default": 1},
                "live": {"type": "boolean", "default": False},
                "visual_mode": {
                    "type": "string",
                    "enum": ["detail", "context", "wide"],
                    "default": "context",
                },
                "radius_deg": {
                    "type": "number",
                    "description": "Override the visual_mode radius preset.",
                },
                "rank_mode": {
                    "type": "string",
                    "enum": ["best_visual", "latest", "science_ready", "balanced"],
                    "default": "best_visual",
                },
                "missions": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["HST", "JWST"]},
                    "default": ["HST", "JWST"],
                },
                "sources": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["mast", "skyview"]},
                    "default": ["mast"],
                },
                "skyview_surveys": {"type": "array", "items": {"type": "string"}},
                "pixels": {
                    "type": "integer",
                    "minimum": 64,
                    "maximum": 2048,
                    "description": "Override the visual_mode SkyView pixel preset.",
                },
            },
            "required": ["object", "bands"],
        },
        "annotations": READ_ONLY_ANNOTATIONS,
        "_meta": GALLERY_TOOL_META,
    },
    {
        "name": "get_asset",
        "description": "Return asset metadata, reuse, and citations by asset ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"asset_id": {"type": "string"}},
            "required": ["asset_id"],
        },
        "annotations": READ_ONLY_ANNOTATIONS,
    },
    {
        "name": "get_citations",
        "description": "Return citations for an asset.",
        "inputSchema": {
            "type": "object",
            "properties": {"asset_id": {"type": "string"}},
            "required": ["asset_id"],
        },
        "annotations": READ_ONLY_ANNOTATIONS,
    },
    {
        "name": "get_raw_links",
        "description": "Return raw archive/source links for a product.",
        "inputSchema": {
            "type": "object",
            "properties": {"product_id": {"type": "string"}},
            "required": ["product_id"],
        },
        "annotations": READ_ONLY_ANNOTATIONS,
    },
    {
        "name": "make_best_visual",
        "description": (
            "Return the highest-trust/highest-legibility visual for an object, including "
            "target validation, provenance, and a calibrated FITS render plan when possible."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "bands": {"type": "array", "items": {"type": "string"}},
                "live": {"type": "boolean", "default": True},
                "visual_mode": {
                    "type": "string",
                    "enum": ["detail", "context", "wide"],
                    "default": "context",
                },
                "radius_deg": {
                    "type": "number",
                    "description": "Override the visual_mode radius preset.",
                },
                "rank_mode": {
                    "type": "string",
                    "enum": ["best_visual", "latest", "science_ready", "balanced"],
                    "default": "best_visual",
                },
                "missions": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["HST", "JWST"]},
                    "default": ["HST", "JWST"],
                },
                "sources": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["mast", "skyview"]},
                    "default": ["mast"],
                },
                "skyview_surveys": {"type": "array", "items": {"type": "string"}},
                "pixels": {
                    "type": "integer",
                    "minimum": 64,
                    "maximum": 2048,
                    "description": "Override the visual_mode SkyView pixel preset.",
                },
            },
            "required": ["object"],
        },
        "annotations": READ_ONLY_ANNOTATIONS,
        "_meta": GALLERY_TOOL_META,
    },
    {
        "name": "render_fits_composite",
        "description": (
            "Plan a calibrated FITS composite for an object from eligible public source "
            "products. Returns unsupported with exact reasons until optional render "
            "dependencies are installed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "bands": {"type": "array", "items": {"type": "string"}},
                "live": {"type": "boolean", "default": True},
                "visual_mode": {
                    "type": "string",
                    "enum": ["detail", "context", "wide"],
                    "default": "context",
                },
                "radius_deg": {
                    "type": "number",
                    "description": "Override the visual_mode radius preset.",
                },
                "missions": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["HST", "JWST"]},
                    "default": ["HST", "JWST"],
                },
                "sources": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["mast", "skyview"]},
                    "default": ["mast"],
                },
                "skyview_surveys": {"type": "array", "items": {"type": "string"}},
                "pixels": {
                    "type": "integer",
                    "minimum": 64,
                    "maximum": 2048,
                    "description": "Override the visual_mode SkyView pixel preset.",
                },
                "size": {
                    "type": "string",
                    "enum": ["thumbnail", "standard", "square"],
                    "default": "standard",
                },
                "stretch": {
                    "type": "string",
                    "enum": ["asinh", "linear", "log", "sqrt"],
                    "default": "asinh",
                },
            },
            "required": ["object"],
        },
        "annotations": READ_ONLY_ANNOTATIONS,
    },
    {
        "name": "get_visual_provenance",
        "description": (
            "Return provenance, image tier, selection reason, and target-validation cards "
            "for the best visual assets for an object."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "max_views": {"type": "integer", "default": 6},
                "live": {"type": "boolean", "default": True},
                "visual_mode": {
                    "type": "string",
                    "enum": ["detail", "context", "wide"],
                    "default": "context",
                },
                "radius_deg": {
                    "type": "number",
                    "description": "Override the visual_mode radius preset.",
                },
                "missions": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["HST", "JWST"]},
                    "default": ["HST", "JWST"],
                },
                "sources": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["mast", "skyview"]},
                    "default": ["mast"],
                },
                "skyview_surveys": {"type": "array", "items": {"type": "string"}},
                "pixels": {
                    "type": "integer",
                    "minimum": 64,
                    "maximum": 2048,
                    "description": "Override the visual_mode SkyView pixel preset.",
                },
            },
            "required": ["object"],
        },
        "annotations": READ_ONLY_ANNOTATIONS,
    },
]


async def call_tool(name: str, arguments: dict[str, Any]) -> Any:
    """Dispatch an MCP tool call."""

    if name == "search":
        limit = int(arguments.get("limit", 10))
        results = repository.find_objects(str(arguments["query"]), limit=limit)
        return {
            "results": [
                {
                    "id": f"object:{obj.id}",
                    "type": "celestial_object",
                    "title": obj.name,
                    "url": f"/v1/objects/{obj.id}",
                    "snippet": f"{obj.name} is curated as a {obj.type}.",
                }
                for obj in results
            ]
        }
    if name == "fetch":
        object_id = _object_id(str(arguments["id"]))
        return evidence_service.bundle_for_object(object_id).model_dump(mode="json")
    if name == "resolve_object":
        if bool(arguments.get("live", False)):
            return (
                await live_ingestion_service.resolve_live(str(arguments["query"]))
            ).model_dump(mode="json")
        return resolver_service.resolve(str(arguments["query"])).model_dump(mode="json")
    if name == "search_observations":
        if bool(arguments.get("live", False)):
            bundle = await live_source_evidence_service.bundle_for_query(
                str(arguments["object"]),
                bands=_bands(arguments.get("bands")),
                max_views=int(arguments.get("limit", 20)),
                visual_mode=_visual_mode(arguments.get("visual_mode")),
                radius_deg=_optional_float(arguments, "radius_deg"),
                missions=_missions(arguments.get("missions")),
                rank_mode=str(arguments.get("rank_mode", "best_visual")),
                sources=_sources(arguments.get("sources")),
                skyview_surveys=_skyview_surveys(arguments.get("skyview_surveys")),
                pixels=_optional_int(arguments, "pixels"),
            )
            return {
                "object": bundle.object.model_dump(mode="json"),
                "object_id": bundle.object.id,
                "observations": [_live_observation_row(view) for view in bundle.views],
                "warnings": [warning.model_dump(mode="json") for warning in bundle.warnings],
                "meta": bundle.meta.model_dump(mode="json"),
            }
        resolved = resolver_service.resolve(str(arguments["object"]))
        object_id = resolved.object_id or resolved.ambiguity.alternatives[0].id
        observations = repository.observations_for_object(
            object_id,
            _bands(arguments.get("bands")),
        )[: int(arguments.get("limit", 20))]
        return {
            "object_id": object_id,
            "observations": [obs.model_dump(mode="json") for obs in observations],
        }
    if name == "get_object_evidence":
        if bool(arguments.get("live", False)):
            return (
                await live_source_evidence_service.bundle_for_query(
                    str(arguments["object"]),
                    bands=_bands(arguments.get("bands")),
                    max_views=int(arguments.get("max_views", 6)),
                    visual_mode=_visual_mode(arguments.get("visual_mode")),
                    radius_deg=_optional_float(arguments, "radius_deg"),
                    missions=_missions(arguments.get("missions")),
                    rank_mode=str(arguments.get("rank_mode", "best_visual")),
                    sources=_sources(arguments.get("sources")),
                    skyview_surveys=_skyview_surveys(arguments.get("skyview_surveys")),
                    pixels=_optional_int(arguments, "pixels"),
                )
            ).model_dump(mode="json")
        return evidence_service.bundle_for_query(
            str(arguments["object"]),
            bands=_bands(arguments.get("bands")),
            max_views=int(arguments.get("max_views", 6)),
        ).model_dump(mode="json")
    if name == "get_best_views":
        if bool(arguments.get("live", False)):
            bundle = await live_source_evidence_service.bundle_for_query(
                str(arguments["object"]),
                bands=_bands(arguments.get("bands")),
                max_views=int(arguments.get("max_views", 6)),
                visual_mode=_visual_mode(arguments.get("visual_mode")),
                radius_deg=_optional_float(arguments, "radius_deg"),
                missions=_missions(arguments.get("missions")),
                rank_mode=str(arguments.get("rank_mode", "best_visual")),
                sources=_sources(arguments.get("sources")),
                skyview_surveys=_skyview_surveys(arguments.get("skyview_surveys")),
                pixels=_optional_int(arguments, "pixels"),
            )
            return {
                "object_id": bundle.object.id,
                "views": [view.model_dump(mode="json") for view in bundle.views],
                "warnings": [warning.model_dump(mode="json") for warning in bundle.warnings],
                "meta": bundle.meta.model_dump(mode="json"),
            }
        resolved = resolver_service.resolve(str(arguments["object"]))
        object_id = resolved.object_id or resolved.ambiguity.alternatives[0].id
        bands = _bands(arguments.get("bands"))
        views = rank_views(
            repository.views_for_object(object_id, bands),
            bands=bands,
            max_views=int(arguments.get("max_views", 6)),
        )
        return {"object_id": object_id, "views": [view.model_dump(mode="json") for view in views]}
    if name == "compare_wavelengths":
        if bool(arguments.get("live", False)):
            return await _compare_live_wavelengths(arguments)
        return evidence_service.compare(
            str(arguments["object"]),
            bands=_bands(arguments.get("bands")) or [],
            max_views_per_band=int(arguments.get("max_views_per_band", 1)),
        ).model_dump(mode="json")
    if name == "get_asset":
        return asset_service.get_asset(str(arguments["asset_id"])).model_dump(mode="json")
    if name == "get_citations":
        return asset_service.get_asset_citations(str(arguments["asset_id"])).model_dump(mode="json")
    if name == "get_raw_links":
        return asset_service.get_product_raw_links(str(arguments["product_id"])).model_dump(
            mode="json"
        )
    if name == "make_best_visual":
        bundle = await _bundle_for_visual_tool(arguments, max_views=8)
        best_view = bundle.views[0] if bundle.views else None
        render_plan = _fits_render_plan_for_views(
            bundle.views,
            object_id=bundle.object.id,
            size="standard",
            stretch="asinh",
        )
        rendered_view = _rendered_view_for_plan(
            best_view,
            render_plan,
            object_name=bundle.object.name,
        )
        views = (
            [rendered_view, *[view.model_dump(mode="json") for view in bundle.views[:3]]]
            if rendered_view
            else [view.model_dump(mode="json") for view in bundle.views[:1]]
        )
        return {
            "object": bundle.object.model_dump(mode="json"),
            "views": views,
            "best_view": rendered_view
            or (best_view.model_dump(mode="json") if best_view else None),
            "render_plan": render_plan,
            "visual_ladder": _visual_ladder(),
            "warnings": [warning.model_dump(mode="json") for warning in bundle.warnings],
            "meta": bundle.meta.model_dump(mode="json"),
        }
    if name == "render_fits_composite":
        bundle = await _bundle_for_visual_tool(arguments, max_views=8)
        return {
            "object": bundle.object.model_dump(mode="json"),
            "render_plan": _fits_render_plan_for_views(
                bundle.views,
                object_id=bundle.object.id,
                size=str(arguments.get("size", "standard")),
                stretch=str(arguments.get("stretch", "asinh")),
            ),
            "candidate_views": [view.model_dump(mode="json") for view in bundle.views],
            "warnings": [warning.model_dump(mode="json") for warning in bundle.warnings],
            "meta": bundle.meta.model_dump(mode="json"),
        }
    if name == "get_visual_provenance":
        bundle = await _bundle_for_visual_tool(
            arguments,
            max_views=int(arguments.get("max_views", 6)),
        )
        return {
            "object": bundle.object.model_dump(mode="json"),
            "provenance": [_visual_provenance_card(view) for view in bundle.views],
            "visual_ladder": _visual_ladder(),
            "warnings": [warning.model_dump(mode="json") for warning in bundle.warnings],
            "meta": bundle.meta.model_dump(mode="json"),
        }
    raise ValueError(f"Unknown AstroLens MCP tool: {name}")


def _live_observation_row(view: Any) -> dict[str, Any]:
    asset_url = view.asset.asset_url if view.asset else None
    return {
        "view_id": view.id,
        "label": view.label,
        "band_family": view.band_family,
        "source_archive": view.source_archive,
        "facility": view.facility,
        "instrument": view.instrument,
        "asset_url": asset_url,
        "asset": view.asset.model_dump(mode="json") if view.asset else None,
        "visual_tier": view.asset.visual_tier if view.asset else None,
        "target_validation": (
            view.asset.target_validation.model_dump(mode="json")
            if view.asset and view.asset.target_validation
            else None
        ),
        "provenance": (
            view.asset.provenance.model_dump(mode="json")
            if view.asset and view.asset.provenance
            else None
        ),
        "citation_ids": [citation.id for citation in view.citations],
        "caveats": view.caveats,
        "facts": [fact.model_dump(mode="json") for fact in view.facts],
        "raw_products": [product.model_dump(mode="json") for product in view.raw_products],
    }


async def _compare_live_wavelengths(arguments: dict[str, Any]) -> dict[str, Any]:
    bands = _bands(arguments.get("bands")) or []
    max_views_per_band = int(arguments.get("max_views_per_band", 1))
    bundle = await live_source_evidence_service.bundle_for_query(
        str(arguments["object"]),
        bands=bands or None,
        max_views=max(1, len(bands) * max_views_per_band),
        visual_mode=_visual_mode(arguments.get("visual_mode")),
        radius_deg=_optional_float(arguments, "radius_deg"),
        missions=_missions(arguments.get("missions")),
        rank_mode=str(arguments.get("rank_mode", "best_visual")),
        sources=_sources(arguments.get("sources")),
        skyview_surveys=_skyview_surveys(arguments.get("skyview_surveys")),
        pixels=_optional_int(arguments, "pixels"),
    )
    comparison: list[dict[str, Any]] = []
    for band in bands:
        views = [view for view in bundle.views if view.band_family == band]
        if not views:
            comparison.append(
                {
                    "band_family": str(band),
                    "general_interpretation": (
                        "No live MAST HST/JWST image view was returned for this band "
                        "in the limited live ingestion cone."
                    ),
                    "caveats": [
                        (
                            "The current live connector only covers public MAST HST/JWST "
                            "image metadata."
                        ),
                    ],
                }
            )
            continue
        for view in views[:max_views_per_band]:
            comparison.append(
                {
                    "band_family": view.band_family,
                    "view_id": view.id,
                    "facility": view.facility,
                    "asset_id": view.asset.id if view.asset else None,
                    "asset_url": view.asset.asset_url if view.asset else None,
                    "general_interpretation": view.facts[0].claim if view.facts else view.label,
                    "citations": [citation.model_dump(mode="json") for citation in view.citations],
                    "caveats": view.caveats,
                }
            )
    return {
        "object": bundle.object.model_dump(mode="json"),
        "views": [view.model_dump(mode="json") for view in bundle.views],
        "comparison": comparison,
        "warnings": [warning.model_dump(mode="json") for warning in bundle.warnings],
        "meta": bundle.meta.model_dump(mode="json"),
    }


async def _bundle_for_visual_tool(
    arguments: dict[str, Any],
    *,
    max_views: int,
) -> Any:
    if bool(arguments.get("live", True)):
        return await live_source_evidence_service.bundle_for_query(
            str(arguments["object"]),
            bands=_bands(arguments.get("bands")),
            max_views=max_views,
            visual_mode=_visual_mode(arguments.get("visual_mode")),
            radius_deg=_optional_float(arguments, "radius_deg"),
            missions=_missions(arguments.get("missions")),
            rank_mode=str(arguments.get("rank_mode", "best_visual")),
            sources=_sources(arguments.get("sources")),
            skyview_surveys=_skyview_surveys(arguments.get("skyview_surveys")),
            pixels=_optional_int(arguments, "pixels"),
        )
    return evidence_service.bundle_for_query(
        str(arguments["object"]),
        bands=_bands(arguments.get("bands")),
        max_views=max_views,
    )


def _fits_render_plan_for_views(
    views: list[Any],
    *,
    object_id: str,
    size: str,
    stretch: str,
) -> dict[str, Any]:
    products = [
        SourceFitsProduct.from_data_product(product)
        for view in views
        for product in view.raw_products
    ]
    if not products:
        return {
            "status": "unsupported",
            "error": "No source products were available for FITS render planning.",
        }
    request = FitsRenderRequest(
        object_id=object_id,
        products=products,
        size=size,  # type: ignore[arg-type]
        stretch=stretch,  # type: ignore[arg-type]
    )
    return fits_renderer.render(request).model_dump(mode="json")


def _visual_provenance_card(view: Any) -> dict[str, Any]:
    asset = view.asset
    return {
        "view_id": view.id,
        "label": view.label,
        "visual_tier": asset.visual_tier if asset else None,
        "selection_reason": asset.selection_reason if asset else None,
        "target_validation": (
            asset.target_validation.model_dump(mode="json")
            if asset and asset.target_validation
            else None
        ),
        "provenance": (
            asset.provenance.model_dump(mode="json")
            if asset and asset.provenance
            else None
        ),
        "source_products": [product.model_dump(mode="json") for product in view.raw_products],
        "caveats": view.caveats,
    }


def _rendered_view_for_plan(
    source_view: Any,
    render_plan: dict[str, Any],
    *,
    object_name: str,
) -> dict[str, Any] | None:
    if (
        not source_view
        or render_plan.get("status") != "complete"
        or not render_plan.get("asset_url")
    ):
        return None
    recipe = render_plan.get("recipe") or {}
    source_products = recipe.get("source_products") or []
    source_asset = source_view.asset
    target_validation = (
        source_asset.target_validation.model_dump(mode="json")
        if source_asset and source_asset.target_validation
        else None
    )
    return {
        "id": f"view:{recipe.get('asset_id') or render_plan.get('asset_id')}",
        "label": f"{object_name} AstroLens FITS render",
        "band_family": "multiwavelength" if recipe.get("false_color") else source_view.band_family,
        "facility": "AstroLens render",
        "instrument": "calibrated FITS composite",
        "source_archive": "AstroLens",
        "asset": {
            "id": render_plan.get("asset_id"),
            "source_product_ids": [product.get("id") for product in source_products],
            "format": recipe.get("output_format", "png"),
            "visual_tier": "astrolens_rendered",
            "asset_url": render_plan.get("asset_url"),
            "thumbnail_url": render_plan.get("asset_url"),
            "false_color": recipe.get("false_color"),
            "processing_note": (
                "AstroLens-rendered image from calibrated public FITS products using "
                f"{recipe.get('stretch', 'asinh')} stretch."
            ),
            "selection_reason": "Rendered from calibrated FITS products after archive ranking.",
            "target_validation": target_validation,
            "provenance": {
                "visual_tier": "astrolens_rendered",
                "source_archive": "AstroLens",
                "facility": "AstroLens render",
                "instrument": "calibrated FITS composite",
                "source_record_id": render_plan.get("cache_key"),
                "render_recipe_id": recipe.get("cache_key"),
                "notes": recipe.get("caveats", []),
            },
            "credit_text": source_asset.credit_text if source_asset else None,
            "reuse_policy_id": (
                source_asset.reuse_policy_id if source_asset else "reuse:mast:live:public"
            ),
            "citations": [citation.model_dump(mode="json") for citation in source_view.citations],
        },
        "raw_products": source_products,
        "facts": [fact.model_dump(mode="json") for fact in source_view.facts],
        "reuse": source_view.reuse.model_dump(mode="json"),
        "citations": [citation.model_dump(mode="json") for citation in source_view.citations],
        "caveats": recipe.get("caveats", []),
        "scores": source_view.scores.model_dump(mode="json") if source_view.scores else None,
    }


def _visual_ladder() -> list[dict[str, str]]:
    return [
        {"tier": "outreach_release", "meaning": "Public release/outreach image when available."},
        {
            "tier": "astrolens_rendered",
            "meaning": "AstroLens-generated rendering from calibrated FITS.",
        },
        {"tier": "processed_archive", "meaning": "HLA/HLSP/HAP or calibrated archive product."},
        {"tier": "raw_archive_preview", "meaning": "Convenience preview; use only as fallback."},
    ]
