import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict


class SpanModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    trace_id: str
    span_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_span_id: Optional[str] = None
    name: str
    component: str  # Agent, Retrieval, Tool, LLM, Workflow, Step, Approval, API
    start_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    status: str = "RUNNING"  # RUNNING, OK, ERROR
    metadata: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None

    def finish(self, status: str = "OK", error: Optional[str] = None) -> None:
        self.end_time = datetime.now(timezone.utc)
        self.status = status
        self.error = error
        if self.start_time:
            self.duration_ms = round((self.end_time - self.start_time).total_seconds() * 1000.0, 2)


class TraceModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    organization_id: Optional[str] = None
    user_id: Optional[str] = None
    name: str
    start_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    total_duration_ms: Optional[float] = None
    status: str = "RUNNING"  # RUNNING, OK, ERROR
    spans: List[SpanModel] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def finish(self, status: str = "OK") -> None:
        self.end_time = datetime.now(timezone.utc)
        self.status = status
        if self.start_time:
            self.total_duration_ms = round((self.end_time - self.start_time).total_seconds() * 1000.0, 2)
