# MCP Server Design

## Purpose

The MCP server exposes AstroLens Evidence API to agents such as ChatGPT, Claude, and local development tools. It should provide small, read-only, evidence-focused tools.

AstroLens MCP must not generate lessons, scripts, creator packs, social posts, or long-form content. Agents can generate those downstream using the evidence returned by AstroLens.

## Principles

1. **Read-only V1**: no write tools.
2. **Small tool surface**: expose evidence retrieval primitives, not archive internals.
3. **Structured outputs**: avoid long prose; return IDs, assets, facts, citations, caveats, and source URLs.
4. **Token-conscious**: default outputs should be compact, with pagination/limits.
5. **Provenance-first**: outputs must include citations/source records for facts and assets.
6. **No arbitrary network fetch**: tools must only query AstroLens services and approved source connectors.

## Required tools

V1 tools:

- `search`
- `fetch`
- `resolve_object`
- `search_observations`
- `get_object_evidence`
- `get_best_views`
- `compare_wavelengths`
- `get_asset`
- `get_citations`
- `get_raw_links`

## Prohibited tools

Do not implement:

- `create_lesson`
- `create_teacher_pack`
- `create_creator_pack`
- `create_script`
- `create_social_post`
- `generate_narration`
- `write_article`
- arbitrary URL fetch
- arbitrary SQL/ADQL query from user input in V1
- shell/code execution

## Tool contracts

### search

Find objects, views, assets, or source records relevant to a query.

Input:

```json
{
  "query": "Crab Nebula X-ray visible comparison",
  "limit": 10
}
```

Output:

```json
{
  "results": [
    {
      "id": "object:astro:object:crab_nebula",
      "type": "celestial_object",
      "title": "Crab Nebula",
      "url": "https://astrolens.dev/o/crab-nebula",
      "snippet": "Supernova remnant with visible, infrared, X-ray, and radio evidence available."
    }
  ]
}
```

### fetch

Fetch a known object/view/asset/product by ID.

Input:

```json
{
  "id": "object:astro:object:crab_nebula"
}
```

Output: compact `EvidenceBundle` or relevant entity payload.

### resolve_object

Resolve a name or coordinate.

Input:

```json
{
  "query": "M87"
}
```

Output:

```json
{
  "object_id": "astro:object:m87",
  "name": "M87",
  "aliases": ["Messier 87", "NGC 4486", "Virgo A"],
  "coordinates": {"ra_deg": 187.70593, "dec_deg": 12.39112},
  "confidence": 0.99,
  "ambiguity": {"status": "resolved", "alternatives": []},
  "sources": []
}
```

### get_object_evidence

Return the main `EvidenceBundle`.

Input:

```json
{
  "object": "Crab Nebula",
  "bands": ["visible", "infrared", "xray", "radio"],
  "max_views": 6
}
```

### get_best_views

Return ranked views only.

Input:

```json
{
  "object": "M87",
  "bands": ["visible", "infrared", "xray", "radio"],
  "max_views": 6
}
```

### compare_wavelengths

Return a compact comparison across selected bands.

Input:

```json
{
  "object": "M87",
  "bands": ["visible", "xray", "radio"]
}
```

Output includes:

- resolved object
- selected views
- general interpretation per band
- assets
- citations
- caveats

### get_asset

Return asset metadata by ID.

### get_citations

Return citations for object/view/asset/product.

### get_raw_links

Return raw archive links for a view/product.

## Output size rules

- Default `search` limit: 10.
- Default `get_object_evidence` max views: 6.
- Include thumbnail URLs by default, not huge raw links unless requested.
- Include raw links as separate structured fields.
- Truncate long raw source metadata unless debug/admin mode.

## Error handling

MCP tools should map service errors to structured tool errors where possible:

- `OBJECT_NOT_FOUND`
- `OBJECT_AMBIGUOUS`
- `SOURCE_UNAVAILABLE`
- `SOURCE_TIMEOUT`
- `PRODUCT_NOT_PUBLIC`
- `RENDER_NOT_SUPPORTED`
- `RATE_LIMITED`
- `INVALID_COORDINATES`
- `UNSUPPORTED_BAND`

Do not return Python stack traces or raw connector errors to the agent.

## Security

MCP tools must:

- be read-only
- rate-limit by API key/client
- avoid arbitrary source URL fetching
- not expose secrets
- not expose internal-only IDs unless stable/public-safe
- not include credentials in source URLs
- use strict input schemas

## Tests

MCP tests must cover:

- schema validation
- each tool happy path
- object not found
- ambiguous object
- source outage warnings
- response size constraints
- citations present for facts/assets
- prohibited tools are absent

## Done criteria

An MCP change is done only when:

- tool schema tests pass
- agent eval prompts pass or are updated with justification
- no write/non-goal tools exist
- output remains compact and structured
- provenance/citations are present
