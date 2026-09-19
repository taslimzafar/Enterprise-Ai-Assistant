from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime, timezone


class ErrorCategory(str, Enum):
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RAG_ERROR = "RAG_ERROR"
    LLM_ERROR = "LLM_ERROR"
    TOOL_ERROR = "TOOL_ERROR"
    APPROVAL_ERROR = "APPROVAL_ERROR"
    WORKFLOW_ERROR = "WORKFLOW_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    TIMEOUT = "TIMEOUT"
    RATE_LIMIT = "RATE_LIMIT"
    UNKNOWN = "UNKNOWN"


def categorize_error(error: Exception) -> ErrorCategory:
    """Classify an exception into a normalized ErrorCategory."""
    err_str = f"{type(error).__name__}: {str(error)}".lower()

    if "auth" in err_str or "credentials" in err_str or "token" in err_str or "jwt" in err_str:
        if "forbidden" in err_str or "permission" in err_str or "role" in err_str or "cross_tenant" in err_str:
            return ErrorCategory.AUTHORIZATION_ERROR
        return ErrorCategory.AUTHENTICATION_ERROR

    if "permission" in err_str or "forbidden" in err_str or "unauthorized" in err_str or "403" in err_str:
        return ErrorCategory.AUTHORIZATION_ERROR

    if "validation" in err_str or "pydantic" in err_str or "bad request" in err_str or "400" in err_str:
        return ErrorCategory.VALIDATION_ERROR

    if "timeout" in err_str or "timed out" in err_str:
        return ErrorCategory.TIMEOUT

    if "rate limit" in err_str or "429" in err_str:
        return ErrorCategory.RATE_LIMIT

    if "database" in err_str or "sqlalchemy" in err_str or "asyncpg" in err_str or "postgres" in err_str:
        return ErrorCategory.DATABASE_ERROR

    if "workflow" in err_str:
        return ErrorCategory.WORKFLOW_ERROR

    if "approval" in err_str:
        return ErrorCategory.APPROVAL_ERROR

    if "tool" in err_str or "calculator" in err_str:
        return ErrorCategory.TOOL_ERROR

    if "rag" in err_str or "embedding" in err_str or "retrieval" in err_str:
        return ErrorCategory.RAG_ERROR

    if "llm" in err_str or "openai" in err_str or "chat" in err_str:
        return ErrorCategory.LLM_ERROR

    return ErrorCategory.UNKNOWN


class ErrorRecord:
    def __init__(
        self,
        category: ErrorCategory,
        component: str,
        message: str,
        request_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ):
        self.category = category
        self.component = component
        self.message = message
        self.request_id = request_id
        self.organization_id = organization_id
        self.timestamp = timestamp or datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "component": self.component,
            "message": self.message,
            "request_id": self.request_id,
            "organization_id": self.organization_id,
            "timestamp": self.timestamp.isoformat(),
        }
