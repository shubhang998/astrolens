from fastapi.testclient import TestClient

from astrolens.api.main import app

client = TestClient(app)


def test_root_redirects_browser_users_to_docs() -> None:
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/docs"
