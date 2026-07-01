from fastapi.testclient import TestClient

from astrolens.api.main import app

client = TestClient(app)


def test_openapi_exposes_milestone_1_paths_and_core_schemas() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    payload = response.json()

    assert "/v1/health" in payload["paths"]
    assert "/v1/sources/health" in payload["paths"]
    assert "/v1/render/fits-plan" in payload["paths"]

    schemas = payload["components"]["schemas"]
    for schema_name in [
        "CelestialObject",
        "ObjectAlias",
        "Observation",
        "DataProduct",
        "View",
        "Asset",
        "Fact",
        "TargetValidation",
        "ImageProvenance",
        "Citation",
        "ReusePolicy",
        "EvidenceBundle",
        "SourceHealthResponse",
        "APIError",
    ]:
        assert schema_name in schemas


def test_openapi_does_not_expose_non_goal_endpoints() -> None:
    payload = client.get("/openapi.json").json()
    paths = set(payload["paths"])

    prohibited_fragments = [
        "lesson",
        "teacher",
        "creator",
        "script",
        "social",
        "narration",
        "article",
    ]
    for path in paths:
        assert not any(fragment in path for fragment in prohibited_fragments)
