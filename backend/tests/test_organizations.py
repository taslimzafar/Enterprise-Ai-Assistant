import pytest
import uuid
from httpx import AsyncClient
from app.core.config import settings

async def create_user(async_client: AsyncClient, email: str, password: str = "password123"):
    response = await async_client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"email": email, "password": password, "full_name": "Test User"}
    )
    assert response.status_code == 200
    return response.json()

async def get_token(async_client: AsyncClient, email: str, password: str = "password123"):
    response = await async_client.post(
        f"{settings.API_V1_STR}/auth/login",
        data={"username": email, "password": password}
    )
    return response.json()["access_token"]

async def test_organization_crud_and_rbac(async_client: AsyncClient):
    owner_email = f"owner_{uuid.uuid4().hex[:8]}@example.com"
    member_email = f"member_{uuid.uuid4().hex[:8]}@example.com"
    other_email = f"other_{uuid.uuid4().hex[:8]}@example.com"
    
    # Register users
    await create_user(async_client, owner_email)
    await create_user(async_client, member_email)
    await create_user(async_client, other_email)
    
    owner_token = await get_token(async_client, owner_email)
    member_token = await get_token(async_client, member_email)
    other_token = await get_token(async_client, other_email)
    
    # Get owner's default org
    response = await async_client.get(
        f"{settings.API_V1_STR}/organizations/",
        headers={"Authorization": f"Bearer {owner_token}"}
    )
    assert response.status_code == 200
    orgs = response.json()
    assert len(orgs) == 1
    org_id = orgs[0]["id"]
    
    # Get member's id
    response = await async_client.get(f"{settings.API_V1_STR}/auth/me", headers={"Authorization": f"Bearer {member_token}"})
    member_id = response.json()["id"]
    
    # 1. Owner adds member by email
    response = await async_client.post(
        f"{settings.API_V1_STR}/organizations/{org_id}/members",
        json={"email": member_email, "role": "MEMBER"},
        headers={"Authorization": f"Bearer {owner_token}"}
    )
    assert response.status_code == 200
    
    # 2. Member tries to add someone else (should fail, only OWNER/ADMIN can)
    response = await async_client.get(f"{settings.API_V1_STR}/auth/me", headers={"Authorization": f"Bearer {other_token}"})
    other_id = response.json()["id"]
    
    response = await async_client.post(
        f"{settings.API_V1_STR}/organizations/{org_id}/members",
        json={"email": other_email, "role": "MEMBER"},
        headers={"Authorization": f"Bearer {member_token}"}
    )
    assert response.status_code == 403
    
    # 3. Other tries to access org (should fail, not a member)
    response = await async_client.post(
        f"{settings.API_V1_STR}/organizations/{org_id}/members",
        json={"email": other_email, "role": "MEMBER"},
        headers={"Authorization": f"Bearer {other_token}"}
    )
    assert response.status_code == 403
    
    # 4. Owner removes member
    response = await async_client.delete(
        f"{settings.API_V1_STR}/organizations/{org_id}/members/{member_id}",
        headers={"Authorization": f"Bearer {owner_token}"}
    )
    assert response.status_code == 200
