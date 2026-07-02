# Hero Tools Eval

Scripted checks for the two-job hero surface (`show_object`, `explain_object`,
`find_objects`). Run against a live server with the `skyview` extra installed
and network access; each check lists the JSON-RPC call and pass criteria.

## 1. show_object returns a cross-source composite for an AGN

Call: `tools/call show_object {"object": "M87"}`

Pass when:

- `hero_view.band_family == "multiwavelength"` (or a warning
  `COMPOSITE_UNAVAILABLE` explains why the best single view was used instead)
- `panels` contains at most 4 views, no two sharing a band family
- every view listed in `credits` has a non-empty `credit_line`
- `object_facts` includes a `redshift` fact and a `lookback_time` fact whose
  `derivation` is `astropy.cosmology.Planck18.lookback_time(z)`
- `headline` text appears verbatim in one of the fact claims or is composed
  of fact claims plus scale comparisons (no novel numbers)

## 2. explain_object compiles cited measurements

Call: `tools/call explain_object {"object": "Vega"}`

Pass when:

- a `distance` fact exists with `derivation == "distance_pc = 1000 / parallax_mas"`
- every fact has non-empty `source_fields` and `citation_ids`
- an `apparent_magnitude` fact carries the naked-eye scale comparison
- the response contains no image views (fast path)

## 3. Saturn uses target-name search, never a cone

Call: `tools/call show_object {"object": "Saturn"}`

Pass when:

- warnings include `EPHEMERIS_TARGET_NAME_SEARCH`
- no SkyView-rendered views are present; if SkyView was requested the
  `EPHEMERIS_SKYVIEW_EXCLUDED` warning explains why
- any observations returned are real HST/JWST rows whose `target_name`
  matches SATURN (spot-check raw links)

## 4. Random quasar sampling varies

Call twice: `tools/call find_objects {"category": "quasar", "random_sample": true, "limit": 5}`

Pass when:

- both calls return 1–5 hits with valid coordinates
- the two hit sets differ (or a "non-random" warning explains the fallback)
- each hit includes a `followup` string invoking `show_object`

## 5. Unknown category teaches

Call: `tools/call find_objects {"category": "wormhole"}`

Pass when the error is `-32602` with `error.data.code == "VALIDATION_ERROR"`
and `supported_categories` listing the curated vocabulary.

## 6. Regression: existing evidence shape unchanged

Call: `tools/call get_object_evidence {"object": "M87", "live": true}`

Pass when the response shape matches the pre-hero contract (no composite view
unless requested, no `object_facts` unless `include_facts` is set by the
caller path — the REST/MCP default remains off).
