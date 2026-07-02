# AstroLens Evidence API

AstroLens is an agent-first, read-only astronomy evidence API. It returns
object identity, ranked telescope views, assets, citations, reuse metadata,
raw links, provenance, caveats, and source health metadata.

AstroLens does not generate lesson plans, scripts, social posts, creator packs,
teacher packs, or long-form educational content. Agents and downstream apps
can generate those from AstroLens evidence.

## Current V1 Status

This repository now implements a fixture-backed AstroLens V1 slice:

- FastAPI application skeleton
- typed Pydantic domain schemas
- typed error envelope
- `GET /v1/health`
- `GET /v1/sources/health`
- `GET /v1/resolve?q=...`
- `GET /v1/search?q=...`
- `GET /v1/evidence?q=...`
- `GET /v1/objects/{object_id}`
- `GET /v1/objects/{object_id}/evidence`
- `GET /v1/objects/{object_id}/views`
- `GET /v1/objects/{object_id}/observations`
- `GET /v1/assets/{asset_id}`
- `GET /v1/assets/{asset_id}/citations`
- `GET /v1/products/{product_id}/raw-links`
- `POST /v1/compare`
- `POST /v1/render`
- `POST /v1/render/fits-plan` (renders calibrated FITS from allowlisted archive hosts only)
- `GET /v1/rendered/{filename}`
- `GET /v1/jobs/{job_id}`
- `GET /v1/objects/{object_id}/facts` (compiled, cited SIMBAD measurements + derivations)
- JSON-RPC 2.0 `/mcp` endpoint with read-only tools (strict parse/batch/notification
  handling, enforced response byte cap, ambiguity surfaced instead of guessed)
- hero MCP tools: `show_object` (best cross-source multi-wavelength composite with
  credits and facts), `explain_object` (deterministic cited facts: distance, size,
  brightness, lookback time), `find_objects` (SIMBAD category/region search with
  server-side random sampling)
- cross-source composites: band recipes by object type mix MAST + SkyView FITS in
  one rendered image with per-channel provenance
- moving targets (Saturn, Jupiter, ...) route to MAST target-name search instead of
  a wrong-field cone search; SkyView is excluded with a teaching warning
- full-spectrum SkyView coverage including WISE (mid-IR), Planck (millimeter),
  and Fermi (gamma) surveys
- compact MCP response profile with bounded list inputs and structured source errors
- `ArchiveConnector` protocol and normalized connector candidates
- curated local seed evidence for 50 objects
- multi-wavelength golden evidence for major objects including M87, Crab Nebula, Cassiopeia A, and Sagittarius A*
- limited live CDS Sesame identity resolution
- limited live MAST HST/JWST public image observation and product ingestion
- optional live SkyView generated FITS cutouts rendered into AstroLens image assets
- OpenAPI schema registration for `EvidenceBundle` and error models

There are still no DB migrations, full FITS rendering pipeline, broad archive
fan-out, or content-generation endpoints. Live source adapters should replace
or augment the curated connector shells one source at a time.

Limited live ingestion is available for object identity resolution:

```text
GET /v1/resolve?q=M87&live=true
```

This calls the public CDS Sesame resolver, parses the SIMBAD-backed XML
response, and stores the result in an in-memory live cache for the running
process. The default resolver remains cache-first and curated:

```text
GET /v1/resolve?q=M87
```

Limited live evidence ingestion is also available for public MAST HST/JWST
image metadata and product manifests:

```text
GET /v1/evidence?q=M87&live=true&max_views=2
```

The live evidence path resolves the target with CDS Sesame, searches MAST CAOM
for public HST/JWST image observations in a small cone, fetches selected product
manifests, and returns an `EvidenceBundle` with preview URLs, raw product links,
citations, reuse guidance, and caveats. The MCP `get_object_evidence` tool uses
the same path when called with `{"object":"M87","live":true,"max_views":2}`.

Optional live SkyView evidence is available when the `skyview` extra is
installed. This path resolves the target with CDS Sesame, requests bounded
SkyView survey FITS cutouts, and renders those FITS files into AstroLens preview
assets:

```text
GET /v1/evidence?q=M87&live=true&sources=skyview&bands=visible,infrared,xray,radio&visual_mode=context
```

For MCP/ChatGPT, call `get_object_evidence` or `compare_wavelengths` with:

```json
{
  "object": "M87",
  "live": true,
  "sources": ["skyview"],
  "bands": ["visible", "infrared", "xray", "radio"],
  "visual_mode": "context"
}
```

Live visual requests support `visual_mode=detail|context|wide`. The mode selects
bounded radius and SkyView pixel presets; explicit `radius_deg` or `pixels`
values override the preset. `context` preserves the previous default behavior.

FITS render downloads are restricted to trusted archive hosts (`stsci.edu`,
`gsfc.nasa.gov`); extend with the `ASTROLENS_RENDER_URL_ALLOWLIST` environment
variable (comma-separated host suffixes).

SkyView images are generated survey cutouts, not official press images. The
default visible view uses SDSSg/r/i RGB compositing when available, with DSS
surveys available as fallback/custom inputs. The response includes source survey
names, raw FITS URLs, rendering provenance, citations, and reuse guidance.

## Install

```bash
uv sync
```

If `uv` is not installed locally, a normal virtual environment also works:

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

For live SkyView generated FITS cutouts, install the optional SkyView extra:

```bash
uv sync --extra skyview
```

Or with pip:

```bash
.venv/bin/pip install -e ".[skyview,dev]"
```

## Run

```bash
PYTHONPATH=src UV_CACHE_DIR=.uv-cache uv run uvicorn astrolens.api.main:app --reload
```

Local API:

```text
http://127.0.0.1:8000
```

Interactive docs:

```text
http://127.0.0.1:8000/docs
```

## Deploy (stable developer instance)

The repo ships a [render.yaml](render.yaml) blueprint. One-time setup: sign in
at render.com with GitHub, choose New + Blueprint, select this repository, and
deploy. Every push to `main` then auto-deploys to a stable
`https://<name>.onrender.com` URL; use `https://<name>.onrender.com/mcp` as
the MCP connector URL in ChatGPT (no authentication). The blueprint binds
Render's assigned port and sets `ASTROLENS_PUBLIC_BASE_URL` to the service's
own URL so rendered-image links and the gallery widget CSP use the deploy
domain. The Docker image includes the `skyview` extra, so live SkyView
rendering works in the container.

Notes: the blueprint uses the `starter` plan so the service stays warm (the
free plan sleeps after idle and cold-starts too slowly for MCP tool calls);
its 512 MB RAM comfortably covers SkyView cutout rendering, but very large
HST/JWST FITS composites may need a bigger instance.

The blueprint also mounts a persistent disk at the render cache directory so
rendered images survive deploys, and sets `ASTROLENS_WARM_CACHE=1`, which
starts a polite background warmer that walks the 50 curated objects on
startup so famous targets answer from warm caches.

## Test

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

Live integration tests are opt-in:

```bash
ASTROLENS_RUN_LIVE=1 UV_CACHE_DIR=.uv-cache uv run pytest tests/integration
```

## Product Boundary

AstroLens provides evidence infrastructure only:

- object resolution
- ranked telescope views
- assets/previews/raw links
- observations/products
- citations
- reuse metadata
- caveats
- provenance

It must remain read-only in V1.
