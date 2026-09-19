from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime
from app.db.models.membership import RoleEnum

class OrganizationBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: Optional[str] = Field(None, max_length=100)

class OrganizationCreate(OrganizationBase):
    pass

class OrganizationUpdate(OrganizationBase):
    name: Optional[str] = Field(None, min_length=1, max_length=255)

class OrganizationInDBBase(OrganizationBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

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

    model_config = ConfigDict(from_attributes=True)
