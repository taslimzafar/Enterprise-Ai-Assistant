"""phase_13_evaluation

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-20 03:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. evaluation_runs table
    op.create_table(
        'evaluation_runs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('organization_id', sa.String(), nullable=False),
        sa.Column('dataset_id', sa.String(), nullable=False),
        sa.Column('dataset_version', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='COMPLETED'),
        sa.Column('total_cases', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('passed_cases', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_cases', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('average_correctness', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('average_groundedness', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('average_retrieval_score', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('total_duration_ms', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('total_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_evaluation_runs_organization_id'), 'evaluation_runs', ['organization_id'], unique=False)

    # 2. evaluation_records table
    op.create_table(
        'evaluation_records',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('run_id', sa.String(), nullable=False),
        sa.Column('organization_id', sa.String(), nullable=False),
        sa.Column('dataset_id', sa.String(), nullable=False),
        sa.Column('case_id', sa.String(), nullable=False),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('query', sa.Text(), nullable=False),
        sa.Column('expected_answer', sa.Text(), nullable=True),
        sa.Column('actual_answer', sa.Text(), nullable=True),
        sa.Column('expected_sources', sa.JSON(), nullable=True),
        sa.Column('retrieved_sources', sa.JSON(), nullable=True),
        sa.Column('correctness_score', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('groundedness_score', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('retrieval_score', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('latency_ms', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('token_usage', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='PASSED'),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['run_id'], ['evaluation_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_evaluation_records_organization_id'), 'evaluation_records', ['organization_id'], unique=False)
    op.create_index(op.f('ix_evaluation_records_run_id'), 'evaluation_records', ['run_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_evaluation_records_run_id'), table_name='evaluation_records')
    op.drop_index(op.f('ix_evaluation_records_organization_id'), table_name='evaluation_records')
    op.drop_table('evaluation_records')
    op.drop_index(op.f('ix_evaluation_runs_organization_id'), table_name='evaluation_runs')
    op.drop_table('evaluation_runs')
