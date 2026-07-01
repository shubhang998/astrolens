# MCP Production Hardening Evals

Use these questions after changes to live connectors, MCP tools, or response
assembly. The goal is to catch agent-facing regressions without requiring live
archive calls in unit tests.

## Response Size

1. Ask `get_object_evidence` for M87 with `live=true`, `sources=["mast"]`, and
   `max_views=99`.
   - Expected: the MCP schema advertises `max_views <= 6`, the dispatcher clamps
     the request, and `structuredContent` uses compact raw metadata.
2. Ask `search` with `limit=1000`.
   - Expected: the MCP schema advertises `limit <= 10`, and no more than 10
     results are returned.
3. Inspect a live evidence response that includes source products.
   - Expected: `raw_metadata` keeps stable source fields such as product filename,
     data URI, filters, project, and survey, while bulky source-only fields are
     omitted.

## Error Mapping

4. Simulate a source timeout from MAST or SkyView.
   - Expected: REST returns the standard `APIError` envelope with
     `SOURCE_TIMEOUT`; MCP returns a JSON-RPC error with `data.code =
     "SOURCE_TIMEOUT"` and no traceback.
5. Simulate an HTTP 429 from a live source.
   - Expected: connector code maps it to `RATE_LIMITED` and marks it retryable.
6. Pass an unsupported band such as `microwave`.
   - Expected: MCP returns an invalid-params JSON-RPC error with
     `UNSUPPORTED_BAND`.

## Schema Stability

7. Compare `/openapi.json` before and after the change.
   - Expected: public REST response model names remain present; successful
     response fields are additive or unchanged.
8. Call `tools/list`.
   - Expected: read-only annotations remain present, no write/non-goal tools are
     added, and input schemas include explicit bounds for list-producing tools.

## Connector Safety

9. Pass arbitrary strings or URLs in `skyview_surveys`.
   - Expected: unknown surveys are ignored; the connector returns the existing
     "no supported surveys matched" warning and does not call the SkyView client.
10. Inspect facts, assets, raw links, and views in returned payloads.
    - Expected: citations/reuse/provenance remain present, and no endpoint or
      MCP tool generates lessons, scripts, social posts, or creator packs.
