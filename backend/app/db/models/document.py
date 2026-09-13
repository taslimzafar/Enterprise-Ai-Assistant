from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Integer, Text
from sqlalchemy.sql import func
from app.db.database import Base
import uuid
import enum


class DocumentStatus(str, enum.Enum):
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    EMBEDDING = "EMBEDDING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    uploaded_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    filename = Column(String, nullable=False)  # Safe generated filename (UUID-based)
    original_filename = Column(String, nullable=False)  # User's original filename
    file_type = Column(String, nullable=False)  # pdf, docx, txt
    mime_type = Column(String, nullable=True)
    file_size = Column(Integer, nullable=False)  # bytes
    storage_path = Column(String, nullable=False)  # Key in storage backend
    status = Column(Enum(DocumentStatus), default=DocumentStatus.UPLOADED, nullable=False, index=True)
    processing_error = Column(Text, nullable=True)
    chunk_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)
