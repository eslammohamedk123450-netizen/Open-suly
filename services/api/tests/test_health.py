from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_returns_liveness_without_credentials() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "suly-api",
        "version": "0.1.0",
    }
