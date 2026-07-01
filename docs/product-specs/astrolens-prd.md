# AstroLens Evidence API — Product Requirements Document

**Status:** Draft v1.1  
**Product:** AstroLens Evidence API  
**Primary interface:** REST API + MCP server  
**Primary customer:** AI agents and developers building astronomy exploration, education, research-assist, and media tools  
**Core principle:** AstroLens provides evidence infrastructure. It does not generate lessons, scripts, social posts, or long-form content.

---

## 1. Executive Summary

AstroLens is an agent-first, read-only astronomy evidence API. It helps AI agents and applications retrieve reliable public telescope data across fragmented astronomy archives without needing to understand archive-specific APIs, astronomical object aliases, FITS files, coordinate systems, data rights, or citation formats.

Given an object name, coordinate, or astronomy query, AstroLens returns a structured `EvidenceBundle` containing:

- resolved astronomical object identity
- aliases and coordinates
- ranked public telescope views
- image/preview assets where available
- raw archive links
- observation/product metadata
- telescope/instrument/wavelength metadata
- source-grounded facts
- citations and credit text
- reuse policy metadata
- confidence scores and caveats
- source health/cache metadata

The API exists so agents like ChatGPT, Claude, Perplexity, Cursor, or custom AI apps can safely produce user-facing explanations, classroom material, scripts, summaries, comparisons, or interfaces using real telescope evidence.

AstroLens itself should not generate those downstream outputs in V1.

---

## 2. Problem

Astronomy data is publicly available in many archives, but it is hard for non-specialists and AI agents to use reliably.

A user or agent may ask:

> “Show me the Crab Nebula in visible, infrared, X-ray, and radio, and cite the sources.”

To answer this well, a system may need to resolve object names, search several archives, compare wavelength regimes, find usable image previews, distinguish raw and processed products, identify provenance, handle rights/credit requirements, and explain caveats like false color or non-simultaneous observations.

Today, that requires knowledge of systems such as SIMBAD, NED, MAST, IRSA, HEASARC, Chandra, SkyView, ADS, and Virtual Observatory standards. Existing tools are powerful for astronomers but not optimized for agent reliability, public-use assets, or one-call evidence retrieval.

---

## 3. Product Thesis

The winning product is not a generic wrapper around every astronomy archive.

The winning product is a fast, cached, citation-rich evidence layer that answers:

> “What is the best real telescope evidence for this object or query, and how can an agent safely use it?”

AstroLens should optimize for:

- correctness of object resolution
- useful ranked views, not exhaustive archive dumps
- structured provenance
- stable schemas for agents
- fast cached responses
- conservative rights/reuse metadata
- clear caveats
- graceful degradation when source archives are slow or unavailable

---

## 4. Goals

### 4.1 V1 Product Goals

AstroLens V1 must provide:

1. Object resolution for common astronomical names, aliases, and coordinates.
2. A canonical `EvidenceBundle` for an object/query.
3. Ranked telescope views across major wavelength families.
4. Public asset metadata, thumbnails/previews, and raw links where available.
5. Citations, credit text, and reuse-policy metadata for every returned asset or fact.
6. Read-only MCP tools for agents.
7. Fast cache-first response behavior.
8. Source health and stale-cache warnings.
9. Golden-object coverage for an initial curated set of famous objects.
10. Extensible connector architecture for adding more archives over time.

### 4.2 Business/Product Goals

AstroLens should become infrastructure for:

- AI agents answering astronomy questions
- education platforms
- public science apps
- museum/planetarium tools
- creator/research-assist workflows
- developer experiments using public telescope data

AstroLens should be valuable because it provides retrieval, normalization, ranking, citations, and provenance — not because it owns the underlying public data.

---

## 5. Non-Goals

V1 must not include:

- lesson-plan generation
- teacher packs
- creator packs
- YouTube script generation
- social-media post generation
- long-form educational writing
- user-facing curriculum workflows
- a full consumer web app
- full professional astronomy analysis
- arbitrary FITS workbench functionality
- full support for every archive and data product
- write-capable MCP tools
- arbitrary user-provided URL fetching
- claims of novel scientific discovery

Downstream agents and apps can use AstroLens evidence to generate lessons, scripts, summaries, classroom material, or creator assets themselves.

---

## 6. Target Users

### 6.1 Primary Users

#### AI Agents

Agents need structured tools that can return reliable, cited telescope evidence without requiring the agent to manually reason through archive-specific APIs.

Examples:

- ChatGPT agent answering astronomy questions
- Claude Desktop using an MCP server
- AI tutor explaining space objects
- research-assist agent gathering source evidence
- developer agent building a space-exploration UI

#### Developers

Developers need a simple REST API and SDKs that abstract away astronomy archive complexity.

Examples:

- edtech app developer
- museum exhibit developer
- science media tool developer
- astronomy hobby app developer

### 6.2 Secondary Users

- teachers, indirectly through AI tools
- students, indirectly through apps or agents
- YouTubers/science communicators, indirectly through agents/apps
- amateur astronomers
- citizen-science builders

---

## 7. Product Boundary

AstroLens provides evidence.

Agents provide narration, pedagogy, tone, adaptation, and downstream content.

| Layer | Responsibility |
|---|---|
| AstroLens | Retrieve, normalize, rank, cite, cache, expose provenance, return assets/raw links/facts/caveats. |
| Agent | Explain, summarize, teach, write, adapt to audience, compose scripts or lessons. |
| App/UI | User experience, publishing, classroom workflows, creator workflows, accounts, payments. |

This boundary should be enforced in API design. Do not add endpoints that generate lessons, scripts, or creator packages.

---

## 8. V1 Scope

### 8.1 Must Have

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
- `POST /v1/render` with async behavior for non-cached renders
- `GET /v1/jobs/{job_id}`
- MCP server with read-only tools
- local cache/index
- source health reporting
- golden-object test set

### 8.2 Should Have

- simple Python SDK
- simple TypeScript SDK
- OpenAPI 3.1 spec
- fixture-based connector tests
- source-specific rate limits and timeouts
- stale-while-revalidate behavior
- asset thumbnail cache
- debug scoring mode for internal ranking evaluation

### 8.3 Later

- deeper spectra support
- light curves
- ALMA/NRAO complex radio/sub-mm products
- Gaia motion visualization
- ZTF transient/time-domain workflows
- large-scale batch APIs
- embeddings/semantic object discovery
- public web demo
- user feedback loops for ranking improvement

---

## 9. V1 Data Sources

### 9.1 Tier 1 Sources

Use these first because they cover identity, public images, multi-wavelength discovery, and citations.

| Source | V1 Role |
|---|---|
| SIMBAD | Object identity, aliases, coordinates, object types. |
| NED | Extragalactic identity, aliases, redshift/distance context. |
| MAST | Hubble, JWST, TESS, Kepler, GALEX and related archive records/products. |
| IRSA | Infrared/all-sky survey data and image/catalog access. |
| SkyView | Fast multi-wavelength image generation/preview by sky position. |
| HEASARC | High-energy archive/cat data, especially X-ray/gamma-ray context. |
| Chandra Data Archive | High-resolution X-ray observations/products where available. |
| ADS | Literature and citation context. |

### 9.2 Tier 2 Sources

Add after V1 works:

- Gaia Archive
- NASA Exoplanet Archive
- SDSS
- DESI
- NOIRLab / Legacy Surveys
- ALMA
- NRAO
- ZTF
- Rubin public/rights-aware products

---

## 10. Core Concepts

### 10.1 Celestial Object

A canonical resolved astronomical object.

Examples:

- M87
- Crab Nebula
- Orion Nebula
- Andromeda Galaxy
- Sagittarius A*

