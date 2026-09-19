import asyncio
import time
from typing import Optional, Any
from pydantic import ValidationError
from app.core.config import settings
from app.core.logging import logger
from app.services.tools.base import BaseTool, ToolContext, ToolResult
from app.services.tools.permissions import ToolPermissionChecker, ToolPermissionError
from app.services.tools.calculator import CalculatorTool
from app.services.tools.knowledge_search import KnowledgeSearchTool
from app.services.tools.database_query import DatabaseQueryTool
from app.services.tools.organization_stats import OrganizationStatsTool
from app.services.tools.demo_note import CreateDemoNoteTool


class ToolRegistry:
    """Central registry governing tool discovery, schema validation, and authorization."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        # Register standard default tools
        self.register(CalculatorTool())
        self.register(KnowledgeSearchTool())
        self.register(DatabaseQueryTool())
        self.register(OrganizationStatsTool())
        self.register(CreateDemoNoteTool())

    def register(self, tool: BaseTool) -> None:
        """Register a strongly typed tool in the system."""
        self._tools[tool.name] = tool
        logger.info(f"Registered agent tool: '{tool.name}' (roles: {tool.required_roles})")

    def get(self, name: str) -> Optional[BaseTool]:
        """Retrieve tool by exact name."""
        return self._tools.get(name)

    def list_all(self) -> list[BaseTool]:
        """List all registered tools."""
        return list(self._tools.values())

    def get_available_tools(self, user_role: str) -> list[BaseTool]:
        """Return only tools that the authenticated user's role is permitted to execute."""
        return [
            tool for tool in self._tools.values()
            if ToolPermissionChecker.is_authorized(user_role, tool.required_roles)
        ]

    def get_tool_definitions(self, user_role: str) -> list[dict[str, Any]]:
        """Return JSON-serializable tool schemas for LLM system prompt catalog."""
        return [tool.to_dict() for tool in self.get_available_tools(user_role)]

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: ToolContext,
        timeout: Optional[float] = None,
    ) -> ToolResult:
        """Validate permissions, arguments, and safely execute tool within timeout."""
        start_time = time.time()
        timeout_seconds = timeout or getattr(settings, "TOOL_TIMEOUT_SECONDS", 10.0)

        # 1. Lookup Tool
        tool = self.get(tool_name)
        if not tool:
            elapsed = (time.time() - start_time) * 1000.0
            logger.warning(f"Attempted to invoke unregistered tool: '{tool_name}'")
            return ToolResult(
                success=False,
                error=f"Unregistered tool: '{tool_name}'. Available tools: {list(self._tools.keys())}",
                execution_time_ms=elapsed,
            )

        # 2. Enforce Permissions
        try:
            ToolPermissionChecker.verify_permission(
                tool_name=tool.name,
                user_role=context.user_role,
                required_roles=tool.required_roles,
            )
        except ToolPermissionError as pe:
            elapsed = (time.time() - start_time) * 1000.0
            return ToolResult(
                success=False,
                error=str(pe),
                execution_time_ms=elapsed,
            )

        # 3. Validate Input Arguments against Pydantic Schema
        try:
            validated_input = tool.input_schema(**arguments)
        except ValidationError as ve:
            elapsed = (time.time() - start_time) * 1000.0
            logger.warning(f"Validation failed for tool '{tool_name}': {ve}")
            return ToolResult(
                success=False,
                error=f"Invalid arguments for tool '{tool_name}': {ve.errors()}",
                execution_time_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000.0
            return ToolResult(
                success=False,
                error=f"Malformed arguments for tool '{tool_name}': {str(e)}",
                execution_time_ms=elapsed,
            )

        # 4. Execute with Timeout
        try:
            result = await asyncio.wait_for(
                tool.execute(validated_input, context),
                timeout=timeout_seconds,
            )
            return result
        except asyncio.TimeoutError:
            elapsed = (time.time() - start_time) * 1000.0
            logger.error(f"Tool '{tool_name}' timed out after {timeout_seconds}s")
            return ToolResult(
                success=False,
                error=f"Tool '{tool_name}' execution timed out after {timeout_seconds} seconds.",
                execution_time_ms=elapsed,
            )
        except asyncio.CancelledError:
            elapsed = (time.time() - start_time) * 1000.0
            logger.warning(f"Tool '{tool_name}' execution cancelled.")
            raise
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000.0
            logger.error(f"Unexpected error executing tool '{tool_name}': {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=f"Execution error in tool '{tool_name}': {str(e)}",
                execution_time_ms=elapsed,
            )


# Global singleton registry instance
tool_registry = ToolRegistry()
