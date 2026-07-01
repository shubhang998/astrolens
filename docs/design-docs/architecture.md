# AstroLens Architecture Design

## Purpose

This document defines the implementation architecture for AstroLens Evidence API. AstroLens is a read-only, agent-first astronomy retrieval service. It returns object identity, ranked telescope views, assets, citations, reuse metadata, raw links, provenance, facts, caveats, and source-health warnings.

It does **not** generate lessons, scripts, creator packs, social posts, or long-form educational content. Agents and downstream apps do that using AstroLens evidence.

## Design principles

1. **Cache-first hot path**: normal agent requests must use local normalized data whenever possible. Do not fan out to several public astronomy archives during a user-facing request.
2. **Read-only V1**: no write-capable public endpoints and no write-capable MCP tools.
3. **Evidence over prose**: return facts, citations, assets, and caveats. Do not return long generated explanations as core API behavior.
4. **Provenance everywhere**: every object, view, asset, raw link, and scientific fact must include source/citation metadata or an explicit warning.
5. **Source isolation**: route handlers call services; services call connectors; connectors call external archives. No direct source calls from routes.
6. **Graceful degradation**: source outages should produce warnings and cached/stale results, not total failures when useful cached data exists.
7. **Schema stability**: API and MCP outputs are contracts for agents. Prefer additive changes and version breaking changes.

## System overview

```text
Agent / App / SDK
  -> REST API or MCP Server
  -> API route layer
  -> service layer
  -> normalized DB/cache/search index
  -> response with evidence, citations, caveats, and warnings
```

Cold path:

```text
scheduled/on-demand ingestion job
  -> source connector
  -> source cache
  -> normalization
  -> ranking inputs
  -> DB/index/assets/citations
```

## Recommended stack

- Python 3.12+
- FastAPI
- Pydantic v2
- SQLAlchemy 2.x
- Alembic
- Postgres + PostGIS
- Redis
- RQ or Celery for jobs
- httpx for async HTTP
- tenacity for retries
- structlog for structured logs
- OpenTelemetry for tracing
- pytest + respx for tests
- ruff + pyright
- Docker Compose for local development

Astronomy packages:

- astropy
- astroquery where useful
- pyvo where useful
- reproject when rendering/alignment is needed later
- Pillow/imageio for simple image work

## Services

### Resolver service

Responsibilities:

- Resolve user query to canonical `CelestialObject`.
- Normalize aliases and coordinates.
- Surface ambiguity rather than silently choosing low-confidence matches.
- Prefer cached local identity records; refresh through SIMBAD/NED connectors when needed.

### Evidence service

Responsibilities:

- Build `EvidenceBundle` from object identity, ranked views, assets, facts, citations, reuse policies, raw links, and warnings.
- Keep responses compact and agent-friendly.
- Never invent missing views or facts.

### Ranking service

Responsibilities:

- Score candidate views and products.
- Prefer agent usefulness over visual beauty alone.
- Return debug scoring only when requested.

### Asset service

Responsibilities:

- Resolve asset metadata.
- Prefer existing preview/public assets.
- Queue rendering jobs only when supported and necessary.
- Always attach reuse and credit metadata.

### Citation service

Responsibilities:

- Normalize citation records from archives and ADS.
- Return source URLs, retrieval time, credit text, and policy links when available.

### Cache service

Responsibilities:

- Local source-cache management.
- Stale-while-revalidate behavior.
- Source-health warnings.

## API route rules

Routes must:

- Validate inputs with Pydantic.
- Call services only, not connectors directly.
- Return typed response models.
- Use the common `APIError` response shape.
- Include `request_id` in response metadata and logs.

Routes must not:

- Fetch arbitrary user-provided URLs.
- Call shell commands.
- Call live archives directly.
- Return scientific facts without provenance/citations.

## Hot path performance targets

- `GET /v1/resolve` cached: P95 < 500 ms
- `GET /v1/evidence` cached: P95 < 1200 ms
- `GET /v1/objects/{id}/views` cached: P95 < 900 ms
- `POST /v1/compare` cached: P95 < 1500 ms
- MCP `search`: P95 < 1000 ms
- MCP `fetch`: P95 < 1500 ms

## Source outage behavior

If an archive is unavailable:

- Serve cached data if available.
- Mark cache as stale if applicable.
- Add a structured warning.
- Do not fail the whole response unless there is no useful cached result.

Example warning:

```json
{
  "code": "SOURCE_UNAVAILABLE",
  "source": "MAST",
  "message": "Returned cached data because live refresh failed.",
  "stale": true,
  "retryable": true
}
```

## Repository boundaries

```text
api/          HTTP route layer only
mcp/          MCP server and tool schemas
services/     business logic and orchestration
connectors/   external source adapters only
core/         domain models, enums, errors, provenance, scoring primitives
db/           persistence models, migrations, sessions
rendering/    optional FITS/image rendering logic
workers/      ingestion, refresh, render jobs
```

## Definition of done for architecture changes

- Public schemas remain stable or versioned.
- Tests cover changed behavior.
- Source failures are handled explicitly.
- New service boundaries are documented.
- No route directly calls a connector.
- No write-capable MCP/API behavior is introduced.
