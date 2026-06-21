"""API tests for GET /analytics."""
from __future__ import annotations

import pytest


def test_analytics_empty(client):
    response = client.get("/analytics")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["by_type"] == {}
    assert "window_start" in data
    assert "window_end" in data
    assert "cached" in data


@pytest.mark.asyncio
async def test_analytics_with_data(client, seed_violations):
    response = client.get("/analytics")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 5
    assert data["by_type"].get("HELMET_NON_COMPLIANCE", 0) >= 5


@pytest.mark.asyncio
async def test_analytics_caching_and_by_date(client, seed_violations):
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    start_str = (now - timedelta(days=1)).isoformat()
    end_str = (now + timedelta(days=1)).isoformat()
    params = {"start_date": start_str, "end_date": end_str}

    response1 = client.get("/analytics", params=params)
    assert response1.status_code == 200
    data1 = response1.json()
    assert data1["cached"] is False
    assert len(data1["by_date"]) > 0

    response2 = client.get("/analytics", params=params)
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["cached"] is True
    assert data2["total"] == data1["total"]
    assert data2["by_type"] == data1["by_type"]
    assert data2["by_date"] == data1["by_date"]

