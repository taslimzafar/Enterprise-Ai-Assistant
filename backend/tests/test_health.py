import pytest
from fastapi.testclient import TestClient

from app.core.config import settings

async def test_health_check(async_client):
    response = await async_client.get(f"{settings.API_V1_STR}/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "service" in data

async def test_ready_check(async_client):
    response = await async_client.get(f"{settings.API_V1_STR}/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