### 10.2 Observation

A telescope observation or archive record associated with an object or sky region.

### 10.3 Data Product

A specific downloadable or usable product associated with an observation.

Examples:

- FITS file
- calibrated image
- spectrum
- preview image
- catalog row
- cutout

### 10.4 View

An agent-facing abstraction representing the best usable interpretation of one wavelength/facility perspective on an object.

A `View` may be backed by one or more observations/products.

Examples:

- `view:crab:hubble:visible`
- `view:m87:chandra:xray`
- `view:orion:jwst:infrared`

### 10.5 Asset

A preview, thumbnail, rendered image, or externally hosted image associated with a view/product.

### 10.6 Fact

A small, source-grounded claim attached to an object, view, wavelength, observation, or asset.

Facts should be atomic and citeable.

### 10.7 EvidenceBundle

The main response object. It packages the object, views, facts, assets, citations, reuse metadata, caveats, and cache/source health details into one agent-friendly response.

---

## 11. Main API Contract: EvidenceBundle

### 11.1 Endpoint

```http
GET /v1/evidence?q={object_or_query}&bands=visible,infrared,xray,radio&max_views=6
```

Also support:

```http
GET /v1/objects/{object_id}/evidence?bands=visible,infrared,xray,radio&max_views=6
```

### 11.2 Response Shape

```json
{
  "object": {
    "id": "astro:object:crab_nebula",
    "name": "Crab Nebula",
    "aliases": ["Messier 1", "M1", "NGC 1952"],
    "type": "supernova remnant",
    "coordinates": {
      "ra_deg": 83.63308,
      "dec_deg": 22.0145,
      "frame": "ICRS"
    },
    "identity_sources": [
      {
        "name": "SIMBAD",
        "url": "https://...",
        "retrieved_at": "2026-06-30T00:00:00Z"
      }
    ]
  },
  "views": [
    {
      "id": "view:crab:hubble:visible",
      "label": "Visible-light view",
      "band_family": "visible",
      "facility": "Hubble Space Telescope",
      "instrument": "ACS",
      "source_archive": "MAST",
      "asset": {
        "asset_id": "asset:crab:hubble:visible:preview",
        "thumbnail_url": "https://cdn.example.com/...",
        "image_url": "https://cdn.example.com/...",
        "width": 1920,
        "height": 1080,
        "format": "png"
      },
      "raw_products": [
        {
          "product_id": "product:mast:hst:...",
          "file_format": "fits",
          "download_url": "https://..."
        }
      ],
      "facts": [
        {
          "claim": "Visible-light observations can show filamentary gas structure in the nebula.",
          "scope": "general_wavelength_interpretation",
          "confidence": 0.86,
          "citations": ["citation:mast:hst:..."]
        }
      ],
      "reuse": {
        "status": "usable_with_credit",
        "credit_required": true,
        "credit_text": "NASA, ESA, STScI...",
        "policy_url": "https://...",
        "commercial_use": "check_source_policy",
        "do_not_imply_endorsement": true
      },
      "citations": [
        {
          "id": "citation:mast:hst:...",
          "title": "MAST Hubble observation record",
          "source": "MAST",
          "url": "https://...",
          "credit_text": "NASA, ESA, STScI...",
          "retrieved_at": "2026-06-30T00:00:00Z"
        }
      ],
      "caveats": [
        "Colors may be mapped from filters and may not represent natural human vision.",
        "Observation dates may differ across wavelength views."
      ],
      "scores": {
        "object_match": 0.97,
        "public_access": 1.0,
        "asset_availability": 0.95,
        "preview_quality": 0.92,
        "science_ready": 0.88,
        "provenance_quality": 0.95,
        "overall": 0.93
      }
    }
  ],
  "cross_wavelength_notes": [
    {
      "band_family": "xray",
      "general_meaning": "X-rays often trace high-energy material such as hot gas, compact objects, shocks, or particle acceleration.",
      "confidence": 0.8
    },
    {
      "band_family": "infrared",
      "general_meaning": "Infrared observations often reveal cooler material, dust, embedded stars, or redshifted distant light.",
      "confidence": 0.8
    }
  ],
  "warnings": [],
  "meta": {
    "request_id": "req_...",
    "cache": {
      "status": "hit",
      "refreshed_at": "2026-06-30T00:00:00Z",
      "stale": false
    }
  }
}
```

---

## 12. REST API Requirements

### 12.1 Health

```http
GET /v1/health
```

Returns:

```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

```http
GET /v1/sources/health
```

Returns per-source status:

```json
{
  "sources": [
    {
      "name": "MAST",
      "status": "ok",
      "last_success_at": "2026-06-30T00:00:00Z",
      "last_error_at": null,
      "latency_ms": 420
    }
  ]
}
```

### 12.2 Resolve Object

```http
GET /v1/resolve?q=M87
```

Requirements:

- Accept object names, aliases, and coordinates.
- Return canonical object ID.
- Return aliases, type, coordinates, and identity sources.
- Return alternatives when ambiguous.
- Do not silently pick low-confidence matches.

### 12.3 Search

```http
GET /v1/search?q=Crab%20Nebula%20X-ray%20visible%20comparison&limit=10
```

Search should return objects, views, and assets that match the query.

### 12.4 Object Detail

```http
GET /v1/objects/{object_id}
```

Returns canonical object metadata.

### 12.5 Observations

```http
GET /v1/objects/{object_id}/observations?bands=visible,infrared,xray&public_only=true&limit=20
```

Returns normalized observation metadata. This is lower-level than `evidence` and mostly for developers.

### 12.6 Views

```http
GET /v1/objects/{object_id}/views?bands=visible,infrared,xray,radio&max=6
```

Returns ranked views without the full evidence wrapper.

### 12.7 Compare Wavelengths

```http
POST /v1/compare
```

Request:

```json
{
  "object": "M87",
  "bands": ["visible", "xray", "radio"],
  "max_views_per_band": 1
}
```

Response:

```json
{
  "object": {...},
  "comparison": [
    {
      "band_family": "visible",
      "view_id": "view:m87:hubble:visible",
      "facility": "Hubble Space Telescope",
      "asset_id": "asset:m87:hubble:visible",
      "general_interpretation": "Visible light often traces starlight and optical emission structures.",
      "citations": [...]
    }
  ],
  "caveats": [
    "Different wavelength views may not be simultaneous.",
    "Images may have different resolutions, fields of view, and color mappings."
  ]
}
```

### 12.8 Assets

```http
GET /v1/assets/{asset_id}
```

Returns asset metadata, URLs, dimensions, format, source products, citations, reuse policy, and caveats.

### 12.9 Citations

```http
GET /v1/assets/{asset_id}/citations
```

Returns citations and credit text.

### 12.10 Raw Links

```http
GET /v1/products/{product_id}/raw-links
```

Returns raw archive/source links. Use this for developers and agents that need deeper data access.

### 12.11 Render

```http
POST /v1/render
```

Rendering is cache-first and async for new renders.

If cached:

```json
{
  "status": "complete",
  "asset": {...}
}
```

If not cached:

```json
{
  "status": "queued",
  "job_id": "job:render:...",
  "poll_url": "/v1/jobs/job:render:..."
}
```

V1 rendering must be conservative:

- Prefer existing archive previews or already-rendered public assets.
- Only support simple FITS image rendering where safe.
- Do not block the request path for new FITS renders.
- Always include processing metadata and caveats.

---

## 13. MCP Server Requirements

AstroLens MCP should expose read-only tools only.

### 13.1 Required MCP Tools

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

### 13.2 Prohibited MCP Tools

Do not add:

- `create_lesson`
- `create_script`
- `create_creator_pack`
- `create_social_post`
- `generate_narration`
- `write_article`
- write/update/delete tools
- arbitrary fetch URL tool
- arbitrary code execution tool

### 13.3 MCP Tool: `search`

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

### 13.4 MCP Tool: `fetch`

Input:

```json
{
  "id": "object:astro:object:crab_nebula"
}
```

Output:

- Return object metadata plus compact evidence summary.
- Include citations.
- Keep output small by default.
- Provide IDs for follow-up calls.

### 13.5 MCP Tool: `resolve_object`

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
  "coordinates": {
    "ra_deg": 187.70593,
    "dec_deg": 12.39112
  },
  "confidence": 0.99,
  "ambiguity": {
    "status": "resolved",
    "alternatives": []
  },
  "sources": [...]
}
```

