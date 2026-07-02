# Rendering Design

## Purpose

Rendering converts supported astronomy products into usable preview/public assets for agents and apps. Rendering is not the core of V1. AstroLens should prefer existing public previews and only render when useful, supported, and safe.

## V1 rendering stance

- Prefer existing archive previews/public image assets.
- Render FITS to PNG only for simple supported image products.
- Treat rendering as asynchronous unless the asset is already cached.
- Do not support complex cubes/spectra/alignment pipelines in V1.
- Never present AstroLens-rendered images as official NASA/ESA/CSA/STScI press images.

## Visual mode presets

Live generated visual evidence supports three bounded field-of-view modes:

| Mode | MAST radius | SkyView radius | SkyView pixels | Intended use |
|---|---:|---:|---:|---|
| `detail` | 0.01 deg | 0.03 deg | 1024 | compact targets and close-up structure |
| `context` | 0.03 deg | 0.08 deg | 1024 | balanced default; preserves earlier SkyView behavior |
| `wide` | 0.08 deg | 0.20 deg | 1536 | extended objects and surrounding sky context |

Explicit `radius_deg` and `pixels` request values override these presets. The
mode should be preserved in request/product metadata so agents can explain the
field-of-view choice without implying scientific completeness.

## HiPS / Tiled Map Plan

HiPS and tiled-map support is a later rendering capability, not part of the
current FITS preview path. The next design slice should define a read-only tile
plan response that includes survey identity, tile service provenance, reuse
metadata, coordinate frame, field-of-view bounds, and citations. It should not
fetch arbitrary tile URLs supplied by users, and it should not replace the
current `detail`/`context`/`wide` presets until tests cover tile provenance and
bounded source selection.

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

## Single-band false-color tints

Single-product renders are no longer plain grayscale outside the visible
band: intensity maps through an observatory-conventional black -> hue ->
white duotone (`tint_for_wavelength`): X-ray blue-violet, radio orange-red,
infrared amber, ultraviolet violet, gamma magenta, millimeter teal. Visible
single filters stay neutral (grayscale is the honest choice there). The tint
is a deterministic lookup by wavelength, is recorded as a recipe caveat
("brightness is real data, hue is presentational"), and never feeds the
color-separation boost used by multi-band composites.

## Cross-source composites and band recipes

`services/composites.py` builds one multi-wavelength composite per object by
mixing FITS products from different archives (e.g. SkyView radio + MAST
visible). Behavior:

- Band recipes are keyed by object type (`recipe_for_object_type`): AGN →
  radio+X-ray+visible; supernova remnants → X-ray+radio+visible; star-forming
  regions → infrared+visible; default → visible.
- Channel picks take the highest-ranked view per band that carries an eligible
  FITS product, from any archive. Fewer than two channels → no composite
  (callers fall back to the best single view with a warning).
- The renderer is invoked with `FitsRenderRequest.preselected=True`, which
  skips visit-fingerprint grouping and maps channels purely by wavelength
  (shortest→blue, longest→red). Reprojection, the ≥5% overlap gate, and
  `fallback_single_channel` behavior are unchanged.
- Pixel-scale quality gate: if channel pixel scales differ by more than 4x
  (`pixel_scale_ratio`), a resolution-mismatch caveat is appended — never
  refuse, always caveat.
- Composite views are `band_family=multiwavelength`, tier
  `astrolens_rendered`, `false_color=true`, with per-channel provenance notes
  ("red: NVSS (SkyView)"), the union of contributing citations, and a
  mandatory false-color caveat plus the recipe rationale.
- Composites are opt-in (`composite=true` on the live-sources service; the
  `show_object` MCP tool enables it) so existing responses are unchanged.

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

FITS download URLs are validated before any fetch: only `https` URLs whose
host matches a trusted archive suffix (`stsci.edu`, `gsfc.nasa.gov` by
default) are downloaded. Deployments can extend the allowlist with the
`ASTROLENS_RENDER_URL_ALLOWLIST` environment variable (comma-separated host
suffixes). `file://` URLs are rejected except when a renderer is constructed
with `allow_file_urls=True` (tests only). Failed or unsupported renders never
report an `asset_url`, and local cache paths are never serialized into public
responses. Render execution runs in worker threads (`asyncio.to_thread`) so
downloads and pixel work never block the API event loop.

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
