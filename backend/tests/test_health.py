"""API tests for GET /health."""
from __future__ import annotations

from app.dependencies import get_storage_service


def test_health_ok(client, mock_storage):
    mock_storage._client.bucket_exists = lambda _: True
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "ok"
    assert data["storage"] == "ok"


def test_health_degraded_storage(client):
    client.app.dependency_overrides[get_storage_service] = lambda: None
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["storage"] == "unreachable"
