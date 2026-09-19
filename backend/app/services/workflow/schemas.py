from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator
from app.db.models.workflow import (
    WorkflowStatus,
    ExecutionStatus,
    StepExecutionStatus,
    StepType,
)


class WorkflowStepBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    type: StepType
    order: int = 0
    configuration: Dict[str, Any] = Field(default_factory=dict)
    input_mapping: Dict[str, Any] = Field(default_factory=dict)
    output_key: str = Field(..., min_length=1, max_length=100)
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    retry_count: int = Field(default=0, ge=0, le=5)
    requires_approval: bool = False
    condition: Optional[Dict[str, Any]] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Step name cannot be empty.")
        return v

    @field_validator("output_key")
    @classmethod
    def validate_output_key(cls, v: str) -> str:
        v = v.strip()
        if not v or not v.isidentifier():
            raise ValueError(f"Output key '{v}' must be a valid alphanumeric identifier.")
        return v


class WorkflowStepCreate(WorkflowStepBase):
    pass


class WorkflowStepResponse(WorkflowStepBase):
    id: str
    workflow_id: str

    model_config = ConfigDict(from_attributes=True)


class WorkflowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(default="", max_length=2000)
    steps: List[WorkflowStepCreate] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Workflow name cannot be empty.")
        return v


class WorkflowUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    steps: Optional[List[WorkflowStepCreate]] = None


class WorkflowResponse(BaseModel):
    id: str
    organization_id: str
    name: str
    description: str
    status: WorkflowStatus
    version: int
    created_by: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    steps: List[WorkflowStepResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class WorkflowListResponse(BaseModel):
    items: List[WorkflowResponse]
    total: int


class WorkflowExecutionCreate(BaseModel):
    initial_inputs: Dict[str, Any] = Field(default_factory=dict)


class WorkflowStepExecutionResponse(BaseModel):
    id: str
    execution_id: str
    step_id: str
    status: StepExecutionStatus
    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    retry_attempts: int = 0
    approval_id: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class WorkflowExecutionResponse(BaseModel):
    id: str
    workflow_id: str
    organization_id: str
    status: ExecutionStatus
    context_data: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    executed_by: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    step_executions: List[WorkflowStepExecutionResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class WorkflowExecutionListResponse(BaseModel):
    items: List[WorkflowExecutionResponse]
    total: int
