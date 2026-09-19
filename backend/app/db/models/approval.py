import enum
import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Text, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base


class ApprovalStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class Approval(Base):
    __tablename__ = "approvals"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(
        String,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requested_by_user_id = Column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conversation_id = Column(
        String,
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    message_id = Column(
        String,
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    tool_name = Column(String, nullable=False)
    action_type = Column(String, nullable=False)
    action_arguments = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict)
    reason = Column(Text, nullable=False, default="")
    status = Column(
        Enum(ApprovalStatus, name="approvalstatus"),
        default=ApprovalStatus.PENDING,
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)
    approved_by_user_id = Column(
        String,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)

    # Relationships
    organization = relationship("Organization")
    requester = relationship("User", foreign_keys=[requested_by_user_id])
    approver = relationship("User", foreign_keys=[approved_by_user_id])
    conversation = relationship("Conversation")
    message = relationship("Message")
