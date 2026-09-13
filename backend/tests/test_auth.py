import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
import uuid
from app.core.config import settings

# Use a random email so the test can be run multiple times
test_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
test_password = "password123"

async def test_signup(async_client):
    response = await async_client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"email": test_email, "password": test_password}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == test_email
    assert "id" in data

async def test_login(async_client):
    response = await async_client.post(
        f"{settings.API_V1_STR}/auth/login",
        data={"username": test_email, "password": test_password}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    return data["access_token"]

async def test_me(async_client):
    token = await test_login(async_client)
    response = await async_client.get(
        f"{settings.API_V1_STR}/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == test_email

async def test_organizations(async_client):
    token = await test_login(async_client)
    response = await async_client.get(
        f"{settings.API_V1_STR}/organizations/",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["name"] == f"{test_email.split('@')[0]}'s Organization"