### 13.6 MCP Tool: `get_object_evidence`

Input:

```json
{
  "object": "Crab Nebula",
  "bands": ["visible", "infrared", "xray", "radio"],
  "max_views": 6
}
```

Output:

- Return `EvidenceBundle`.
- Prefer compact mode unless caller requests full detail.

### 13.7 MCP Tool: `compare_wavelengths`

Input:

```json
{
  "object": "M87",
  "bands": ["visible", "xray", "radio"]
}
```

Output:

- Return one ranked view per requested band when available.
- Include citations and caveats.

---

## 14. Data Model

### 14.1 Tables

Required tables:

- `objects`
- `object_aliases`
- `observations`
- `data_products`
- `views`
- `assets`
- `facts`
- `citations`
- `reuse_policies`
- `source_records`
- `source_cache`
- `source_health`
- `ingestion_jobs`
- `render_jobs`
- `ranking_feedback`

### 14.2 `objects`

```json
{
  "id": "astro:object:m87",
  "canonical_name": "M87",
  "object_type": "giant elliptical galaxy",
  "ra_deg": 187.70593,
  "dec_deg": 12.39112,
  "frame": "ICRS",
  "created_at": "...",
  "updated_at": "..."
}
```

### 14.3 `object_aliases`

```json
{
  "object_id": "astro:object:m87",
  "alias": "Messier 87",
  "source": "SIMBAD",
  "confidence": 0.99
}
```

### 14.4 `observations`

```json
{
  "id": "obs:mast:hst:abc123",
  "object_id": "astro:object:m87",
  "source_archive": "MAST",
  "facility": "Hubble Space Telescope",
  "instrument": "ACS",
  "band_family": "visible",
  "wavelength_min_nm": 435,
  "wavelength_max_nm": 814,
  "observation_date": "2006-02-15",
  "access_status": "public",
  "proprietary_until": null,
  "source_url": "https://...",
  "source_record_id": "...",
  "metadata": {}
}
```

### 14.5 `data_products`

```json
{
  "id": "product:mast:hst:abc123:i2d",
  "observation_id": "obs:mast:hst:abc123",
  "product_type": "image",
  "file_format": "fits",
  "calibration_level": "science_ready",
  "download_url": "https://...",
  "preview_url": "https://...",
  "file_size_mb": 512,
  "renderability_score": 0.82,
  "metadata": {}
}
```

### 14.6 `views`

```json
{
  "id": "view:m87:hubble:visible",
  "object_id": "astro:object:m87",
  "band_family": "visible",
  "facility": "Hubble Space Telescope",
  "asset_id": "asset:m87:hubble:visible:preview",
  "source_product_ids": ["product:mast:hst:..."],
  "scores": {
    "overall": 0.93
  }
}
```

### 14.7 `assets`

```json
{
  "id": "asset:m87:hubble:visible:preview",
  "source_product_ids": ["product:mast:hst:..."],
  "format": "png",
  "width": 1920,
  "height": 1080,
  "asset_url": "https://cdn.astrolens.dev/assets/...",
  "thumbnail_url": "https://cdn.astrolens.dev/thumbs/...",
  "false_color": true,
  "credit_text": "NASA/ESA/STScI...",
  "reuse_policy_id": "reuse:nasa:general"
}
```

### 14.8 `facts`

```json
{
  "id": "fact:infrared:general:001",
  "entity_type": "view",
  "entity_id": "view:orion:jwst:infrared",
  "claim": "Infrared observations can reveal dust-obscured regions and cooler material.",
  "scope": "general_wavelength_interpretation",
  "confidence": 0.82,
  "citation_ids": ["citation:..."]
}
```

### 14.9 `citations`

```json
{
  "id": "citation:mast:hst:abc123",
  "entity_type": "data_product",
  "entity_id": "product:mast:hst:abc123:i2d",
  "title": "MAST Hubble observation record",
  "source": "MAST",
  "url": "https://...",
  "credit_text": "NASA/ESA/STScI...",
  "retrieved_at": "2026-06-30T00:00:00Z"
}
```

### 14.10 `reuse_policies`

```json
{
  "id": "reuse:nasa:general",
  "status": "usable_with_credit",
  "commercial_use": "check_source_policy",
  "credit_required": true,
  "credit_text": "NASA/ESA/STScI...",
  "do_not_imply_endorsement": true,
  "policy_url": "https://...",
  "notes": [
    "Rights can vary by derived product.",
    "Always preserve source credit."
  ]
}
```

---

## 15. Ranking Requirements

Ranking is the key product moat.

Agents need the most useful evidence, not the largest archive dump.

### 15.1 Candidate Score

Compute a score for every candidate view:

```text
overall =
  0.25 * object_match
+ 0.15 * public_access
+ 0.15 * asset_availability
+ 0.10 * preview_quality
+ 0.10 * science_ready_level
+ 0.10 * provenance_quality
+ 0.05 * citation_quality
+ 0.05 * renderability
+ 0.05 * source_reliability
+ wavelength_diversity_bonus
- caveat_penalty
```

### 15.2 Score Definitions

| Score | Meaning |
|---|---|
| `object_match` | Does this observation actually cover the object, not just a nearby field? |
| `public_access` | Is it publicly usable now? |
| `asset_availability` | Is there a usable preview/image/thumbnail or renderable product? |
| `preview_quality` | Is the view visually meaningful for non-specialists/agents? |
| `science_ready_level` | Is it processed/calibrated enough for public use? |
| `provenance_quality` | Are source, date, archive, instrument, and product metadata clear? |
| `citation_quality` | Can an agent cite this correctly? |
| `renderability` | Can AstroLens provide a usable PNG/thumbnail quickly? |
| `source_reliability` | Is the source connector stable/cacheable? |
| `wavelength_diversity_bonus` | Does this view add a missing physical/wavelength perspective? |
| `caveat_penalty` | Is the product misleading, low-confidence, rights-unclear, noisy, or unavailable? |

### 15.3 Ranking Behavior

- Default `evidence` response should return 3–6 views.
- Avoid returning multiple near-duplicate views unless requested.
- Prefer wavelength diversity over many views from the same source.
- Prefer source-grounded, citation-rich products over visually impressive but poorly attributed products.
- Provide debug score output only when requested by internal/debug mode.

---

## 16. Explanation/Facts Requirements

V1 should not generate prose-heavy explanations.

It should return small, structured facts and caveats that agents can use.

### 16.1 Fact Requirements

Every fact must include:

- claim
- scope
- confidence
- citation IDs where applicable

### 16.2 Allowed Fact Scopes

- `object_identity`
- `observation_metadata`
- `general_wavelength_interpretation`
- `source_archive_metadata`
- `reuse_policy`
- `processing_caveat`

### 16.3 Prohibited Claims

Do not return:

