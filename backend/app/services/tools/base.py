from abc import ABC, abstractmethod
from typing import Type, Any, Optional
from pydantic import BaseModel, Field


class ToolContext(BaseModel):
    """Authenticated context passed to every tool execution."""
    organization_id: str
    user_id: str
    user_role: str = "MEMBER"
    conversation_id: Optional[str] = None


class ToolResult(BaseModel):
    """Standardized tool execution outcome."""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0


class BaseTool(ABC):
    """Abstract base class for all enterprise agent tools."""

    name: str
    description: str
    input_schema: Type[BaseModel]
    output_schema: Type[BaseModel]
    required_roles: list[str] = Field(default_factory=lambda: ["MEMBER", "MANAGER", "ADMIN", "OWNER"])

    @abstractmethod
    async def execute(self, input_data: BaseModel, context: ToolContext) -> ToolResult:
        """Execute the tool business logic with the verified tenant context."""
        pass

    def to_dict(self) -> dict[str, Any]:
        """Convert tool definition to JSON-serializable dictionary for LLM tool catalogs."""
        schema = self.input_schema.model_json_schema() if hasattr(self.input_schema, "model_json_schema") else self.input_schema.schema()
        return {
            "name": self.name,
            "description": self.description,
            "parameters": schema,
            "required_roles": self.required_roles,
        }
