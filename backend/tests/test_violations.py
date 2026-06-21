"""API tests for GET /violations endpoints."""
from __future__ import annotations

import pytest


def test_list_violations_empty(client):
    response = client.get("/violations")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 0
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert data["results"] == []


@pytest.mark.asyncio
async def test_list_violations_pagination(client, seed_violations):
    response = client.get("/violations?page=1&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 5
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert len(data["results"]) == 2


@pytest.mark.asyncio
async def test_list_violations_filter_type(client, seed_violations):
    response = client.get("/violations?violation_type=HELMET_NON_COMPLIANCE")
    assert response.status_code == 200
    for row in response.json()["results"]:
        assert row["violation_type"] == "HELMET_NON_COMPLIANCE"


@pytest.mark.asyncio
async def test_get_violation_by_id(client, seed_violations):
    response = client.get("/violations/b47ac10b-58cc-4372-a567-0e02b2c3d481")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "b47ac10b-58cc-4372-a567-0e02b2c3d481"
    assert "annotated_image_url" in data


def test_get_violation_not_found(client):
    response = client.get("/violations/nonexistent-id")
    assert response.status_code == 404
