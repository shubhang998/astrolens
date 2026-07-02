# Source Connectors Design

## Purpose

Connectors isolate AstroLens from archive-specific APIs, protocols, schemas, formats, rate limits, and failure modes. They return normalized candidates while preserving raw source metadata for provenance/debugging.

## V1 sources

Implement these first:

- SIMBAD: object identity, aliases, coordinates, object types.
- NED: extragalactic identity, aliases, redshifts, galaxy context.
- MAST: Hubble, JWST, TESS, Kepler, GALEX, and related products.
- IRSA: infrared/all-sky products, WISE, Spitzer, 2MASS, ZTF-related products.
- SkyView: fast multi-wavelength generated images/previews.
- HEASARC: high-energy datasets and catalogs.
- ADS: literature/citation context.

Add later:

- Gaia
- NASA Exoplanet Archive
- SDSS
- DESI
- NOIRLab / Legacy Surveys
- ALMA
- NRAO
- ZTF-specific workflows
- Rubin public/rights-aware products

## Connector interface

Every connector should implement the common protocol.

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

    async def list_products(self, observation_id: str) -> list[ProductCandidate]:
        ...

    async def get_citation(self, source_record_id: str) -> Citation:
        ...
```

Implement only methods meaningful for a source. Unsupported methods should fail with a typed `UnsupportedConnectorOperation` error, not generic exceptions.

## Rules

Connectors must:

- Use source-specific timeouts.
- Use bounded retries with exponential backoff where safe.
- Map timeouts, rate limits, access denials, malformed source responses, and
  source outages to typed `AstroLensError` codes.
- Use circuit breakers/source health where repeated failures occur.
- Normalize output into domain candidate models.
- Preserve raw source metadata under `raw_metadata`.
- Include source URL, source record ID, and retrieval time when available.
- Be covered by fixture-based tests.

Connectors must not:

- Write directly to the database.
- Return untyped arbitrary dicts as their primary output.
- Call other connectors directly.
- Fetch arbitrary URLs supplied by users.
- Hide source errors as empty success responses.
- Make live network calls in unit tests.

## Normalized candidate types

### ResolvedObjectCandidate

Required fields:

- `name`
- `aliases`
- `object_type`
- `ra_deg`
- `dec_deg`
- `frame`
- `source`
- `source_url`
- `confidence`
- `raw_metadata`

### ObservationCandidate

Required fields:

- `source_archive`
- `facility`
- `instrument`
- `band_family`
- `observation_date` when available
- `access_status`
- `source_record_id`
- `source_url`
- `region` or footprint when available
- `raw_metadata`

### ProductCandidate

Required fields:

- `product_type`
- `file_format`
- `download_url` or source-access descriptor
- `preview_url` when available
- `calibration_level` when available
- `file_size_mb` when available
- `source_record_id`
- `raw_metadata`

## Source-specific guidance

### SIMBAD

Use for canonical identity and aliases. Prefer it for Galactic stars/nebulae and general object cross-identifications. Treat ambiguous names carefully.

### NED

Use for extragalactic objects, galaxies, quasars, redshifts, and aliases. Prefer the newer NED APIs rather than deprecated legacy endpoints.

### MAST

Use for public Hubble/JWST and related archive products. Store archive/source IDs exactly. Distinguish raw, calibrated, high-level science products, previews, and downloadable products.

### IRSA

Use for infrared and all-sky survey data. Normalize survey names and band families carefully. IRSA can return many catalog/survey products; do not rank everything highly by default.

### SkyView

Use for fast generated image views when direct archive products are too heavy or unavailable. Mark SkyView assets as generated from survey data, not as official press images.

Current implementation:

- Dependency: optional `astrolens[skyview]`, backed by `astroquery.skyview`.
- Query style: AstroLens resolves the object first, then sends numeric ICRS coordinates to SkyView.
- Default surveys: SDSSg/r/i for visible RGB where available, 2MASS-J/H/K for infrared RGB, GALEX Near UV, RASS-Cnt Broad, VLA FIRST, Planck 217 I (millimeter), and Fermi 5 (gamma).
- Fallback/custom surveys: DSS2 Blue/Red/IR, NVSS, WISE 3.4/12/22, IRIS 100, Planck 353 I, and H-Alpha Comp remain supported when users need wider coverage.
- Visual modes: `detail`, `context`, and `wide` select bounded radius/pixel presets before SkyView is called; explicit radius/pixel inputs override the preset.
- Product shape: HTTPS generated FITS URLs with survey name, band family, source record ID, and raw metadata.
- Asset shape: AstroLens-rendered PNG previews or RGB composites from those FITS files, with rendering caveats.
- Custom survey input is bounded to AstroLens-known `SURVEY_SPECS`; arbitrary
  unknown survey names or URL-like strings must not be passed through to the
  SkyView client.

Do not let users pass arbitrary FITS URLs through this connector. The connector should only use bounded survey names and generated URLs returned by SkyView.

### SIMBAD TAP (implemented)

Use for object measurements and category/region search. The connector
(`src/astrolens/connectors/simbad_tap.py`) POSTs ADQL to the fixed sync TAP
endpoint (`https://simbad.cds.unistra.fr/simbad/sim-tap/sync`, `format=json`)
and is pinned to the stable `basic`/`ident`/`otypes`/`allfluxes` tables.

