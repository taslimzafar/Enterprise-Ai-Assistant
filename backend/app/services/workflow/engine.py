import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, AsyncGenerator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
import app.db.database as db_module
from app.db.models.workflow import (
    Workflow,
    WorkflowStep,
    WorkflowExecution,
    WorkflowStepExecution,
    WorkflowStatus,
    ExecutionStatus,
    StepExecutionStatus,
    StepType,
)
from app.db.models.approval import Approval, ApprovalStatus
from app.services.approval.service import approval_service
from app.services.tools import tool_registry
from app.services.workflow.models import StepResult, WorkflowExecutionContext
from app.services.workflow.conditions import SafeConditionEvaluator
from app.services.workflow.registry import StepHandlerRegistry
from app.services.workflow.exceptions import (
    WorkflowStateError,
    WorkflowNotFoundError,
    WorkflowExecutionNotFoundError,
    InvalidConditionError,
    StepExecutionError,
    ApprovalRequiredPause,
)


class WorkflowEngine:
    """Deterministic, resilient multi-step workflow execution engine with PostgreSQL state persistence."""

    @classmethod
    async def run_execution(
        cls,
        execution_id: str,
        organization_id: str,
        user_id: str,
        user_role: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute a workflow instance step-by-step, persisting state at every boundary and yielding SSE events."""
        async with db_module.async_session_maker() as session:
            # 1. Load execution & workflow
            exec_query = (
                select(WorkflowExecution)
                .filter(
                    WorkflowExecution.id == execution_id,
                    WorkflowExecution.organization_id == organization_id,
                )
            )
            exec_res = await session.execute(exec_query)
            execution = exec_res.scalar_one_or_none()
            if not execution:
                raise WorkflowExecutionNotFoundError(f"Workflow execution '{execution_id}' not found.")

            wf_query = select(Workflow).filter(Workflow.id == execution.workflow_id)
            wf_res = await session.execute(wf_query)
            workflow = wf_res.scalar_one_or_none()
            if not workflow:
                raise WorkflowNotFoundError(f"Workflow '{execution.workflow_id}' not found.")

            # Check execution state
            if execution.status in (ExecutionStatus.COMPLETED, ExecutionStatus.CANCELLED, ExecutionStatus.FAILED):
                raise WorkflowStateError(f"Cannot execute workflow in terminal status '{execution.status.value}'.")

            # Mark running
            execution.status = ExecutionStatus.RUNNING
            if not execution.started_at:
                execution.started_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(execution)

            # Load steps in order
            steps_query = (
                select(WorkflowStep)
                .filter(WorkflowStep.workflow_id == workflow.id)
                .order_by(WorkflowStep.order.asc())
            )
            steps_res = await session.execute(steps_query)
            steps = list(steps_res.scalars().all())

            # Load or create step executions
            step_execs_query = (
                select(WorkflowStepExecution)
                .filter(WorkflowStepExecution.execution_id == execution_id)
            )
            step_execs_res = await session.execute(step_execs_query)
            step_exec_map = {se.step_id: se for se in step_execs_res.scalars().all()}

            context_data = dict(execution.context_data or {})

        # Yield workflow start event
        yield {
            "event": "workflow_start",
            "data": {
                "execution_id": execution.id,
                "workflow_id": workflow.id,
                "workflow_name": workflow.name,
                "status": "RUNNING",
                "total_steps": len(steps),
            },
        }

        # 2. Iterate through steps sequentially
        for step in steps:
            # Check if this step was already completed or skipped in a previous turn
            step_exec = step_exec_map.get(step.id)
            if step_exec and step_exec.status in (StepExecutionStatus.COMPLETED, StepExecutionStatus.SKIPPED):
                continue

            # Ensure StepExecution record exists
            async with db_module.async_session_maker() as session:
                if not step_exec:
                    step_exec = WorkflowStepExecution(
                        execution_id=execution_id,
                        step_id=step.id,
                        status=StepExecutionStatus.PENDING,
                        inputs={},
                        outputs={},
                        retry_attempts=0,
                    )
                    session.add(step_exec)
                    await session.commit()
                    await session.refresh(step_exec)
                    step_exec_map[step.id] = step_exec

                # 3. Evaluate Condition (if configured)
                if step.condition:
                    try:
                        satisfies = SafeConditionEvaluator.evaluate(step.condition, context_data)
                    except InvalidConditionError as ice:
                        logger.error(f"Invalid condition in step '{step.name}': {ice}")
                        step_exec.status = StepExecutionStatus.FAILED
                        step_exec.error = str(ice)
                        step_exec.completed_at = datetime.now(timezone.utc)
                        execution.status = ExecutionStatus.FAILED
                        execution.error = f"Condition error in step '{step.name}': {ice}"
                        execution.completed_at = datetime.now(timezone.utc)
                        await session.commit()

                        yield {
                            "event": "workflow_step_failed",
                            "data": {
                                "execution_id": execution_id,
                                "step_id": step.id,
                                "step_name": step.name,
                                "error": str(ice),
                            },
                        }
                        yield {
                            "event": "workflow_failed",
                            "data": {"execution_id": execution_id, "error": str(ice)},
                        }
                        return

                    if not satisfies:
                        logger.info(f"Step '{step.name}' condition evaluated to False. Skipping.")
                        step_exec.status = StepExecutionStatus.SKIPPED
                        step_exec.completed_at = datetime.now(timezone.utc)
                        await session.commit()
                        continue

                # 4. Resolve inputs
                resolved_inputs = StepHandlerRegistry.resolve_inputs(
                    configuration=step.configuration,
                    input_mapping=step.input_mapping,
                    context_data=context_data,
                )
                step_exec.inputs = resolved_inputs
                step_exec.status = StepExecutionStatus.RUNNING
                step_exec.started_at = datetime.now(timezone.utc)
                await session.commit()

            yield {
                "event": "workflow_step_start",
                "data": {
                    "execution_id": execution_id,
                    "step_id": step.id,
                    "step_name": step.name,
                    "step_type": step.type.value,
                    "order": step.order,
                },
            }

            # 5. Check Human-in-the-Loop (HITL) approval requirement
            underlying_tool_name = StepHandlerRegistry.STEP_TOOL_MAPPING.get(step.type)
            underlying_tool = tool_registry.get(underlying_tool_name) if underlying_tool_name else None
            tool_needs_appr = getattr(underlying_tool, "requires_approval", False)
            step_needs_appr = step.requires_approval or tool_needs_appr

            if step_needs_appr:
                async with db_module.async_session_maker() as session:
                    curr_step_exec = await session.get(WorkflowStepExecution, step_exec.id)
                    curr_execution = await session.get(WorkflowExecution, execution_id)

                    # Check if approval already created and its status
                    if curr_step_exec.approval_id:
                        approval = await approval_service.get_approval(session, curr_step_exec.approval_id, organization_id)
                        if approval.status == ApprovalStatus.APPROVED:
                            logger.info(f"Step '{step.name}' has verified approval '{approval.id}'. Permitting execution.")
                        elif approval.status == ApprovalStatus.REJECTED:
                            err_msg = f"Step '{step.name}' was rejected: {approval.rejection_reason or 'No reason provided'}"
                            curr_step_exec.status = StepExecutionStatus.FAILED
                            curr_step_exec.error = err_msg
                            curr_step_exec.completed_at = datetime.now(timezone.utc)
                            curr_execution.status = ExecutionStatus.FAILED
                            curr_execution.error = err_msg
                            curr_execution.completed_at = datetime.now(timezone.utc)
                            await session.commit()

                            yield {
                                "event": "workflow_step_failed",
                                "data": {
                                    "execution_id": execution_id,
                                    "step_id": step.id,
                                    "step_name": step.name,
                                    "error": err_msg,
                                },
                            }
                            yield {
                                "event": "workflow_failed",
                                "data": {"execution_id": execution_id, "error": err_msg},
                            }
                            return
                        elif approval.status in (ApprovalStatus.EXPIRED, ApprovalStatus.CANCELLED):
                            err_msg = f"Step '{step.name}' approval has expired or was cancelled."
                            curr_step_exec.status = StepExecutionStatus.FAILED
                            curr_step_exec.error = err_msg
                            curr_step_exec.completed_at = datetime.now(timezone.utc)
                            curr_execution.status = ExecutionStatus.FAILED
                            curr_execution.error = err_msg
                            curr_execution.completed_at = datetime.now(timezone.utc)
                            await session.commit()

                            yield {
                                "event": "workflow_step_failed",
                                "data": {
                                    "execution_id": execution_id,
                                    "step_id": step.id,
                                    "step_name": step.name,
                                    "error": err_msg,
                                },
                            }
                            yield {
                                "event": "workflow_failed",
                                "data": {"execution_id": execution_id, "error": err_msg},
                            }
                            return
                        else:
                            # Still PENDING
                            curr_execution.status = ExecutionStatus.WAITING_APPROVAL
                            curr_step_exec.status = StepExecutionStatus.WAITING_APPROVAL
                            await session.commit()

                            yield {
                                "event": "workflow_waiting_approval",
                                "data": {
                                    "execution_id": execution_id,
                                    "step_id": step.id,
                                    "step_name": step.name,
                                    "approval_id": approval.id,
                                },
                            }
                            return

                    else:
                        # Create new Phase 10 approval record
                        approval = await approval_service.create_approval(
                            db=session,
                            organization_id=organization_id,
                            requested_by_user_id=user_id,
                            tool_name=underlying_tool_name or f"workflow_step_{step.name}",
                            action_type="workflow_step",
                            action_arguments=resolved_inputs,
                            reason=f"Workflow '{workflow.name}' step '{step.name}' requires authorization.",
                        )
                        curr_step_exec.approval_id = approval.id
                        curr_step_exec.status = StepExecutionStatus.WAITING_APPROVAL
                        curr_execution.status = ExecutionStatus.WAITING_APPROVAL
                        await session.commit()

                        step_exec.approval_id = approval.id
                        step_exec.status = StepExecutionStatus.WAITING_APPROVAL

                        logger.info(
                            f"Workflow execution '{execution_id}' paused for approval '{approval.id}' at step '{step.name}'"
                        )

                        yield {
                            "event": "workflow_waiting_approval",
                            "data": {
                                "execution_id": execution_id,
                                "step_id": step.id,
                                "step_name": step.name,
                                "approval_id": approval.id,
                                "action_arguments": resolved_inputs,
                            },
                        }
                        return

            # 6. Execute step with retry mechanism
            max_attempts = max(1, 1 + step.retry_count)
            attempt = 0
            step_result: Optional[StepResult] = None

            exec_runtime_ctx = WorkflowExecutionContext(
                workflow_id=workflow.id,
                execution_id=execution_id,
                organization_id=organization_id,
                user_id=user_id,
                user_role=user_role,
                data=context_data,
            )

            while attempt < max_attempts:
                attempt += 1
                try:
                    step_result = await StepHandlerRegistry.execute_step(
                        step_type=step.type,
                        step_name=step.name,
                        resolved_inputs=resolved_inputs,
                        exec_ctx=exec_runtime_ctx,
                        timeout_seconds=step.timeout_seconds,
                    )
                    if step_result.success:
                        break
                    else:
                        logger.warning(f"Step '{step.name}' attempt {attempt}/{max_attempts} failed: {step_result.error}")
                except Exception as e:
                    logger.error(f"Step '{step.name}' attempt {attempt}/{max_attempts} raised exception: {e}")
                    step_result = StepResult(success=False, error=str(e))

            # 7. Process Step Result
            async with db_module.async_session_maker() as session:
                step_exec = await session.get(WorkflowStepExecution, step_exec.id)
                step_exec.retry_attempts = attempt - 1

                if not step_result or not step_result.success:
                    err_msg = step_result.error if step_result else "Unknown execution error."
                    step_exec.status = StepExecutionStatus.FAILED
                    step_exec.error = err_msg
                    step_exec.completed_at = datetime.now(timezone.utc)

                    execution = await session.get(WorkflowExecution, execution_id)
                    execution.status = ExecutionStatus.FAILED
                    execution.error = f"Step '{step.name}' failed after {attempt} attempts: {err_msg}"
                    execution.completed_at = datetime.now(timezone.utc)
                    await session.commit()

                    yield {
                        "event": "workflow_step_failed",
                        "data": {
                            "execution_id": execution_id,
                            "step_id": step.id,
                            "step_name": step.name,
                            "error": err_msg,
                            "retry_attempts": attempt - 1,
                        },
                    }
                    yield {
                        "event": "workflow_failed",
                        "data": {"execution_id": execution_id, "error": execution.error},
                    }
                    return

                # Success: persist step output in context data
                context_data[step.output_key] = step_result.output
                step_exec.status = StepExecutionStatus.COMPLETED
                step_exec.outputs = (
                    step_result.output if isinstance(step_result.output, dict)
                    else {"result": step_result.output}
                )
                step_exec.completed_at = datetime.now(timezone.utc)

                execution = await session.get(WorkflowExecution, execution_id)
                execution.context_data = context_data
                await session.commit()

            yield {
                "event": "workflow_step_complete",
                "data": {
                    "execution_id": execution_id,
                    "step_id": step.id,
                    "step_name": step.name,
                    "output_key": step.output_key,
                    "outputs": step_exec.outputs,
                },
            }

        # 8. All steps completed successfully
        async with db_module.async_session_maker() as session:
            execution = await session.get(WorkflowExecution, execution_id)
            execution.status = ExecutionStatus.COMPLETED
            execution.completed_at = datetime.now(timezone.utc)
            await session.commit()

        yield {
            "event": "workflow_complete",
            "data": {
                "execution_id": execution_id,
                "workflow_id": workflow.id,
                "status": "COMPLETED",
                "context_data": context_data,
            },
        }
