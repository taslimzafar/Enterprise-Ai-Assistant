import uuid
from datetime import datetime, timezone
from typing import Optional, List, Tuple, Dict, Any
from sqlalchemy import select, func, desc, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
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
from app.services.workflow.schemas import (
    WorkflowCreate,
    WorkflowUpdate,
    WorkflowStepCreate,
)
from app.services.workflow.exceptions import (
    WorkflowNotFoundError,
    WorkflowExecutionNotFoundError,
    WorkflowValidationError,
    WorkflowStateError,
    InvalidStateTransitionError,
    CrossTenantAccessError,
)
from app.services.workflow.conditions import SafeConditionEvaluator


class WorkflowService:
    """Enterprise Workflow Orchestration Service managing workflow definitions and execution state."""

    @staticmethod
    def _validate_step_definitions(steps: List[WorkflowStepCreate]) -> None:
        """Enforce strict security validation on step definitions."""
        used_output_keys = set()
        for idx, step in enumerate(steps):
            # 1. Output key uniqueness check
            if step.output_key in used_output_keys:
                raise WorkflowValidationError(
                    f"Duplicate output key '{step.output_key}' detected at step {idx + 1}."
                )
            used_output_keys.add(step.output_key)

            # 2. Check for arbitrary code / SQL / Python keywords in configuration
            raw_cfg_str = str(step.configuration).lower()
            forbidden_tokens = ["eval(", "exec(", "subprocess", "import ", "drop table", "select * from users", "union select"]
            for tok in forbidden_tokens:
                if tok in raw_cfg_str:
                    raise WorkflowValidationError(f"Forbidden code/injection pattern detected in step '{step.name}': '{tok}'")

            # 3. Validate condition syntax if present
            if step.condition:
                try:
                    # Dry-run evaluation on empty dict to check syntax
                    SafeConditionEvaluator.evaluate(step.condition, {})
                except Exception as e:
                    raise WorkflowValidationError(f"Invalid condition in step '{step.name}': {str(e)}")

    @classmethod
    async def create_workflow(
        cls,
        db: AsyncSession,
        organization_id: str,
        created_by: str,
        workflow_in: WorkflowCreate,
    ) -> Workflow:
        """Create a new Workflow in DRAFT status with validated steps."""
        cls._validate_step_definitions(workflow_in.steps)

        workflow_id = str(uuid.uuid4())
        workflow = Workflow(
            id=workflow_id,
            organization_id=organization_id,
            name=workflow_in.name,
            description=workflow_in.description,
            status=WorkflowStatus.DRAFT,
            version=1,
            created_by=created_by,
        )
        db.add(workflow)

        # Add steps
        for idx, step_data in enumerate(workflow_in.steps):
            step = WorkflowStep(
                id=str(uuid.uuid4()),
                workflow_id=workflow_id,
                name=step_data.name,
                type=step_data.type,
                order=step_data.order if step_data.order is not None else idx,
                configuration=step_data.configuration,
                input_mapping=step_data.input_mapping,
                output_key=step_data.output_key,
                timeout_seconds=step_data.timeout_seconds,
                retry_count=step_data.retry_count,
                requires_approval=step_data.requires_approval,
                condition=step_data.condition,
            )
            db.add(step)

        await db.commit()
        return await cls.get_workflow(db, workflow_id, organization_id)

    @classmethod
    async def get_workflow(
        cls,
        db: AsyncSession,
        workflow_id: str,
        organization_id: str,
    ) -> Workflow:
        """Fetch a workflow by ID enforcing strict organization isolation."""
        query = (
            select(Workflow)
            .filter(
                Workflow.id == workflow_id,
                Workflow.organization_id == organization_id,
            )
            .options(selectinload(Workflow.steps))
        )
        res = await db.execute(query)
        wf = res.scalar_one_or_none()
        if not wf:
            raise WorkflowNotFoundError(f"Workflow '{workflow_id}' not found.")
        return wf

    @classmethod
    async def list_workflows(
        cls,
        db: AsyncSession,
        organization_id: str,
        status: Optional[WorkflowStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Workflow], int]:
        """List workflows within an organization with optional status filtering."""
        conditions = [Workflow.organization_id == organization_id]
        if status:
            conditions.append(Workflow.status == status)

        count_query = select(func.count(Workflow.id)).filter(and_(*conditions))
        count_res = await db.execute(count_query)
        total = count_res.scalar() or 0

        items_query = (
            select(Workflow)
            .filter(and_(*conditions))
            .options(selectinload(Workflow.steps))
            .order_by(desc(Workflow.created_at))
            .limit(min(limit, 100))
            .offset(offset)
        )
        items_res = await db.execute(items_query)
        items = list(items_res.scalars().all())

        return items, total

    @classmethod
    async def update_workflow(
        cls,
        db: AsyncSession,
        workflow_id: str,
        organization_id: str,
        workflow_update: WorkflowUpdate,
    ) -> Workflow:
        """Update workflow metadata and steps."""
        wf = await cls.get_workflow(db, workflow_id, organization_id)

        if wf.status == WorkflowStatus.ARCHIVED:
            raise WorkflowStateError("Cannot update an ARCHIVED workflow.")

        if workflow_update.name is not None:
            wf.name = workflow_update.name
        if workflow_update.description is not None:
            wf.description = workflow_update.description

        if workflow_update.steps is not None:
            cls._validate_step_definitions(workflow_update.steps)
            # Remove existing steps
            for existing_step in list(wf.steps):
                await db.delete(existing_step)

            # Insert new steps
            for idx, step_data in enumerate(workflow_update.steps):
                new_step = WorkflowStep(
                    id=str(uuid.uuid4()),
                    workflow_id=wf.id,
                    name=step_data.name,
                    type=step_data.type,
                    order=step_data.order if step_data.order is not None else idx,
                    configuration=step_data.configuration,
                    input_mapping=step_data.input_mapping,
                    output_key=step_data.output_key,
                    timeout_seconds=step_data.timeout_seconds,
                    retry_count=step_data.retry_count,
                    requires_approval=step_data.requires_approval,
                    condition=step_data.condition,
                )
                db.add(new_step)

            wf.version += 1

        await db.commit()
        return await cls.get_workflow(db, workflow_id, organization_id)

    @classmethod
    async def activate_workflow(
        cls,
        db: AsyncSession,
        workflow_id: str,
        organization_id: str,
    ) -> Workflow:
        """Activate a workflow to allow executions."""
        wf = await cls.get_workflow(db, workflow_id, organization_id)
        if not wf.steps:
            raise WorkflowValidationError("Cannot activate a workflow with no steps.")

        wf.status = WorkflowStatus.ACTIVE
        await db.commit()
        await db.refresh(wf)
        return wf

    @classmethod
    async def archive_workflow(
        cls,
        db: AsyncSession,
        workflow_id: str,
        organization_id: str,
    ) -> Workflow:
        """Archive a workflow preventing further executions."""
        wf = await cls.get_workflow(db, workflow_id, organization_id)
        wf.status = WorkflowStatus.ARCHIVED
        await db.commit()
        await db.refresh(wf)
        return wf

    @classmethod
    async def start_execution(
        cls,
        db: AsyncSession,
        workflow_id: str,
        organization_id: str,
        executed_by: str,
        initial_inputs: Dict[str, Any],
    ) -> WorkflowExecution:
        """Initialize a new workflow execution record."""
        wf = await cls.get_workflow(db, workflow_id, organization_id)
        if wf.status != WorkflowStatus.ACTIVE:
            raise WorkflowStateError(f"Cannot execute workflow in status '{wf.status.value}'. Must be ACTIVE.")

        execution = WorkflowExecution(
            id=str(uuid.uuid4()),
            workflow_id=wf.id,
            organization_id=organization_id,
            status=ExecutionStatus.PENDING,
            context_data={"inputs": initial_inputs or {}},
            executed_by=executed_by,
        )
        db.add(execution)
        await db.commit()
        await db.refresh(execution)

        return await cls.get_execution(db, execution.id, organization_id)

    @classmethod
    async def get_execution(
        cls,
        db: AsyncSession,
        execution_id: str,
        organization_id: str,
    ) -> WorkflowExecution:
        """Fetch a workflow execution by ID enforcing tenant isolation."""
        query = (
            select(WorkflowExecution)
            .filter(
                WorkflowExecution.id == execution_id,
                WorkflowExecution.organization_id == organization_id,
            )
            .options(selectinload(WorkflowExecution.step_executions))
        )
        res = await db.execute(query)
        execution = res.scalar_one_or_none()
        if not execution:
            raise WorkflowExecutionNotFoundError(f"Workflow execution '{execution_id}' not found.")
        return execution

    @classmethod
    async def list_executions(
        cls,
        db: AsyncSession,
        workflow_id: str,
        organization_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[WorkflowExecution], int]:
        """List executions for a workflow within an organization."""
        conditions = [
            WorkflowExecution.workflow_id == workflow_id,
            WorkflowExecution.organization_id == organization_id,
        ]

        count_query = select(func.count(WorkflowExecution.id)).filter(and_(*conditions))
        count_res = await db.execute(count_query)
        total = count_res.scalar() or 0

        items_query = (
            select(WorkflowExecution)
            .filter(and_(*conditions))
            .options(selectinload(WorkflowExecution.step_executions))
            .order_by(desc(WorkflowExecution.created_at))
            .limit(min(limit, 100))
            .offset(offset)
        )
        items_res = await db.execute(items_query)
        items = list(items_res.scalars().all())

        return items, total

    @classmethod
    async def pause_execution(
        cls,
        db: AsyncSession,
        execution_id: str,
        organization_id: str,
    ) -> WorkflowExecution:
        """Pause a running workflow execution."""
        execution = await cls.get_execution(db, execution_id, organization_id)
        if execution.status in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED):
            raise InvalidStateTransitionError(f"Cannot pause execution in terminal state '{execution.status.value}'.")

        execution.status = ExecutionStatus.PAUSED
        await db.commit()
        await db.refresh(execution)
        return execution

    @classmethod
    async def resume_execution(
        cls,
        db: AsyncSession,
        execution_id: str,
        organization_id: str,
    ) -> WorkflowExecution:
        """Resume a paused or waiting approval workflow execution."""
        execution = await cls.get_execution(db, execution_id, organization_id)
        if execution.status not in (ExecutionStatus.PAUSED, ExecutionStatus.WAITING_APPROVAL):
            raise InvalidStateTransitionError(
                f"Cannot resume execution with status '{execution.status.value}'. Must be PAUSED or WAITING_APPROVAL."
            )

        execution.status = ExecutionStatus.RUNNING
        await db.commit()
        await db.refresh(execution)
        return execution

    @classmethod
    async def cancel_execution(
        cls,
        db: AsyncSession,
        execution_id: str,
        organization_id: str,
    ) -> WorkflowExecution:
        """Cancel a workflow execution."""
        execution = await cls.get_execution(db, execution_id, organization_id)
        if execution.status in (ExecutionStatus.COMPLETED, ExecutionStatus.CANCELLED):
            raise InvalidStateTransitionError(f"Cannot cancel execution in state '{execution.status.value}'.")

        execution.status = ExecutionStatus.CANCELLED
        execution.completed_at = datetime.now(timezone.utc)

        # Mark any running or waiting step executions as CANCELLED
        for se in execution.step_executions:
            if se.status in (StepExecutionStatus.PENDING, StepExecutionStatus.RUNNING, StepExecutionStatus.WAITING_APPROVAL):
                se.status = StepExecutionStatus.CANCELLED
                se.completed_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(execution)
        return execution


workflow_service = WorkflowService()
