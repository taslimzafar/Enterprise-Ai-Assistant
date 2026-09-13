from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.api.dependencies import get_db, get_current_active_user
from app.db.models.user import User
from app.db.models.organization import Organization
from app.db.models.membership import Membership, RoleEnum
from app.schemas.organization import Organization as OrganizationSchema, OrganizationCreate
from pydantic import BaseModel
import uuid

class MemberCreate(BaseModel):
    user_id: str | None = None
    email: str | None = None
    role: RoleEnum

router = APIRouter()

@router.get("/", response_model=List[OrganizationSchema])
async def read_organizations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retrieve organizations that the current user belongs to.
    """
    result = await db.execute(
        select(Organization)
        .join(Membership)
        .filter(Membership.user_id == current_user.id)
    )
    organizations = result.scalars().all()
    return organizations

@router.post("/", response_model=OrganizationSchema)
async def create_organization(
    org_in: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Create a new organization and make the user its OWNER.
    """
    org_slug = f"{org_in.name.lower().replace(' ', '-')}-{str(uuid.uuid4())[:8]}"
    if org_in.slug:
        org_slug = org_in.slug
        
    org = Organization(name=org_in.name, slug=org_slug)
    db.add(org)
    await db.flush()
    
    membership = Membership(
        user_id=current_user.id,
        organization_id=org.id,
        role=RoleEnum.OWNER
    )
    db.add(membership)
    await db.commit()
    await db.refresh(org)
    
    return org

from app.api.dependencies import RoleChecker

@router.get("/{org_id}/members")
async def get_members(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    membership: Membership = Depends(RoleChecker([RoleEnum.OWNER, RoleEnum.ADMIN, RoleEnum.MANAGER, RoleEnum.MEMBER]))
):
    result = await db.execute(
        select(Membership, User.email, User.full_name)
        .join(User, User.id == Membership.user_id)
        .filter(Membership.organization_id == org_id)
    )
    
    members = []
    for mem, email, full_name in result.all():
        members.append({
            "id": mem.id,
            "user_id": mem.user_id,
            "role": mem.role,
            "email": email,
            "full_name": full_name,
            "created_at": mem.created_at
        })
    return members

@router.post("/{org_id}/members")
async def add_member(
    org_id: str,
    member_in: MemberCreate,
    db: AsyncSession = Depends(get_db),
    membership: Membership = Depends(RoleChecker([RoleEnum.OWNER, RoleEnum.ADMIN]))
):
    if not member_in.user_id and not member_in.email:
        raise HTTPException(status_code=400, detail="Must provide either user_id or email")
        
    target_user_id = member_in.user_id
    if member_in.email:
        result = await db.execute(select(User).filter(User.email == member_in.email))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        target_user_id = user.id
    elif member_in.user_id:
        result = await db.execute(select(User).filter(User.id == member_in.user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

    # Check if user is already a member
    result = await db.execute(select(Membership).filter(Membership.user_id == target_user_id, Membership.organization_id == org_id))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User is already a member of this organization")
        
    new_member = Membership(
        user_id=target_user_id,
        organization_id=org_id,
        role=member_in.role
    )
    db.add(new_member)
    await db.commit()
    return {"status": "success"}

@router.delete("/{org_id}/members/{user_id}")
async def remove_member(
    org_id: str,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    membership: Membership = Depends(RoleChecker([RoleEnum.OWNER, RoleEnum.ADMIN]))
):
    # Cannot remove oneself this way (or prevent removing OWNER if needed, keeping simple for now)
    if user_id == membership.user_id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")
        
    result = await db.execute(select(Membership).filter(Membership.user_id == user_id, Membership.organization_id == org_id))
    member_to_remove = result.scalar_one_or_none()
    
    if not member_to_remove:
        raise HTTPException(status_code=404, detail="Member not found")
        
    await db.delete(member_to_remove)
    await db.commit()
    return {"status": "success"}
