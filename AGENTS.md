# AGENTS.md

## Project
AstroLens Evidence API is an agent-first, read-only astronomy retrieval API.
It returns object identity, ranked telescope views, assets, citations, reuse metadata, raw links, and provenance.
It does not generate lessons, scripts, creator packs, social posts, or long-form content.

## Read first
- docs/product-specs/astrolens-prd.md
- docs/design-docs/architecture.md when touching architecture
- docs/design-docs/source-connectors.md when touching connectors
- docs/design-docs/ranking.md when touching ranking
- docs/design-docs/mcp.md when touching MCP
- docs/design-docs/rendering.md when touching rendering

## Commands
- Install: `uv sync`
- Run API: `uv run uvicorn astrolens.api.main:app --reload`
- Test: `uv run pytest`
- Lint: `uv run ruff check .`
- Format: `uv run ruff format .`
- Typecheck: `uv run pyright`

## Hard rules
- V1 is read-only.
- No lesson, teacher-pack, creator-pack, script, or social-content endpoints.
- No live external archive calls in unit tests.
- Route handlers must not call external archives directly; use services/connectors.
- Every public scientific fact, asset, view, or raw link must carry provenance/citation metadata.
- Every asset must carry reuse/credit metadata or an explicit `reuse.status = "unknown"` warning.
- MCP tools must be read-only and evidence-focused.
- Do not add new production dependencies without explaining why.
- Do not fetch arbitrary user-provided URLs.
- Prefer typed Pydantic models at API boundaries.
- Prefer explicit domain models over unstructured dicts.

## Definition of done
A task is done only when:
- relevant tests are added or updated
- `uv run pytest` passes, or the reason it cannot run is documented
- `uv run ruff check .` passes
- `uv run pyright` passes
- OpenAPI schemas are updated if public API shape changes
- docs are updated if behavior changes
- no non-goal endpoint or write-capable MCP tool was introduced
