"""Phase 4 — qa_defect_log_entry, qa_journey_run_result tables.

Revision ID: 09f8efbe5c0c
Revises: 5df3ac54e432
Create Date: 2026-08-29 12:00:00.000000

Hand-written (no live DB to autogenerate against), following the exact shape of
migrations/versions/2026-08-29_phase3_privacy_pii_redaction_event.py. Both tables are
plain mutable rows (no insert-only grants migration needed) — see src/qa/models.py's
module docstring for why.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '09f8efbe5c0c'
down_revision: str | Sequence[str] | None = '5df3ac54e432'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('qa_defect_log_entry',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('defect_shape_key', sa.String(), nullable=False),
    sa.Column('demo_journey_id', sa.String(), nullable=True),
    sa.Column('adversarial_scenario_id', sa.String(), nullable=True),
    sa.Column('language', sa.String(), nullable=False),
    sa.Column('severity', sa.String(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('occurrence_count', sa.Integer(), nullable=False),
    sa.Column('compiled_artifact_type', sa.String(), nullable=True),
    sa.Column('compiled_artifact_ref', sa.String(), nullable=True),
    sa.Column('first_seen_at', sa.DateTime(), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(), nullable=False),
    sa.Column('notes', sa.String(), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('qa_defect_log_entry_pkey'))
    )
    op.create_index(op.f('qa_defect_log_entry_defect_shape_key_idx'), 'qa_defect_log_entry', ['defect_shape_key'], unique=False)

    op.create_table('qa_journey_run_result',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('demo_journey_id', sa.String(), nullable=False),
    sa.Column('adversarial_scenario_id', sa.String(), nullable=True),
    sa.Column('passed', sa.Boolean(), nullable=False),
    sa.Column('run_at', sa.DateTime(), nullable=False),
    sa.Column('defect_log_entry_id', sa.String(), nullable=True),
    sa.Column('test_node_id', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['defect_log_entry_id'], ['qa_defect_log_entry.id'], name=op.f('qa_journey_run_result_defect_log_entry_id_fkey')),
    sa.PrimaryKeyConstraint('id', name=op.f('qa_journey_run_result_pkey'))
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('qa_journey_run_result')
    op.drop_index(op.f('qa_defect_log_entry_defect_shape_key_idx'), table_name='qa_defect_log_entry')
    op.drop_table('qa_defect_log_entry')
