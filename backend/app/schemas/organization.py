from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.db.models.membership import RoleEnum

class OrganizationBase(BaseModel):
    name: str
    slug: Optional[str] = None

class OrganizationCreate(OrganizationBase):
    pass

class OrganizationUpdate(OrganizationBase):
    name: Optional[str] = None

class OrganizationInDBBase(OrganizationBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class Organization(OrganizationInDBBase):
    pass

class MembershipBase(BaseModel):
    role: RoleEnum

class MembershipCreate(MembershipBase):
    user_id: str
    organization_id: str

class Membership(MembershipBase):
    id: str
    user_id: str
    organization_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
