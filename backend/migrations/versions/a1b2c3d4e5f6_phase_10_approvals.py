"""phase_10_approvals

Revision ID: a1b2c3d4e5f6
Revises: e50f0b047ad5
Create Date: 2026-09-20 01:05:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'e50f0b047ad5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create approvals table
    op.create_table(
        'approvals',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('organization_id', sa.String(), nullable=False),
        sa.Column('requested_by_user_id', sa.String(), nullable=False),
        sa.Column('conversation_id', sa.String(), nullable=True),
        sa.Column('message_id', sa.String(), nullable=True),
        sa.Column('tool_name', sa.String(), nullable=False),
        sa.Column('action_type', sa.String(), nullable=False),
        sa.Column('action_arguments', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED', 'CANCELLED', name='approvalstatus'),
            nullable=False,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('approved_by_user_id', sa.String(), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['requested_by_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['approved_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_approvals_id'), 'approvals', ['id'], unique=False)
    op.create_index(op.f('ix_approvals_organization_id'), 'approvals', ['organization_id'], unique=False)
    op.create_index(op.f('ix_approvals_requested_by_user_id'), 'approvals', ['requested_by_user_id'], unique=False)
    op.create_index(op.f('ix_approvals_conversation_id'), 'approvals', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_approvals_status'), 'approvals', ['status'], unique=False)
    op.create_index(op.f('ix_approvals_created_at'), 'approvals', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_approvals_created_at'), table_name='approvals')
    op.drop_index(op.f('ix_approvals_status'), table_name='approvals')
    op.drop_index(op.f('ix_approvals_conversation_id'), table_name='approvals')
    op.drop_index(op.f('ix_approvals_requested_by_user_id'), table_name='approvals')
    op.drop_index(op.f('ix_approvals_organization_id'), table_name='approvals')
    op.drop_index(op.f('ix_approvals_id'), table_name='approvals')
    op.drop_table('approvals')
    sa.Enum(name='approvalstatus').drop(op.get_bind(), checkfirst=False)
