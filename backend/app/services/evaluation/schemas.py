from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class TestCaseSchema(BaseModel):
    __test__ = False

    id: str
    question: str
    expected_answer: Optional[str] = None
    expected_source_ids: List[str] = Field(default_factory=list)
    category: str  # factual, retrieval, multi-document, no-answer, conversational, tool-use, workflow, security
    difficulty: str = "medium"  # easy, medium, hard
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EvaluationDatasetSchema(BaseModel):
    id: str
    name: str
    version: str
    description: str
    total_cases: int
    categories: List[str]
    cases: List[TestCaseSchema] = Field(default_factory=list)


class EvaluationRunRequest(BaseModel):
    dataset_id: str = "baseline_v1"
    dataset_version: Optional[str] = "1.0.0"
    categories: Optional[List[str]] = None  # optional filter


class EvaluationRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    organization_id: str
    dataset_id: str
    case_id: str
    category: str
    query: str
    expected_answer: Optional[str] = None
    actual_answer: Optional[str] = None
    expected_sources: Optional[List[str]] = None
    retrieved_sources: Optional[List[str]] = None
    correctness_score: float
    groundedness_score: float
    retrieval_score: float
    latency_ms: float
    token_usage: Optional[Dict[str, Any]] = None
    status: str
    error: Optional[str] = None
    created_at: Optional[datetime] = None


class EvaluationRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    dataset_id: str
    dataset_version: str
    status: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    average_correctness: float
    average_groundedness: float
    average_retrieval_score: float
    total_duration_ms: float
    total_tokens: int
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    records: Optional[List[EvaluationRecordResponse]] = None


class CategoryMetric(BaseModel):
    category: str
    total_cases: int
    passed_cases: int
    pass_rate: float
    average_correctness: float
    average_groundedness: float
    average_retrieval: float


class LatencyPercentiles(BaseModel):
    count: int
    average_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    min_ms: float
    max_ms: float


class EvaluationMetricsResponse(BaseModel):
    total_runs: int
    total_evaluations: int
    pass_rate: float
    average_correctness: float
    average_groundedness: float
    average_retrieval_score: float
    categories: List[CategoryMetric] = Field(default_factory=list)
    latency: LatencyPercentiles
