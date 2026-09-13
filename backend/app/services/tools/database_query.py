import re
import time
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field
from sqlalchemy import select, func, desc
from app.core.logging import logger
import app.db.database as db_module
from app.db.models.document import Document
from app.db.models.document_chunk import DocumentChunk
from app.db.models.conversation import Conversation
from app.db.models.membership import Membership
from app.services.tools.base import BaseTool, ToolContext, ToolResult


# Disallowed mutation keywords
MUTATION_PATTERN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|replace|grant|revoke)\b",
    re.IGNORECASE,
)


class DatabaseQueryInput(BaseModel):
    """Input payload for controlled, read-only organization database queries."""
    operation: Literal[
        "count_documents",
        "list_document_metadata",
        "count_conversations",
        "organization_statistics",
    ] = Field(
        ...,
        description="Structured read-only query operation to execute.",
    )
    limit: Optional[int] = Field(
        default=10,
        description="Maximum items to return for list operations (1-50).",
        ge=1,
        le=50,
    )
    raw_sql: Optional[str] = Field(
        default=None,
        description="Raw SQL queries are strictly forbidden and will be rejected.",
    )


class DatabaseQueryOutput(BaseModel):
    """Output payload of read-only database query execution."""
    operation: str
    organization_id: str
    result: Any


class DatabaseQueryTool(BaseTool):
    """Performs controlled, read-only database queries strictly isolated to the user's organization."""

    name = "database_query"
    description = (
        "Query organizational statistics and metadata (e.g. document counts, list document metadata, "
        "conversation count, organization statistics). Read-only and strictly scoped to current organization."
    )
    input_schema = DatabaseQueryInput
    output_schema = DatabaseQueryOutput
    required_roles = ["MANAGER", "ADMIN", "OWNER"]

    async def execute(self, input_data: DatabaseQueryInput, context: ToolContext) -> ToolResult:
        start_time = time.time()
        org_id = context.organization_id

        # Strict security check: reject raw SQL or mutation attempts
        if input_data.raw_sql or (input_data.operation and MUTATION_PATTERN.search(input_data.operation)):
            elapsed = (time.time() - start_time) * 1000.0
            logger.warning(
                f"Security violation in database_query tool: rejected raw SQL/mutation from org_id='{org_id}'"
            )
            return ToolResult(
                success=False,
                error="Arbitrary or mutation SQL operations are strictly forbidden.",
                execution_time_ms=elapsed,
            )

        try:
            async with db_module.async_session_maker() as session:
                if input_data.operation == "count_documents":
                    res = await session.execute(
                        select(func.count(Document.id)).filter(
                            Document.organization_id == org_id,
                        )
                    )
                    count = res.scalar() or 0
                    data = {"total_documents": count}

                elif input_data.operation == "list_document_metadata":
                    res = await session.execute(
                        select(
                            Document.id,
                            Document.filename,
                            Document.file_type,
                            Document.file_size,
                            Document.chunk_count,
                            Document.status,
                            Document.created_at,
                        )
                        .filter(
                            Document.organization_id == org_id,
                        )
                        .order_by(desc(Document.created_at))
                        .limit(input_data.limit or 10)
                    )
                    rows = res.all()
                    data = {
                        "documents": [
                            {
                                "id": r.id,
                                "filename": r.filename,
                                "file_type": r.file_type,
                                "file_size_bytes": r.file_size,
                                "chunk_count": r.chunk_count,
                                "status": r.status.value if hasattr(r.status, "value") else str(r.status),
                                "created_at": r.created_at.isoformat() if r.created_at else None,
                            }
                            for r in rows
                        ]
                    }

                elif input_data.operation == "count_conversations":
                    res = await session.execute(
                        select(func.count(Conversation.id)).filter(
                            Conversation.organization_id == org_id
                        )
                    )
                    count = res.scalar() or 0
                    data = {"total_conversations": count}

                elif input_data.operation == "organization_statistics":
                    doc_count_res = await session.execute(
                        select(func.count(Document.id)).filter(
                            Document.organization_id == org_id,
                        )
                    )
                    doc_count = doc_count_res.scalar() or 0

                    chunk_count_res = await session.execute(
                        select(func.count(DocumentChunk.id)).filter(
                            DocumentChunk.organization_id == org_id
                        )
                    )
                    chunk_count = chunk_count_res.scalar() or 0

                    conv_count_res = await session.execute(
                        select(func.count(Conversation.id)).filter(
                            Conversation.organization_id == org_id
                        )
                    )
                    conv_count = conv_count_res.scalar() or 0

                    member_count_res = await session.execute(
                        select(func.count(Membership.id)).filter(
                            Membership.organization_id == org_id
                        )
                    )
                    member_count = member_count_res.scalar() or 0

                    data = {
                        "total_documents": doc_count,
                        "total_indexed_chunks": chunk_count,
                        "total_conversations": conv_count,
                        "total_members": member_count,
                    }

                else:
                    elapsed = (time.time() - start_time) * 1000.0
                    return ToolResult(
                        success=False,
                        error=f"Unsupported operation: '{input_data.operation}'",
                        execution_time_ms=elapsed,
                    )

            elapsed = (time.time() - start_time) * 1000.0
            return ToolResult(
                success=True,
                data={
                    "operation": input_data.operation,
                    "organization_id": org_id,
                    "result": data,
                },
                execution_time_ms=elapsed,
            )

        except Exception as e:
            logger.error(f"DatabaseQueryTool error: {e}", exc_info=True)
            elapsed = (time.time() - start_time) * 1000.0
            return ToolResult(
                success=False,
                error=f"Database query error: {str(e)}",
                execution_time_ms=elapsed,
            )
