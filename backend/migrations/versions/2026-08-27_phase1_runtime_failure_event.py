"""Phase 1 batch 3 — runtime_failure_event table.

Revision ID: c3b80a2109d3
Revises: 7fa61b4aba36
Create Date: 2026-08-27 17:18:16.321404

Hand-reviewed per CLAUDE.md §2.5: autogenerate also proposed dropping and recreating five
CHECK constraints on unrelated tables (call_attempt.disposition_code, claim_action.action_code,
motor_claim/claim_status_event.claim_stage) — the same Enum(native_enum=False) autogenerate
false positive documented in the two preceding migrations. Removed below; this migration
touches only runtime_failure_event.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3b80a2109d3'
down_revision: Union[str, Sequence[str], None] = '7fa61b4aba36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('runtime_failure_event',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('call_id', sa.String(), nullable=True),
    sa.Column('component', sa.String(), nullable=False),
    sa.Column('failure_type', sa.String(), nullable=False),
    sa.Column('recovery_action', sa.String(), nullable=False),
    sa.Column('consumed_retry_attempt', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('runtime_failure_event_pkey'))
    )
    op.create_index(op.f('runtime_failure_event_call_id_idx'), 'runtime_failure_event', ['call_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('runtime_failure_event_call_id_idx'), table_name='runtime_failure_event')
    op.drop_table('runtime_failure_event')