Identity handoff rule: `fetch_measurements` takes the canonical name that CDS
Sesame returned (e.g. `"M  87"`) because SIMBAD `ident.id` matching is
string-exact; one whitespace-collapsed retry covers spacing drift. Never fuzzy
match identity inside this connector.

Measurements query (columns parsed by metadata name, never position):

```sql
SELECT b.main_id, b.otype, b.ra, b.dec,
       b.plx_value, b.plx_err, b.plx_bibcode,
       b.rvz_redshift, b.rvz_radvel, b.rvz_type, b.rvz_bibcode,
       b.morph_type, b.morph_bibcode,
       b.galdim_majaxis, b.galdim_minaxis, b.galdim_bibcode,
       b.sp_type, b.sp_bibcode, b.nbref,
       f.V, f.B, f.K
FROM basic AS b
JOIN ident AS i ON i.oidref = b.oid
LEFT JOIN allfluxes AS f ON f.oidref = b.oid
WHERE i.id = 'M  87'
```

Category search joins `otypes` (hierarchical: 'G' matches Seyferts), supports
an optional `CONTAINS(POINT..., CIRCLE...)` cone and V-magnitude limit, and
clamps `TOP` to 20. Random sampling is server-side and portable:
`MOD(b.oid, m) = r` with a seedable residue; if a sampled page returns too few
rows the modulus halves and re-queries, and the final unsampled fallback is
flagged with a "non-random" warning.

Categories come from the curated `CATEGORY_OTYPES` map (quasar, galaxy,
supernova-remnant, star-forming-region, planetary-nebula, pulsar, ...);
unknown categories raise `VALIDATION_ERROR` listing supported values. ADQL
string literals are escaped (quotes doubled, control characters rejected).

### Moving targets (MAST target-name search)

Solar-system bodies are flagged `ephemeris_object=true` and their stored
coordinates are placeholders. Live evidence for them must use
`MastConnector.search_public_images_by_target_name` (service
`Mast.Caom.Filtered`, upper-cased `target_name` filter) — never a coordinate
cone search. SkyView is excluded for these targets with a teaching warning.

### HEASARC / Chandra

Use for X-ray/high-energy evidence. X-ray views need strong caveats: false color, energy bands, resolution differences, and non-simultaneity.

### ADS

Use for paper/citation context. ADS should support provenance and bibliography, not be used to generate claims blindly.

## Fixture policy

Each connector must include fixtures for:

- successful response
- empty response
- ambiguous response when applicable
- source timeout/failure
- malformed source response

Fixtures must be scrubbed of secrets and stored in `tests/fixtures/{source}/`.

## Tests

Minimum tests per connector:

- parses fixture into normalized candidates
- handles missing optional fields
- maps source errors to typed connector errors
- does not perform live network calls in unit tests
- preserves raw metadata
- attaches source URL/source record ID when available

## Done criteria for a connector

- Healthcheck implemented.
- Fixture tests pass.
- Timeout/retry behavior configured.
- Normalized candidates returned.
- Raw metadata preserved.
- Source docs referenced in connector module docstring or design notes.