- uncited specific scientific claims
- speculative interpretations as facts
- statements implying natural color unless verified
- claims that an image is official press imagery unless source confirms it
- claims of commercial reuse certainty unless policy is explicit

---

## 17. Caveats Requirements

Every evidence response should include caveats when relevant.

Common caveats:

- Colors may be false-color or filter-mapped.
- Images may not represent human-visible color.
- Different wavelength views may not be simultaneous.
- Different telescopes have different resolutions and fields of view.
- Non-detection in one band does not mean an object emits no radiation in that band.
- Raw data may require scientific processing before interpretation.
- Reuse rights may vary by source/product; preserve credit text and source links.

---

## 18. Rights and Reuse Requirements

Every asset and citation response must include a `reuse` object.

AstroLens should be conservative.

### 18.1 Reuse Status Values

- `usable_with_credit`
- `public_domain_or_open`
- `check_source_policy`
- `restricted_or_unknown`
- `temporary_proprietary`

### 18.2 Required Fields

```json
{
  "status": "usable_with_credit",
  "credit_required": true,
  "credit_text": "NASA/ESA/STScI...",
  "policy_url": "https://...",
  "commercial_use": "check_source_policy",
  "do_not_imply_endorsement": true,
  "notes": []
}
```

### 18.3 Rules

- Never omit credit text when known.
- Never imply NASA/ESA/CSA/STScI or archive endorsement.
- Do not collapse all public science data into one license label.
- Preserve source policy URL when available.
- Mark uncertain rights as `check_source_policy`, not `usable`.

---

## 19. Reliability Requirements

AstroLens is infrastructure. Reliability matters more than breadth.

### 19.1 Performance Targets

| Endpoint | Target |
|---|---:|
| `GET /v1/health` | P95 < 100 ms |
| `GET /v1/resolve` cached | P95 < 500 ms |
| `GET /v1/evidence` cached | P95 < 1200 ms |
| `GET /v1/objects/{id}/views` cached | P95 < 900 ms |
| `POST /v1/compare` cached | P95 < 1500 ms |
| MCP `search` | P95 < 1000 ms |
| MCP `fetch` | P95 < 1500 ms |
| New render | Async only |

### 19.2 Source Outage Behavior

If a source archive is down:

- serve cached data if available
- label cache as stale
- include warning
- do not fail the entire response if partial evidence is still available

Example warning:

```json
{
  "code": "SOURCE_UNAVAILABLE",
  "source": "MAST",
  "message": "Returned cached data from 2026-06-28 because live refresh failed.",
  "stale": true,
  "retryable": true
}
```

### 19.3 Source Protection

Implement:

- per-source timeout
- retry with exponential backoff
- circuit breaker
- rate limiting
- stale-while-revalidate
- request deduplication
- source-level health status
- background refresh jobs

Do not hammer public archives.

---

## 20. Architecture

### 20.1 Hot Path

Normal agent requests should not fan out to many external archives.

```text
Agent / REST caller
→ AstroLens API
→ local object resolver/cache
→ normalized metadata index
→ ranked evidence bundle
→ response
```

### 20.2 Cold Path

Archive integration should happen through background ingestion and refresh.

```text
source connectors
→ ingestion workers
→ normalization
→ scoring
→ asset cache
→ citation/reuse cache
→ local DB/index
```

### 20.3 Recommended Stack

- Python 3.12+
- FastAPI
- Pydantic v2
- SQLAlchemy 2.x
- Alembic
- Postgres + PostGIS
- Redis
- Celery or RQ
- httpx
- tenacity
- structlog
- OpenTelemetry
- pytest
- respx
- ruff
- pyright
- Docker Compose

### 20.4 Astronomy Packages

- astropy
- astroquery
- pyvo
- reproject, later if needed
- Pillow/imageio

---

## 21. Connector Interface

Every archive connector should implement the same contract.

```python
from typing import Protocol

class ArchiveConnector(Protocol):
    name: str

    async def healthcheck(self) -> SourceHealth:
        ...

    async def resolve_object(self, query: str) -> list[ResolvedObjectCandidate]:
        ...

    async def search_observations(
        self,
        region: SkyRegion,
        filters: ObservationFilters,
    ) -> list[ObservationCandidate]:
        ...

    async def list_products(
        self,
        observation_id: str,
    ) -> list[ProductCandidate]:
        ...

    async def get_citation(
        self,
        source_record_id: str,
    ) -> Citation:
        ...
```

Connector rules:

- Connectors return normalized candidates.
- Connectors preserve raw source metadata separately.
- Connectors never write directly to the database.
- Connectors have fixture-based tests.
- Connectors have source-specific timeout/retry settings.
- Connectors expose health status.
- Unit tests must not call live external APIs.

---

## 22. Ingestion Strategy

### 22.1 Curated Seed Ingestion

Start with a curated object list and verified evidence.

For each object:

- resolve identity
- store aliases and coordinates
- gather candidate views
- select best views
- store citations
- store reuse metadata
- cache previews/assets
- write golden tests

### 22.2 On-Demand Ingestion

When cache misses:

1. Resolve object.
2. Return quick partial result if possible.
3. Enqueue deeper refresh.
4. Mark response as partial/stale if needed.

### 22.3 Scheduled Refresh

Suggested cadence:

- source health: every 5 minutes
- popular objects: weekly
- object identity: monthly
- citations/reuse policies: monthly
- rendered assets: immutable unless source product changes

---

## 23. Golden Object Set

V1 should launch with 50 curated objects.

Minimum initial set:

- M87
- Crab Nebula
- Orion Nebula
- Andromeda Galaxy
- Pillars of Creation
- Carina Nebula
- Cassiopeia A
- Sagittarius A*
- Sombrero Galaxy
- Whirlpool Galaxy
- Horsehead Nebula
- Ring Nebula
- Eagle Nebula
- Tarantula Nebula
- Centaurus A
- Eta Carinae
- Cartwheel Galaxy
- Antennae Galaxies
- Stephan’s Quintet
- Helix Nebula
- Triangulum Galaxy
- Large Magellanic Cloud
- Small Magellanic Cloud
- NGC 1300
- NGC 253
- NGC 1365
- NGC 4258
- 3C 273
- Cygnus A
- Vela Supernova Remnant

For each object, precompute:

- canonical ID
- aliases
- coordinates
- object type
- best visible view if available
- best infrared view if available
- best X-ray view if available
- best radio/all-sky view if available
- citations
- reuse text
- caveats
- raw source links
- agent-ready compact evidence response

---

## 24. Error Handling

Use one consistent error shape.

```json
{
  "error": {
    "code": "OBJECT_AMBIGUOUS",
    "message": "The query 'M31' matched multiple possible objects.",
    "retryable": false,
    "request_id": "req_...",
    "details": {
      "alternatives": [
        {
          "name": "Andromeda Galaxy",
          "object_id": "astro:object:m31"
        }
      ]
    }
  }
}
```

Required error codes:

- `OBJECT_NOT_FOUND`
- `OBJECT_AMBIGUOUS`
- `SOURCE_UNAVAILABLE`
- `SOURCE_TIMEOUT`
- `PRODUCT_NOT_PUBLIC`
- `PRODUCT_TOO_LARGE`
- `RENDER_NOT_SUPPORTED`
- `RATE_LIMITED`
- `INVALID_COORDINATES`
- `UNSUPPORTED_BAND`
- `INTERNAL_ERROR`

---

## 25. Security Requirements

V1 is read-only.

### 25.1 API Security

Implement:

- API keys for developers
- rate limits by key/IP
- request size limits
- pagination limits
- signed asset URLs if needed
- no arbitrary URL fetch from user input
- no shell execution from source metadata
- structured logging without secrets
- allowlisted outbound source hosts

