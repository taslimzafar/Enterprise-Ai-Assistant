"""phase_11_workflows

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-20 02:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. workflows table
    op.create_table(
        'workflows',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('organization_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('DRAFT', 'ACTIVE', 'PAUSED', 'ARCHIVED', name='workflowstatus'),
            nullable=False,
        ),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_workflows_id'), 'workflows', ['id'], unique=False)
    op.create_index(op.f('ix_workflows_organization_id'), 'workflows', ['organization_id'], unique=False)
    op.create_index(op.f('ix_workflows_status'), 'workflows', ['status'], unique=False)
    op.create_index(op.f('ix_workflows_created_at'), 'workflows', ['created_at'], unique=False)

    # 2. workflow_steps table
    op.create_table(
        'workflow_steps',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('workflow_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column(
            'type',
            sa.Enum('KNOWLEDGE_SEARCH', 'CALCULATOR', 'ORGANIZATION_STATS', 'DEMO_NOTE', 'LLM_GENERATION', name='steptype'),
            nullable=False,
        ),
        sa.Column('order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('configuration', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('input_mapping', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('output_key', sa.String(), nullable=False),
        sa.Column('timeout_seconds', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('requires_approval', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('condition', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_workflow_steps_id'), 'workflow_steps', ['id'], unique=False)
    op.create_index(op.f('ix_workflow_steps_workflow_id'), 'workflow_steps', ['workflow_id'], unique=False)
    op.create_index(op.f('ix_workflow_steps_order'), 'workflow_steps', ['order'], unique=False)

    # 3. workflow_executions table
    op.create_table(
        'workflow_executions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('workflow_id', sa.String(), nullable=False),
        sa.Column('organization_id', sa.String(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('PENDING', 'RUNNING', 'WAITING_APPROVAL', 'PAUSED', 'COMPLETED', 'FAILED', 'CANCELLED', name='executionstatus'),
            nullable=False,
        ),
        sa.Column('context_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('executed_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['executed_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_workflow_executions_id'), 'workflow_executions', ['id'], unique=False)
    op.create_index(op.f('ix_workflow_executions_workflow_id'), 'workflow_executions', ['workflow_id'], unique=False)
    op.create_index(op.f('ix_workflow_executions_organization_id'), 'workflow_executions', ['organization_id'], unique=False)
    op.create_index(op.f('ix_workflow_executions_status'), 'workflow_executions', ['status'], unique=False)
    op.create_index(op.f('ix_workflow_executions_created_at'), 'workflow_executions', ['created_at'], unique=False)

    # 4. workflow_step_executions table
    op.create_table(
        'workflow_step_executions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('execution_id', sa.String(), nullable=False),
        sa.Column('step_id', sa.String(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('PENDING', 'RUNNING', 'WAITING_APPROVAL', 'COMPLETED', 'FAILED', 'SKIPPED', 'CANCELLED', name='stepexecutionstatus'),
            nullable=False,
        ),
        sa.Column('inputs', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('outputs', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('retry_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('approval_id', sa.String(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['execution_id'], ['workflow_executions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['step_id'], ['workflow_steps.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['approval_id'], ['approvals.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_workflow_step_executions_id'), 'workflow_step_executions', ['id'], unique=False)
    op.create_index(op.f('ix_workflow_step_executions_execution_id'), 'workflow_step_executions', ['execution_id'], unique=False)
    op.create_index(op.f('ix_workflow_step_executions_step_id'), 'workflow_step_executions', ['step_id'], unique=False)
    op.create_index(op.f('ix_workflow_step_executions_status'), 'workflow_step_executions', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_workflow_step_executions_status'), table_name='workflow_step_executions')
    op.drop_index(op.f('ix_workflow_step_executions_step_id'), table_name='workflow_step_executions')
    op.drop_index(op.f('ix_workflow_step_executions_execution_id'), table_name='workflow_step_executions')
    op.drop_index(op.f('ix_workflow_step_executions_id'), table_name='workflow_step_executions')
    op.drop_table('workflow_step_executions')
    sa.Enum(name='stepexecutionstatus').drop(op.get_bind(), checkfirst=False)

    op.drop_index(op.f('ix_workflow_executions_created_at'), table_name='workflow_executions')
    op.drop_index(op.f('ix_workflow_executions_status'), table_name='workflow_executions')
    op.drop_index(op.f('ix_workflow_executions_organization_id'), table_name='workflow_executions')
    op.drop_index(op.f('ix_workflow_executions_workflow_id'), table_name='workflow_executions')
    op.drop_index(op.f('ix_workflow_executions_id'), table_name='workflow_executions')
    op.drop_table('workflow_executions')
    sa.Enum(name='executionstatus').drop(op.get_bind(), checkfirst=False)

    op.drop_index(op.f('ix_workflow_steps_order'), table_name='workflow_steps')
    op.drop_index(op.f('ix_workflow_steps_workflow_id'), table_name='workflow_steps')
    op.drop_index(op.f('ix_workflow_steps_id'), table_name='workflow_steps')
    op.drop_table('workflow_steps')
    sa.Enum(name='steptype').drop(op.get_bind(), checkfirst=False)

    op.drop_index(op.f('ix_workflows_created_at'), table_name='workflows')
    op.drop_index(op.f('ix_workflows_status'), table_name='workflows')
    op.drop_index(op.f('ix_workflows_organization_id'), table_name='workflows')
    op.drop_index(op.f('ix_workflows_id'), table_name='workflows')
    op.drop_table('workflows')
    sa.Enum(name='workflowstatus').drop(op.get_bind(), checkfirst=False)
