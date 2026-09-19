from typing import Any, Dict, Optional, Callable, Awaitable
from app.core.logging import logger
from app.db.models.workflow import StepType
from app.services.tools import tool_registry, ToolContext, ToolResult
from app.services.llm import get_llm_provider
from app.services.workflow.models import StepResult, WorkflowExecutionContext
from app.services.workflow.conditions import SafeConditionEvaluator
from app.services.workflow.exceptions import WorkflowValidationError, StepExecutionError


class StepHandlerRegistry:
    """Registry of safe, deterministic step runners for workflow execution."""

    STEP_TOOL_MAPPING = {
        StepType.KNOWLEDGE_SEARCH: "knowledge_search",
        StepType.CALCULATOR: "calculator",
        StepType.ORGANIZATION_STATS: "organization_stats",
        StepType.DEMO_NOTE: "create_demo_note",
    }

    @classmethod
    def resolve_inputs(
        cls,
        configuration: Dict[str, Any],
        input_mapping: Dict[str, Any],
        context_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Merge static configuration with dynamically resolved input mapping values."""
        resolved = dict(configuration or {})

        for target_arg, source_path in (input_mapping or {}).items():
            if isinstance(source_path, str):
                val = SafeConditionEvaluator.get_field_value(context_data, source_path)
                if val is not None:
                    resolved[target_arg] = val
            else:
                resolved[target_arg] = source_path

        return resolved

    @classmethod
    async def execute_step(
        cls,
        step_type: StepType,
        step_name: str,
        resolved_inputs: Dict[str, Any],
        exec_ctx: WorkflowExecutionContext,
        timeout_seconds: float = 30.0,
    ) -> StepResult:
        """Safely execute a supported step type."""
        # 1. Tool-based step execution
        if step_type in cls.STEP_TOOL_MAPPING:
            tool_name = cls.STEP_TOOL_MAPPING[step_type]
            tool = tool_registry.get(tool_name)
            if not tool:
                raise WorkflowValidationError(f"Underlying tool '{tool_name}' for step '{step_type}' not found.")

            tool_ctx = ToolContext(
                organization_id=exec_ctx.organization_id,
                user_id=exec_ctx.user_id,
                user_role=exec_ctx.user_role,
            )

            result: ToolResult = await tool_registry.execute_tool(
                tool_name=tool_name,
                arguments=resolved_inputs,
                context=tool_ctx,
                timeout=timeout_seconds,
            )

            if not result.success:
                return StepResult(
                    success=False,
                    error=result.error or f"Tool '{tool_name}' execution failed.",
                )

            return StepResult(
                success=True,
                output=result.data,
            )

        # 2. LLM Generation step execution
        elif step_type == StepType.LLM_GENERATION:
            prompt_template = resolved_inputs.get("prompt") or resolved_inputs.get("template") or ""
            system_prompt = resolved_inputs.get("system_prompt", "You are an enterprise AI assistant executing a workflow step.")

            # Simple safe template interpolation without eval
            interpolated_prompt = prompt_template
            for k, v in exec_ctx.data.items():
                if isinstance(v, (str, int, float, bool)):
                    interpolated_prompt = interpolated_prompt.replace(f"{{{k}}}", str(v))
                elif isinstance(v, dict):
                    for sub_k, sub_v in v.items():
                        if isinstance(sub_v, (str, int, float, bool)):
                            interpolated_prompt = interpolated_prompt.replace(f"{{{k}.{sub_k}}}", str(sub_v))

            try:
                llm = get_llm_provider()
                gen_func = getattr(llm, "generate", getattr(llm, "generate_response", None))
                response_text = await gen_func(
                    prompt=interpolated_prompt,
                    system_instruction=system_prompt,
                )
                return StepResult(
                    success=True,
                    output=response_text.strip(),
                )
            except Exception as e:
                logger.error(f"LLM generation failed in step '{step_name}': {e}", exc_info=True)
                return StepResult(
                    success=False,
                    error=f"LLM generation failed: {str(e)}",
                )

        raise WorkflowValidationError(f"Unsupported workflow step type: '{step_type}'")
