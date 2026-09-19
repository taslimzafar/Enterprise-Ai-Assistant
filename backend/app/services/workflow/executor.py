import json
from typing import AsyncGenerator
from app.services.workflow.engine import WorkflowEngine


class WorkflowStreamingExecutor:
    """Formats workflow execution lifecycle events into standard Server-Sent Events (SSE)."""

    @classmethod
    async def stream_execution(
        cls,
        execution_id: str,
        organization_id: str,
        user_id: str,
        user_role: str,
    ) -> AsyncGenerator[str, None]:
        """Stream SSE chunks for workflow execution."""
        async for event in WorkflowEngine.run_execution(
            execution_id=execution_id,
            organization_id=organization_id,
            user_id=user_id,
            user_role=user_role,
        ):
            event_name = event.get("event", "message")
            data_payload = json.dumps(event.get("data", {}))
            yield f"event: {event_name}\ndata: {data_payload}\n\n"
