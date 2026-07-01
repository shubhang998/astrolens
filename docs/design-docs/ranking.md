# Ranking Design

## Purpose

AstroLens should not return archive dumps. It should return the most useful evidence for an agent. Ranking determines which candidate views/products become `View` records in an `EvidenceBundle`.

The goal is **agent usefulness**, not just beauty.

## Ranking objective

Select views that are:

- actually about the requested object
- publicly accessible
- usable by agents and humans
- backed by clear provenance/citations
- accompanied by assets/previews/raw links
- diverse across wavelengths when requested
- not misleading without caveats

## Candidate scoring

Initial scoring formula:

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

All component scores should be floats from 0.0 to 1.0 unless otherwise documented.

## Score definitions

### object_match

Measures whether the observation/product actually covers the target object.

Inputs:

- resolved object coordinates
- product footprint/region when available
- source target name
- aliases
- search radius
- known object size when available

Rules:

- High score if source target name or footprint clearly matches.
- Lower score if object is merely within a large field.
- Very low score if coordinate match is weak or ambiguous.

### public_access

Measures whether the product can be used immediately.

- 1.0 = public and accessible
- 0.5 = metadata public but product access unclear
- 0.0 = proprietary, restricted, or unavailable

### asset_availability

Measures whether an agent can show or link something useful now.

- high: thumbnail/preview/image available
- medium: raw product only, render possible
- low: product exists but no accessible preview/render path

### preview_quality

Measures whether a preview is visually useful for non-expert exploration.

Initial implementation can use heuristics:

- explicit preview URL exists
- image dimensions adequate
- source is known to provide public-friendly assets
- curated seed override exists

Do not over-engineer CV scoring in V1.

### science_ready_level

Measures whether the product is raw, calibrated, science-ready, high-level, or generated from a survey image service.

Prefer science-ready/high-level/pre-rendered products for agents.

### provenance_quality

Measures source traceability.

High score requires:

- archive/source name
- facility/instrument
- source record URL or ID
- observation/product ID
- retrieval time

### citation_quality

High score requires:

- citation URL
- credit text or policy reference
- source title/record title where possible

### renderability

High score when AstroLens can reliably produce/use an image asset.

Low score for huge or complex FITS cubes/spectra in V1.

### source_reliability

Uses connector health and recent success/failure history.

Do not permanently bury a source because of transient downtime; only affect live refresh and default ranking mildly.

### wavelength_diversity_bonus

When the user asks for multiple bands, boost candidates that fill missing bands.

Do not return six optical images if the request asks for visible, infrared, X-ray, and radio and good non-optical candidates exist.

### caveat_penalty

Penalize results that are likely misleading without heavy caveats:

- unclear object match
- false-color/highly processed asset without enough metadata
- rights/reuse unknown
- very old/stale source cache when freshness matters
- non-image product being used as a visual view

## Ranking behavior

Default `get_best_views` behavior:

- return 3–6 views if available
- prioritize wavelength diversity
- include scores only in debug mode
- include `why_selected` when useful
- include caveats and citations always

Debug behavior:

- expose component scores
- expose candidate rejection reasons
- expose source health/cache information

## Cross-source visual-source-quality ranking

When a live evidence request fans out to more than one source (currently MAST +
SkyView), the resulting views must be merged into a single list that decides
*which images should be used*. This is handled by
`rank_views_by_source_quality` in `services/ranking.py` and applied in
`services/live_sources.py` before truncation.

It ranks each candidate `View` by a deterministic visual-source-quality ladder
(best first), derived from the asset's `visual_tier` and shape:

1. `outreach_release` — public outreach/press images.
2. `processed_archive` — HLA/HLSP/HAP color composites and calibrated archive products.
3. rendered **composite** — SDSS RGB / multi-band `astrolens_rendered` assets
   (assets built from two or more aligned source products). These outrank raw
   archive previews.
4. `raw_archive_preview` — convenience MAST previews.
5. rendered **single-survey** — one-band `astrolens_rendered` SkyView cutouts,
   the fallback tier used only when better visuals are unavailable.
6. views with no usable asset rank last.

The ladder bands dominate. Bounded in-band refinements (target-validation status,
`preview_quality`, and `overall`) only reorder views *inside* a band, and a mild
tie-break prefers MAST over SkyView, then a stable label. Selection is
wavelength-diversity-first: the single best view always leads, then remaining
slots prefer the best not-yet-seen band before filling with the next best.
Ranking reads each view's provenance/tier metadata and never mutates it.

## Human-curated seed set

Start with 50–100 famous objects and manually approve best views. Use these as:

- golden tests
- fallback demo data
- ranking calibration set
- regression suite

Manual curation is acceptable in V1. It is not a failure; it is how the ranking moat starts.

## Rejection reasons

A rejected candidate should have one or more reasons in debug/admin mode:

- `LOW_OBJECT_MATCH`
- `NOT_PUBLIC`
- `NO_ASSET_OR_RENDER_PATH`
- `LOW_PROVENANCE`
- `DUPLICATE_WAVELENGTH`
- `UNSUPPORTED_PRODUCT_TYPE`
- `RIGHTS_UNKNOWN`
- `SOURCE_UNHEALTHY`

## Tests

Ranking tests must cover:

- object-match beats pretty but wrong images
- public-access beats restricted products
- wavelength diversity beats duplicate views
- provenance is required for top-ranked views
- curated overrides work
- score output is deterministic
- missing optional fields do not crash ranking

## Anti-patterns

Do not:

- rank by visual beauty alone
- return many near-duplicate products
- hide score/caveat reasons from debug mode
- let an unavailable source produce a hard failure when cached data exists
- include unsupported products as views without explicit caveats

## Done criteria

A ranking change is done only when:

- golden object tests still pass
- score components are documented
- new heuristics have tests
- output remains schema-compatible
- rejected-candidate behavior is tested when relevant
