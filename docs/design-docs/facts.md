# Facts Compiler Design

## Purpose

Turn catalog measurements into layered, cited, deterministic facts that agents
can quote without hallucination risk. The compiler answers "how far, how big,
how bright, how old" — the questions curious users, teachers, and students ask
first.

## Hard rule

Every numeric public fact must be traceable to a named catalog field or a
deterministic function of catalog fields. `Fact.source_fields` names the
SIMBAD columns; `Fact.derivation` names the function (None = direct catalog
value). LLM-authored numeric or scientific claims are forbidden anywhere in
AstroLens (see AGENTS.md).

## Pipeline

1. Resolve the object (curated repository first, then CDS Sesame).
2. `SimbadTapConnector.fetch_measurements(canonical_name)` returns
   `SimbadMeasurements` with per-measurement bibcodes.
3. `FactsCompilerService.compile` emits facts in three layers.
4. Facts attach to `EvidenceBundle.object_facts` (with `fact_citations`), the
   REST route `GET /v1/objects/{id}/facts`, and the `explain_object` /
   `show_object` MCP tools. Failures always degrade to warnings, never failed
   bundles.

## Fact layers and confidence semantics

| Layer | Example | Confidence |
|---|---|---|
| Direct catalog value with bibcode | redshift, angular size, morphology | 0.9 |
| Direct catalog value without bibcode | otype classification, V magnitude | 0.8 |
| One-step derivation | parallax→distance, z→lookback time | 0.7 |
| Two-step derivation | angular size + distance → physical size | 0.6 |

## Derivation catalog (`src/astrolens/services/facts.py`)

- `distance_pc_from_parallax(plx_mas)` = 1000 / parallax; **gated**: skipped
  with a `FACTS_PARALLAX_UNCERTAIN` warning when relative error > 20%.
- `lookback_time_gyr(z)` and `luminosity_distance_mpc(z)` via
  `astropy.cosmology.Planck18`; **gated**: redshift is used only when
  `rvz_type == 'z'` or z > 0.003, otherwise the radial velocity is reported as
  kinematic and no cosmological derivation is emitted.
- `physical_size_kly(angular_arcmin, distance_ly)` — small-angle formula.
- `naked_eye_visible(v_mag)` — V ≤ 6.0.
- `scale_comparison_for(kind, value, unit)` — deterministic anchor table
  (full-Moon widths, Milky Way diameters, age of the Earth). Arithmetic only.

## Citations

Every fact carries the SIMBAD TAP citation plus `citation:bibcode:{bibcode}`
(ADS URL) when SIMBAD provides a measurement reference. `fact_citations` on
the bundle contains every citation id referenced by any fact.

## Narrative fields

`show_object`/`explain_object` build `headline` and `why_interesting` by
concatenating fact claims and scale comparisons via fixed templates in
`services/showcase.py`. They contain no numbers that are not in a `Fact`.

## Tests

`tests/unit/test_facts_compiler.py` pins golden numerics (M87 z=0.00428 →
lookback ≈ 0.0617 Gyr; Vega parallax 130.23 mas → 7.68 pc), the gates, and the
invariant that every fact is cited and traceable.