### 25.2 MCP Security

MCP tools must be:

- read-only
- schema-validated
- deterministic where possible
- rate-limited
- free of secrets in outputs
- unable to write/update/delete data
- unable to fetch arbitrary URLs
- unable to execute arbitrary code

---

## 26. Observability Requirements

Implement structured telemetry for:

- request ID
- endpoint latency
- cache hit/miss/stale
- connector latency
- connector errors/timeouts
- ranking score distribution
- render job duration
- source health
- MCP tool calls
- rate-limit events

Required logs must not include API keys or secrets.

---

## 27. Testing Requirements

### 27.1 Unit Tests

Cover:

- object resolver confidence
- alias normalization
- coordinate parsing
- source connector parsing
- ranking formula
- citation generation
- reuse policy merging
- caveat generation
- error response shape
- MCP schema validation

### 27.2 Integration Tests

Use recorded fixtures for:

- SIMBAD response
- NED response
- MAST response
- IRSA response
- SkyView response
- HEASARC response
- ADS response

No live external calls in CI by default.

### 27.3 Golden Object Tests

For each golden object, assert:

- object resolves correctly
- aliases include expected names
- coordinates are within tolerance
- evidence returns at least one view
- multi-wavelength objects return multiple bands when available
- citations are present
- reuse policy is present
- caveats are present where applicable
- response stays under token/output budget for MCP
- no hallucinated assets

### 27.4 Agent Evaluation Prompts

Use these prompts against MCP tools:

- “Get evidence for the Crab Nebula across visible, infrared, X-ray, and radio.”
- “Find public telescope views of M87 and cite the sources.”
- “Compare Hubble and JWST evidence for star-forming regions.”
- “Has JWST observed the Orion Nebula? Return raw links if available.”
- “Give me the best X-ray evidence for Cassiopeia A.”

Evaluate:

- correct object
- correct source
- citations present
- asset URLs present when available
- caveats present
- no content-generation endpoints used
- response size acceptable

---

## 28. Repository Structure

```text
astrolens/
  AGENTS.md
  README.md
  ARCHITECTURE.md
  SECURITY.md
  RELIABILITY.md
  pyproject.toml
  docker-compose.yml

  docs/
    product-specs/
      astrolens-prd.md
    design-docs/
      evidence-bundle.md
      source-connectors.md
      ranking.md
      mcp-server.md
      rendering.md
      reuse-and-citations.md
    exec-plans/
      active/
      completed/

  src/
    astrolens/
      api/
        main.py
        routes/
          health.py
          resolve.py
          search.py
          objects.py
          evidence.py
          views.py
          observations.py
          compare.py
          assets.py
          jobs.py

      mcp/
        server.py
        tools.py
        schemas.py

      core/
        models.py
        enums.py
        errors.py
        provenance.py
        scoring.py

      db/
        session.py
        models.py
        migrations/

      services/
        resolver.py
        evidence.py
        ranking.py
        assets.py
        citations.py
        cache.py

      connectors/
        base.py
        simbad.py
        ned.py
        mast.py
        irsa.py
        skyview.py
        heasarc.py
        ads.py

      rendering/
        fits_to_png.py
        thumbnails.py

      workers/
        ingestion.py
        refresh.py
        render.py

  tests/
    unit/
    integration/
    fixtures/
    golden/
```

---

## 29. AGENTS.md

Place this at repo root.

```md
# AGENTS.md

## Project
AstroLens Evidence API: an agent-first, read-only API for retrieving reliable public astronomy telescope evidence.

## Product boundary
AstroLens provides evidence infrastructure only:
- object resolution
- ranked telescope views
- assets/previews/raw links
- observations/products
- citations
- reuse metadata
- caveats
- provenance

AstroLens does not generate lesson plans, scripts, social posts, creator packs, teacher packs, or long-form educational content. Agents and downstream apps generate those using AstroLens evidence.

## Required docs
Before coding, read:
- docs/product-specs/astrolens-prd.md
- docs/design-docs/evidence-bundle.md
- docs/design-docs/source-connectors.md
- docs/design-docs/ranking.md
- docs/design-docs/mcp-server.md
- SECURITY.md
- RELIABILITY.md

## Commands
- Install: `uv sync`
- Run API: `uv run uvicorn astrolens.api.main:app --reload`
- Test: `uv run pytest`
- Lint: `uv run ruff check .`
- Format: `uv run ruff format .`
- Typecheck: `uv run pyright`

## Coding rules
- Use Pydantic v2 schemas at API boundaries.
- Use typed domain models.
- Do not pass unstructured dicts across service boundaries except for raw source metadata.
- Every public response containing scientific evidence must include citations or provenance.
- Never call external archives directly from route handlers.
- Use connector classes under `src/astrolens/connectors`.
- Unit tests must use fixtures/mocks, not live network calls.
- Integration tests may be marked and skipped by default.

## MCP rules
- V1 MCP tools are read-only.
- Do not add write/update/delete tools.
- Do not add lesson/script/content-generation tools.
- Keep MCP outputs compact and structured.
- Include source URLs and citations.

## Definition of done
A task is done only when:
- tests pass
- lint passes
- typecheck passes
- OpenAPI schemas are updated if API shape changes
- docs are updated if behavior changes
```

---

## 30. Milestones

### Milestone 1 — Skeleton

Build:

- FastAPI app
- Pydantic schemas
- typed error model
- health endpoints
- OpenAPI generation
- pytest
- ruff
- pyright
- Docker Compose
- Postgres
- Redis
- root `AGENTS.md`

Acceptance:

- `uv sync` works
- `uv run pytest` passes
- `uv run ruff check .` passes
- `uv run pyright` passes
- `GET /v1/health` returns status ok
- OpenAPI schema includes `EvidenceBundle` and error models

### Milestone 2 — Domain Model and DB

Build:

- SQLAlchemy models
- Alembic migration
- Pydantic API models
- CRUD helpers for core entities

Acceptance:

- migrations run
- sample object can be inserted/read
- models serialize correctly
- DB tests pass

### Milestone 3 — Resolver

Build:

- `GET /v1/resolve`
- resolver service
- SIMBAD connector shell/fixture implementation
- NED connector shell/fixture implementation
- ambiguity handling
- source cache

Acceptance:

- M87 resolves
- Crab Nebula resolves
- ambiguous query returns alternatives
- citations/provenance included
- fixture-based tests pass

### Milestone 4 — EvidenceBundle

Build:

- `GET /v1/evidence`
- `GET /v1/objects/{id}/evidence`
- core `EvidenceBundle` service
- initial curated fixtures for 10–20 objects

Acceptance:

- evidence response includes object, views, assets, facts, citations, reuse, caveats, meta
- no lesson/script/content generation
- golden tests pass for seed objects

### Milestone 5 — Source Connectors

Build connectors for:

- MAST
- IRSA
- SkyView
- HEASARC
- ADS

Acceptance:

- connectors implement common interface
- fixture tests pass
- source health works
- timeout/retry behavior exists
- route handlers do not call connectors directly

### Milestone 6 — Ranking

Build:

- candidate scoring
- view ranking
- wavelength diversity logic
- debug scoring mode
- golden object ranking tests

Acceptance:

- best views sorted by score
- duplicate/near-duplicate views suppressed by default
- citations/reuse/caveats included
- ranking tests pass

### Milestone 7 — MCP Server

Build read-only tools:

- `search`
- `fetch`
- `resolve_object`
- `get_object_evidence`
- `get_best_views`
- `compare_wavelengths`
- `get_asset`
- `get_citations`
- `get_raw_links`

