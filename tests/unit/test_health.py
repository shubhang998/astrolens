from fastapi.testclient import TestClient

from astrolens.api.main import app

client = TestClient(app)


def test_health_returns_exact_milestone_contract() -> None:
    response = client.get("/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "cache_warmer": None}


def test_sources_health_returns_configured_connector_shells() -> None:
    response = client.get("/v1/sources/health")

    assert response.status_code == 200
    payload = response.json()
    assert {source["name"] for source in payload["sources"]} >= {"SIMBAD", "NED", "MAST", "IRSA"}
    assert payload["meta"]["request_id"].startswith("req_")
    assert payload["meta"]["cache"]["status"] == "hit"
    assert payload["meta"]["cache"]["stale"] is False
