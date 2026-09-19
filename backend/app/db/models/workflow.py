import enum
import uuid
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Enum, Text, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base


class WorkflowStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ARCHIVED = "ARCHIVED"


class ExecutionStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StepExecutionStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


class StepType(str, enum.Enum):
    KNOWLEDGE_SEARCH = "KNOWLEDGE_SEARCH"
    CALCULATOR = "CALCULATOR"
    ORGANIZATION_STATS = "ORGANIZATION_STATS"
    DEMO_NOTE = "DEMO_NOTE"
    LLM_GENERATION = "LLM_GENERATION"


class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(
        String,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String, nullable=False)
    description = Column(Text, nullable=False, default="")
    status = Column(
        Enum(WorkflowStatus, name="workflowstatus"),
        default=WorkflowStatus.DRAFT,
        nullable=False,
        index=True,
    )
    version = Column(Integer, default=1, nullable=False)
    created_by = Column(
        String,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    organization = relationship("Organization")
    creator = relationship("User", foreign_keys=[created_by])
    steps = relationship("WorkflowStep", back_populates="workflow", cascade="all, delete-orphan", order_by="WorkflowStep.order")
    executions = relationship("WorkflowExecution", back_populates="workflow", cascade="all, delete-orphan")


class WorkflowStep(Base):
    __tablename__ = "workflow_steps"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    workflow_id = Column(
        String,
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String, nullable=False)
    type = Column(
        Enum(StepType, name="steptype"),
        nullable=False,
    )
    order = Column(Integer, nullable=False, default=0, index=True)
    configuration = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict)
    input_mapping = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict)
    output_key = Column(String, nullable=False)
    timeout_seconds = Column(Integer, default=30, nullable=False)
    retry_count = Column(Integer, default=0, nullable=False)
    requires_approval = Column(Boolean, default=False, nullable=False)
    condition = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)

    # Relationships
    workflow = relationship("Workflow", back_populates="steps")
    step_executions = relationship("WorkflowStepExecution", back_populates="step", cascade="all, delete-orphan")


class WorkflowExecution(Base):
    __tablename__ = "workflow_executions"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    workflow_id = Column(
        String,
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id = Column(
        String,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = Column(
        Enum(ExecutionStatus, name="executionstatus"),
        default=ExecutionStatus.PENDING,
        nullable=False,
        index=True,
    )
    context_data = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict)
    error = Column(Text, nullable=True)
    executed_by = Column(
        String,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    workflow = relationship("Workflow", back_populates="executions")
    organization = relationship("Organization")
    executor = relationship("User", foreign_keys=[executed_by])
    step_executions = relationship(
        "WorkflowStepExecution",
        back_populates="execution",
        cascade="all, delete-orphan",
        order_by="WorkflowStepExecution.started_at"
    )


class WorkflowStepExecution(Base):
    __tablename__ = "workflow_step_executions"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    execution_id = Column(
        String,
        ForeignKey("workflow_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_id = Column(
        String,
        ForeignKey("workflow_steps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = Column(
        Enum(StepExecutionStatus, name="stepexecutionstatus"),
        default=StepExecutionStatus.PENDING,
        nullable=False,
        index=True,
    )
    inputs = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict)
    outputs = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict)
    error = Column(Text, nullable=True)
    retry_attempts = Column(Integer, default=0, nullable=False)
    approval_id = Column(
        String,
        ForeignKey("approvals.id", ondelete="SET NULL"),
        nullable=True,
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    execution = relationship("WorkflowExecution", back_populates="step_executions")
    step = relationship("WorkflowStep", back_populates="step_executions")
    approval = relationship("Approval")
