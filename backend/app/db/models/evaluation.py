import uuid
from sqlalchemy import Column, String, Float, Integer, Text, ForeignKey, DateTime, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.db.database import Base


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    dataset_id = Column(String, nullable=False)
    dataset_version = Column(String, nullable=False)
    status = Column(String, nullable=False, default="COMPLETED")  # RUNNING, COMPLETED, FAILED
    total_cases = Column(Integer, nullable=False, default=0)
    passed_cases = Column(Integer, nullable=False, default=0)
    failed_cases = Column(Integer, nullable=False, default=0)
    average_correctness = Column(Float, nullable=False, default=0.0)
    average_groundedness = Column(Float, nullable=False, default=0.0)
    average_retrieval_score = Column(Float, nullable=False, default=0.0)
    total_duration_ms = Column(Float, nullable=False, default=0.0)
    total_tokens = Column(Integer, nullable=False, default=0)
    created_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    records = relationship("EvaluationRecord", back_populates="run", cascade="all, delete-orphan")


class EvaluationRecord(Base):
    __tablename__ = "evaluation_records"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String, ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    dataset_id = Column(String, nullable=False)
    case_id = Column(String, nullable=False)
    category = Column(String, nullable=False)
    query = Column(Text, nullable=False)
    expected_answer = Column(Text, nullable=True)
    actual_answer = Column(Text, nullable=True)
    expected_sources = Column(JSON, nullable=True)
    retrieved_sources = Column(JSON, nullable=True)
    correctness_score = Column(Float, nullable=False, default=0.0)
    groundedness_score = Column(Float, nullable=False, default=0.0)
    retrieval_score = Column(Float, nullable=False, default=0.0)
    latency_ms = Column(Float, nullable=False, default=0.0)
    token_usage = Column(JSON, nullable=True)
    status = Column(String, nullable=False, default="PASSED")  # PASSED, FAILED, ERROR
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    run = relationship("EvaluationRun", back_populates="records")
