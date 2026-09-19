import uuid
import time
from typing import Optional
from pydantic import BaseModel, Field
from app.core.logging import logger
from app.services.tools.base import BaseTool, ToolContext, ToolResult


class CreateDemoNoteInput(BaseModel):
    """Input parameters for creating an internal organization demo note."""
    title: str = Field(..., min_length=1, max_length=200, description="Title of the demo note.")
    content: str = Field(..., min_length=1, description="Content body of the demo note.")


class CreateDemoNoteOutput(BaseModel):
    """Output payload from creating a demo note."""
    note_id: str
    title: str
    organization_id: str
    status: str
    created_at: str


class CreateDemoNoteTool(BaseTool):
    """Safe internal demonstration tool requiring explicit Human-in-the-Loop approval."""

    name = "create_demo_note"
    description = (
        "Create an internal organization demo note. This is a sensitive action that requires "
        "explicit human authorization before execution."
    )
    input_schema = CreateDemoNoteInput
    output_schema = CreateDemoNoteOutput
    required_roles = ["MEMBER", "MANAGER", "ADMIN", "OWNER"]
    requires_approval = True
    action_type = "create_note"

    async def execute(self, input_data: CreateDemoNoteInput, context: ToolContext) -> ToolResult:
        start_time = time.time()
        org_id = context.organization_id
        note_id = str(uuid.uuid4())

        logger.info(
            f"Executing CreateDemoNoteTool for org='{org_id}', user='{context.user_id}', title='{input_data.title}'"
        )

        elapsed = (time.time() - start_time) * 1000.0
        return ToolResult(
            success=True,
            data={
                "note_id": note_id,
                "title": input_data.title,
                "content": input_data.content,
                "organization_id": org_id,
                "status": "created",
                "created_by": context.user_id,
            },
            execution_time_ms=elapsed,
        )