Acceptance:

- tool schemas validate
- outputs are compact and structured
- citations included
- no content-generation tools exist
- agent eval prompts pass

### Milestone 8 — Rendering

Build:

- asset cache
- existing preview preference
- async render jobs
- basic FITS-to-PNG for supported simple image products
- metadata/caveat output

Acceptance:

- cached asset returns immediately
- unsupported render returns `RENDER_NOT_SUPPORTED`
- new render queues job
- render result includes provenance, false-color flag, credit text, processing note

---

## 31. First Codex Prompt

Use this prompt for the first implementation task.

```text
Build AstroLens Evidence API v1 Milestone 1 only.

AstroLens is an agent-first, read-only astronomy retrieval API. It provides object resolution, ranked telescope views, assets, citations, reuse metadata, raw archive links, and provenance. It does not generate lesson plans, teacher packs, creator packs, scripts, social posts, or long-form educational content. Agents like ChatGPT and Claude will use this API as infrastructure and produce user-facing content themselves.

Read these first:
- AGENTS.md
- docs/product-specs/astrolens-prd.md

Implement:
1. FastAPI app under src/astrolens/api.
2. Pydantic v2 schemas for:
   - CelestialObject
   - ObjectAlias
   - Observation
   - DataProduct
   - View
   - Asset
   - Fact
   - Citation
   - ReusePolicy
   - EvidenceBundle
   - SourceHealth
   - APIError
3. Routes:
   - GET /v1/health
   - GET /v1/sources/health
4. ArchiveConnector protocol under src/astrolens/connectors/base.py.
5. Typed error response format.
6. pytest setup.
7. ruff and pyright config.
8. Docker Compose with API, Postgres, and Redis.
9. AGENTS.md with project rules if missing.
10. No live external API calls yet.
11. No MCP yet.
12. No rendering yet.
13. No lesson/creator/script/content-generation endpoints.

Acceptance criteria:
- uv sync works
- uv run pytest passes
- uv run ruff check . passes
- uv run pyright passes
- GET /v1/health returns {"status":"ok"}
- OpenAPI schema includes EvidenceBundle and error models
```

---

## 32. Definition of V1 Done

V1 is complete when:

- REST API deployed
- MCP server deployed
- at least 50 curated objects available
- object resolution works for common names/aliases
- `GET /v1/evidence` works
- views are ranked
- citations and reuse metadata are present everywhere needed
- cache-first behavior works
- source health is visible
- source outage degrades gracefully
- MCP tools work in read-only mode
- golden object evals pass
- docs exist
- SDK stubs or generated clients exist
- no lesson/script/creator-pack endpoints exist

Hard acceptance scenarios:

1. An agent can ask for Crab Nebula evidence across visible, infrared, X-ray, and radio and receive ranked views, assets, citations, caveats, and raw links.
2. An agent can resolve M87 and retrieve best available public views without knowing MAST, NED, SIMBAD, HEASARC, or IRSA APIs.
3. A source outage returns stale/cache warnings rather than failing the entire response.
4. Every asset returned includes citation and reuse metadata.
5. MCP tools remain read-only and evidence-focused.

---

## 33. Product Positioning

Use this positioning internally:

> AstroLens is the evidence layer between public telescope archives and AI agents.

Do not position it as:

- a lesson generator
- a creator tool
- a NASA clone
- a professional astronomy replacement
- a generic archive wrapper

Position it as:

- agent infrastructure
- astronomy evidence retrieval
- public telescope data normalization
- citation and provenance layer
- one-call object evidence API

---

## 34. Open Decisions

Defaults for V1 unless changed:

1. **Frontend:** no full frontend; optional tiny demo later.
2. **Generation:** no content generation in API.
3. **Data:** cache metadata/assets; do not mirror raw archives.
4. **MCP:** read-only only.
5. **Rendering:** cache-first and async.
6. **Rights:** conservative reuse labels.
7. **Ranking:** human-curated seed plus deterministic scoring.
8. **First launch:** API + MCP + 50 curated objects.

---

## 35. Codex Implementation Best Practices

This section exists to help Codex implement AstroLens accurately and incrementally. The product should be built as reliable infrastructure, not as a sprawling prototype.

### 35.1 Operating Model

Codex should work in small, reviewable increments.

Default workflow for every non-trivial task:

1. Read `AGENTS.md`.
2. Read only the relevant PRD/design sections.
3. Produce or update a short execution plan.
4. Implement one bounded milestone or subtask.
5. Add or update tests.
6. Run the required checks.
7. Review the diff against the acceptance criteria.
8. Report what changed, what was tested, and what remains.

Do not ask Codex to implement multiple large milestones in one run. That increases the chance of architectural drift, fake integrations, missing tests, and unusable abstractions.

### 35.2 Prompt Contract for Codex Tasks

Every Codex implementation prompt should include four blocks:

```text
Goal:
  The one thing Codex must build or change.

Context:
  The exact files/docs Codex must read first.

Constraints:
  Architectural, security, product, and testing rules Codex must obey.

Done when:
  Concrete acceptance criteria and commands that must pass.
```

Good task prompts are specific, testable, and scoped. Bad task prompts are broad, vague, or product-level.

Bad:

```text
Build the AstroLens API.
```

Good:

```text
Implement Milestone 3: object resolution only.
Read AGENTS.md, docs/product-specs/astrolens-prd.md sections 8, 9, 11, 20, and docs/design-docs/object-resolution.md.
Implement GET /v1/resolve using fixture-backed SIMBAD and NED connector adapters.
Do not add live external calls yet.
Done when M87 and Crab Nebula resolve in tests, ambiguous queries return alternatives, ruff passes, pyright passes, and pytest passes.
```

### 35.3 Use Plan Mode for Hard Tasks

For complex tasks, ask Codex to plan before coding.

Use this pattern:

```text
Before editing code, inspect the relevant files and produce a short implementation plan.
Call out any ambiguity, risky dependency, schema mismatch, or missing test fixture.
Do not implement until the plan is internally consistent with AGENTS.md and the PRD.
```

Use planning for:

- source connector architecture
- database migrations
- MCP server design
- ranking logic
- render pipeline
- cache invalidation behavior
- security-sensitive changes
- schema changes that affect public API responses

For small tasks, such as fixing a test or adding a field to a schema, planning can be skipped.

### 35.4 Keep `AGENTS.md` Short and Enforceable

`AGENTS.md` should not be a second PRD. It should contain always-on rules Codex must follow in this repository.

Recommended root `AGENTS.md`:

```md
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
```

Add nested `AGENTS.md` files only when a directory needs different durable rules. For example:

```text
src/astrolens/connectors/AGENTS.md
src/astrolens/mcp/AGENTS.md
src/astrolens/rendering/AGENTS.md
```

Keep nested files short and local.

### 35.5 Directory-Specific Guidance

#### Connector directory guidance

Use this in `src/astrolens/connectors/AGENTS.md` if needed:

```md
# Connector rules

- Connectors normalize source records into domain candidates.
- Connectors preserve raw source metadata under `raw_metadata`.
- Connectors do not write to the database.
- Connectors do not decide final ranking.
- Connectors must expose healthcheck behavior.
- Unit tests must use fixtures or mocked HTTP responses.
- Live integration tests must be marked and skipped by default.
- Each connector must define source-specific timeout and retry policy.
```

#### MCP directory guidance

Use this in `src/astrolens/mcp/AGENTS.md` if needed:

