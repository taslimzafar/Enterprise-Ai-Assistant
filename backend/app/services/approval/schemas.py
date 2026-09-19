from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.db.models.approval import ApprovalStatus


class ApprovalCreate(BaseModel):
    """Schema for requesting a new human-in-the-loop approval."""
    tool_name: str = Field(..., description="Target tool name to execute upon approval.")
    action_type: str = Field(..., description="Descriptive action category (e.g. create_note, delete_doc).")
    action_arguments: dict[str, Any] = Field(default_factory=dict, description="Tool execution arguments.")
    reason: str = Field(..., description="Human-readable justification for the sensitive action.")
    conversation_id: Optional[str] = None
    message_id: Optional[str] = None
    expires_in_hours: Optional[int] = Field(default=24, ge=1, le=168)


class ApprovalAction(BaseModel):
    """Schema for approving, rejecting, or cancelling an approval request."""
    rejection_reason: Optional[str] = Field(default=None, description="Explanation when rejecting an approval.")


class ApprovalResponse(BaseModel):
    """Serialized representation of an approval record."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    requested_by_user_id: str
    conversation_id: Optional[str] = None
    message_id: Optional[str] = None
    tool_name: str
    action_type: str
    action_arguments: dict[str, Any]
    reason: str
    status: ApprovalStatus
    created_at: datetime
    updated_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    approved_by_user_id: Optional[str] = None
    approved_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None


class ApprovalListResponse(BaseModel):
    """Paginated list of approval records."""
    items: list[ApprovalResponse]
    total: int
