# Rendering Design

## Purpose

Rendering converts supported astronomy products into usable preview/public assets for agents and apps. Rendering is not the core of V1. AstroLens should prefer existing public previews and only render when useful, supported, and safe.

## V1 rendering stance

- Prefer existing archive previews/public image assets.
- Render FITS to PNG only for simple supported image products.
- Treat rendering as asynchronous unless the asset is already cached.
- Do not support complex cubes/spectra/alignment pipelines in V1.
- Never present AstroLens-rendered images as official NASA/ESA/CSA/STScI press images.

## Supported V1 outputs

- thumbnail PNG/JPEG
- standard 1920x1080 PNG
- square 1080x1080 PNG if easy crop/pad works
- asset metadata JSON
- optional credit-overlay variant later

## Asset metadata requirements

Every asset must include:

- `asset_id`
- `source_product_ids`
- `format`
- `width`
- `height`
- `asset_url`
- `thumbnail_url`
- `false_color` or `unknown`
- `processing_note`
- `credit_text`
- `reuse_policy_id`
- `citations`
- `created_at`

Example:

```json
{
  "asset_id": "asset:m87:hubble:visible:1080p",
  "source_product_ids": ["product:mast:hst:..."],
  "format": "png",
  "width": 1920,
  "height": 1080,
  "false_color": true,
  "processing_note": "Generated from public archive data by AstroLens.",
  "credit_text": "NASA/ESA/STScI...",
  "reuse_policy_id": "reuse:nasa:general"
}
```

## Render endpoint behavior

`POST /v1/render` should:

1. Validate product ID.
2. Check if requested asset already exists.
3. Return cached asset immediately when available.
4. If not cached and supported, enqueue a render job.
5. Return `job_id` and polling URL.
6. If unsupported, return `RENDER_NOT_SUPPORTED` with a useful reason.

Do not block user-facing requests on slow rendering.

## Render job lifecycle

Statuses:

- `queued`
- `running`
- `succeeded`
- `failed`
- `unsupported`

Render job output:

- asset metadata on success
- structured error on failure
- source product provenance always

## FITS rendering rules

Use `astropy.io.fits` for FITS reading.

V1 supports only simple 2D image HDUs where:

- dimensions are manageable
- data array is numeric
- product has enough metadata for provenance
- memory usage remains bounded

V1 should reject or defer:

- complex data cubes
- spectra
- event lists
- enormous files
- products requiring advanced calibration
- products with unclear rights/reuse metadata

## Image processing rules

- Use deterministic scaling/stretch settings.
- Store stretch metadata.
- Preserve source provenance.
- Include false-color caveat when applicable or unknown.
- Avoid subjective enhancements that cannot be described.
- Avoid overwriting source assets.

## Caveats

Each rendered astronomy image should include relevant caveats:

- Colors may be mapped from wavelengths/filters, not natural human vision.
- Different telescopes and bands have different resolution.
- Images from different wavelengths may not be simultaneous.
- Processing choices affect visual appearance.
- A non-detection does not prove an object emits nothing in that band.

## Storage

Use object storage/CDN for assets. Store metadata in Postgres.

Do not store huge raw source files unless explicitly justified. Prefer source links and cached derivatives.

## Security

Rendering must not:

- fetch arbitrary user-provided URLs
- execute shell commands based on metadata
- write outside configured asset directories/buckets
- allow path traversal
- expose private source URLs/secrets

## Tests

Tests must cover:

- cached asset returned immediately
- supported FITS fixture renders successfully
- unsupported product returns typed error
- huge product is rejected before memory blowup
- asset metadata includes provenance/citations/reuse
- no live archive calls in unit tests

## Done criteria

A rendering change is done only when:

- render tests pass
- memory limits are respected
- unsupported formats fail safely
- asset metadata is complete
- citations/reuse/caveats are present
- public API behavior remains async for new renders