```md
# MCP rules

- MCP tools are read-only in V1.
- Do not add content-generation tools.
- Tool outputs must be compact, structured, and citation-ready.
- Tool schemas must be strict and versioned.
- Tools should call service-layer functions, not source connectors directly.
- Include stable IDs, URLs, confidence, citations, caveats, and cache metadata where relevant.
```

#### Rendering directory guidance

Use this in `src/astrolens/rendering/AGENTS.md` if needed:

```md
# Rendering rules

- Prefer existing public previews before generating new renders.
- New FITS renders must be async jobs unless already cached.
- Rendered assets must include provenance, false-color status, processing note, and credit text.
- Unsupported files should return `RENDER_NOT_SUPPORTED`, not crash.
- Do not present AstroLens-generated renders as official press images.
```

### 35.6 Codex Task Template

Use this template for each milestone/subtask.

```text
Task: <specific task name>

Goal:
<one clear outcome>

Context to read first:
- AGENTS.md
- docs/product-specs/astrolens-prd.md sections <specific sections>
- <specific source files or design docs>

Scope:
- <what to implement>
- <what tests to add>
- <what docs to update>

Out of scope:
- <explicitly forbidden adjacent work>

Constraints:
- no live external calls in unit tests
- preserve public API compatibility unless this task explicitly changes it
- no generation endpoints
- no write-capable MCP tools
- use service/connector boundaries

Done when:
- <behavioral acceptance tests>
- `uv run pytest` passes
- `uv run ruff check .` passes
- `uv run pyright` passes
- OpenAPI updated if needed
- Codex summarizes changed files and remaining risks
```

### 35.7 Golden Rule for Accuracy

AstroLens must prefer a smaller correct answer over a broader speculative answer.

If evidence is missing, uncertain, stale, or source access fails, the API should say so explicitly.

Correct behavior:

```json
{
  "warnings": [
    {
      "code": "SOURCE_UNAVAILABLE",
      "source": "MAST",
      "message": "Returned cached data from 2026-06-28 because live refresh failed.",
      "stale": true
    }
  ]
}
```

Incorrect behavior:

```text
Silently dropping MAST results and returning an answer that appears complete.
```

### 35.8 Accuracy Guardrails Codex Must Preserve

Codex must not introduce behavior that:

- invents observations, assets, raw links, papers, or citations
- treats a search result as a confirmed object match without confidence scoring
- omits ambiguity when object resolution is uncertain
- hides stale-cache status
- returns scientific facts without citations/provenance
- returns public-use assets without credit/reuse metadata
- overclaims commercial use rights
- claims generated renders are official archive products
- claims different wavelength images are simultaneous unless source metadata proves it
- treats false-color images as natural human vision unless the source explicitly says so
- bypasses service/connector boundaries to make routes “quickly work”

### 35.9 Testing Strategy for Codex

Tests should be the implementation rails.

#### Required test categories

| Test type | Required for | Notes |
|---|---|---|
| Unit tests | services, ranking, schemas, error handling | Fast and deterministic. |
| Fixture connector tests | every source connector | No live network calls. |
| Contract tests | REST responses and MCP tools | Prevent schema drift. |
| Golden object tests | curated famous objects | Protect correctness and usefulness. |
| OpenAPI snapshot test | public API changes | Forces intentional schema changes. |
| Security tests | unsafe URL fetch, write MCP tools, missing auth where needed | Prevents high-risk regressions. |
| Performance smoke tests | cached evidence and resolve paths | Protects agent UX. |

#### Test commands

```text
uv run pytest
uv run pytest tests/unit
uv run pytest tests/golden
uv run pytest tests/integration -m integration  # optional/manual
uv run ruff check .
uv run pyright
```

#### Unit-test rule

Unit tests must not call live astronomy archives.

Use:

- checked-in JSON fixtures
- mocked HTTP with `respx` or equivalent
- deterministic fake connectors
- recorded source records with sensitive values removed

Live source calls belong only in manually triggered integration tests.

### 35.10 Golden Objects and Evals

Codex should maintain a golden-object suite. These are known objects used to test object resolution, ranking, citations, and evidence output.

Initial golden objects:

```text
M87
Crab Nebula
Orion Nebula
Andromeda Galaxy
Pillars of Creation
Cassiopeia A
Sagittarius A*
Carina Nebula
Sombrero Galaxy
Whirlpool Galaxy
```

Each golden object test should verify:

- canonical object ID resolves
- aliases include expected names
- coordinates are within tolerance
- object type is plausible
- evidence bundle returns at least one useful view when fixture data exists
- returned views include citations
- returned views include reuse metadata
- caveats are included for false color or non-simultaneous comparisons
- no lesson/script/creator-pack fields appear
- response remains below defined size limits

### 35.11 Fixture Policy

Every connector must have a fixture folder:

```text
tests/fixtures/simbad/
tests/fixtures/ned/
tests/fixtures/mast/
tests/fixtures/irsa/
tests/fixtures/skyview/
tests/fixtures/heasarc/
tests/fixtures/ads/
```

Fixture files should include:

```text
raw_response.json
normalized_expected.json
source_notes.md
```

`source_notes.md` should document:

- where the fixture came from
- date retrieved
- query used
- fields relied upon by parser
- known caveats
- whether the fixture is synthetic, trimmed, or recorded

Do not let Codex create fake fixtures that look like real source data unless the fixture is clearly labeled synthetic.

### 35.12 Source Connector Best Practices

Every connector should follow this structure:

```text
parse raw source response
validate source fields
normalize into domain candidate model
attach source provenance
attach raw metadata
return candidates
```

Connector rules:

- no DB writes
- no ranking decisions
- no user-facing prose generation
- no global HTTP clients without timeout config
- no broad exception swallowing
- no unbounded result lists
- no silent truncation
- no direct route-handler usage

Each connector must define:

```text
source name
base URL or protocol
timeout
retry policy
rate-limit policy
healthcheck behavior
fixture tests
normalization tests
known limitations
```

### 35.13 Ranking Implementation Best Practices

Ranking must be deterministic in V1.

Codex should implement ranking as explicit, testable scoring functions rather than hidden heuristics scattered across services.

Recommended structure:

```text
services/ranking.py
  score_object_match(candidate)
  score_public_access(candidate)
  score_asset_availability(candidate)
  score_preview_quality(candidate)
  score_science_ready(candidate)
  score_provenance_quality(candidate)
  score_citation_quality(candidate)
  score_renderability(candidate)
  score_source_reliability(candidate)
  apply_wavelength_diversity_bonus(candidates)
  suppress_duplicates(candidates)
  rank_views(candidates, request_context)
```

Tests should cover:

- public asset beats inaccessible asset
- exact object match beats nearby field
- view with citations beats view without citations
- duplicate views are suppressed
- wavelength diversity improves final bundle
- low-confidence object match is not selected by default
- stale source data is labeled, not hidden

### 35.14 MCP Implementation Best Practices

MCP tools should be thin wrappers over service-layer calls.

Rules:

- no write tools
- no generation tools
- no arbitrary network tools
- no direct connector calls from MCP tools
- strict input/output schemas
- compact defaults with pagination or limits
- stable IDs for `fetch`
- citations and URLs in every evidence-bearing result
- explicit warnings for stale or partial data

Minimum MCP tool set:

```text
search
fetch
resolve_object
get_object_evidence
get_best_views
compare_wavelengths
get_asset
get_citations
get_raw_links
```

MCP response-size discipline:

- default `max_views` should be small, such as 6
- default search limit should be small, such as 10
- raw metadata should be omitted by default
- raw metadata should require `include_raw_metadata=true`
- large asset lists should be paginated

### 35.15 API Schema Best Practices

Public API schemas must be stable and boring.

Rules:

- use Pydantic models at all API boundaries
- never return arbitrary dicts as the top-level public response
- every response includes `meta.request_id`
- evidence responses include cache metadata
- warnings are structured and machine-readable
- errors use one error envelope
- confidence scores are numeric and documented
- unknown fields from sources live under `raw_metadata`, not mixed into public models
- breaking changes require API version bump or compatibility shim

Preferred error shape:

```json
{
  "error": {
    "code": "OBJECT_AMBIGUOUS",
    "message": "The query matched multiple possible objects.",
    "retryable": false,
    "request_id": "req_...",
    "details": {
      "alternatives": []
    }
  }
}
```

### 35.16 Security Best Practices for Codex Tasks

Codex must preserve these security constraints:

- V1 is read-only.
- API keys/secrets must never be committed.
- No arbitrary user-provided URL fetching.
- External calls must go through approved connectors.
- MCP tools must not modify local files, databases, remote sources, or user accounts.
- Logs must not include secrets or full signed URLs if they contain credentials.
- Request body sizes must be bounded.
- Pagination limits must be enforced.
- Asset fetch/render jobs must validate product IDs against known indexed products.
- Source errors must not leak internal stack traces in public responses.

Add tests for these where practical.

### 35.17 Performance and Reliability Best Practices

Codex should not make the hot path depend on live archive fan-out.

Default request path:

```text
request → local DB/cache/index → ranked evidence bundle → response
```

External archive calls should happen in:

- ingestion jobs
- refresh jobs
- explicit admin/manual refresh
- controlled cache-miss behavior

Performance guardrails:

- use timeouts on every external call
- use retries only for safe idempotent calls
- use circuit breakers/source health flags
- use stale-while-revalidate behavior
- cap result lists
- avoid N+1 queries
- add indexes for object aliases and coordinates
- cache popular evidence bundles
- async render jobs only for non-cached renders

### 35.18 Code Review Checklist for Codex Diff Review

After every meaningful Codex task, run a review prompt like:

```text
Review the diff against AGENTS.md and docs/product-specs/astrolens-prd.md.
Focus on correctness, evidence/provenance, security, tests, API schema stability, and non-goal violations.
List concrete line-level issues.
Do not suggest broad rewrites unless required.
```

Checklist:

- Does this introduce any content-generation endpoint?
- Does this preserve read-only MCP behavior?
- Are public schemas typed and documented?
- Are citations/provenance present where needed?
- Are reuse/credit fields present where needed?
- Are errors structured?
- Are source outages handled gracefully?
- Are unit tests fixture-based?
- Are live integration tests skipped by default?
- Are new dependencies justified?
- Are external calls made only through connectors?
- Are acceptance criteria actually tested?
- Are performance implications reasonable?

### 35.19 Prompt Examples for Codex

#### Good: schema-only task

```text
Task: Implement EvidenceBundle schemas only.

Goal:
Add typed Pydantic v2 schemas for CelestialObject, View, Asset, Fact, Citation, ReusePolicy, EvidenceBundle, SourceHealth, and APIError.

Context:
Read AGENTS.md and PRD sections 11, 12, 15, and 35.

Constraints:
No routes except importing schemas if needed.
No DB models yet.
No live source calls.
No content-generation models.

Done when:
Schema tests pass, OpenAPI includes EvidenceBundle, ruff passes, pyright passes.
```

#### Good: connector parser task

```text
Task: Implement MAST fixture parser.

Goal:
Parse recorded MAST fixture responses into ObservationCandidate and ProductCandidate models.

Context:
Read AGENTS.md, PRD sections 18, 20, 21, 35.11, and docs/design-docs/source-connectors.md.

Constraints:
No live HTTP calls in unit tests.
No DB writes from connector.
No ranking decisions in connector.
Preserve raw source metadata.

Done when:
MAST fixture parser tests pass, normalized_expected.json comparison passes, ruff passes, pyright passes.
```

#### Good: MCP task

```text
Task: Add MCP get_object_evidence tool.

Goal:
Expose read-only MCP tool `get_object_evidence` backed by the existing EvidenceService.

Context:
Read AGENTS.md, PRD sections 10, 15, 22, 35.14, and docs/design-docs/mcp.md.

Constraints:
No write tools.
No content-generation tools.
No direct connector calls.
Default max_views <= 6.
Include citations, caveats, cache metadata, and stable IDs.

Done when:
MCP schema tests pass, tool returns fixture-backed evidence for Crab Nebula, ruff passes, pyright passes.
```

### 35.20 Anti-Patterns Codex Must Avoid

Do not allow Codex to:

- create broad placeholder code with TODOs instead of tested behavior
- silently invent fake archive fields
- add live network calls to unit tests
- bypass the connector/service architecture
- generate user-facing lessons/scripts inside AstroLens
- hardcode source results directly into service code
- swallow exceptions and return empty success responses
- make rendering synchronous for large products
- return raw source dumps by default
- change public schemas without tests
- add dependencies just because they are convenient
- add frontend work before the API is useful
- make MCP tools too broad or creative
- treat the PRD as optional when implementing

### 35.21 When to Stop a Codex Run

Stop or redirect Codex if it:

- expands beyond the requested milestone
- starts building downstream content-generation features
- adds broad abstractions with no tests
- cannot explain how a source fixture maps to the normalized model
- cannot run or explain tests
- changes public API shape accidentally
- creates unbounded search/render behavior
- hides source failures
- creates security-sensitive behavior without tests

The correct response is to narrow the task, restore the architecture boundary, and add tests before continuing.

### 35.22 PR Description Template

Each Codex-produced PR should use this template:

```md
## Summary
- <what changed>
- <what was intentionally left out>

## Product boundary check
- [ ] No lesson/script/creator-pack/content-generation endpoint added
- [ ] V1 remains read-only
- [ ] MCP tools, if changed, remain evidence-focused

## Evidence/provenance check
- [ ] Citations included where needed
- [ ] Reuse/credit metadata included where needed
- [ ] Stale/partial/source-error behavior represented if applicable

## Testing
- [ ] `uv run pytest`
- [ ] `uv run ruff check .`
- [ ] `uv run pyright`
- [ ] Golden tests updated if object/evidence behavior changed
- [ ] OpenAPI updated if public schema changed

## Risks / follow-ups
- <known limitations>
- <manual validation needed>
```

### 35.23 Codex Configuration Recommendations

Use conservative defaults early.

Recommended approach:

- keep repo-level instructions in root `AGENTS.md`
- keep product detail in this PRD and design docs
- use `.codex/config.toml` only for durable repo-specific Codex settings
- use tight sandbox/approval settings for untrusted repos
- only loosen approvals after the repo is stable and tests are strong
- use MCP connections for docs/source systems only when needed
- do not give Codex credentials for production systems during early implementation

Recommended `.codex/config.toml` shape if needed:

```toml
# .codex/config.toml
# Keep this minimal. Prefer AGENTS.md for repo rules.

[tools]
# Configure project-approved MCP/doc tools here later if needed.

[profiles.default]
# Add repo-specific defaults only after workflow stabilizes.
```

### 35.24 Codex Success Criteria

Codex is being used well if:

- tasks are small and reviewable
- tests grow with implementation
- public schemas stay stable
- source integrations are fixture-backed before live-backed
- ambiguity and stale data are explicit
- MCP tools remain compact and read-only
- the system returns useful evidence without pretending to generate final user content
- every new abstraction has a clear reason and tests

Codex is being used poorly if:

- it produces lots of code but weak tests
- it chases frontend/product features before the evidence API works
- it invents missing source behavior
- it hides source failures
- it expands scope because it “seems useful”
- it adds content-generation endpoints despite the product boundary

