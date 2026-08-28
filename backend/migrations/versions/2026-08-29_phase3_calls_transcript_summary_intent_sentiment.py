"""Phase 3 batch 1 — call_transcript, call_summary, customer_intent, sentiment_event,
call_latency_sample tables.

Revision ID: 21426cdfb25e
Revises: 56806a477c19
Create Date: 2026-08-29 09:05:00.000000

Hand-written (no live DB to autogenerate against), following the exact shape of
migrations/versions/2026-08-27_phase1_calls_verification_actions_complaints.py. All five
tables are insert-only (src/insert_only.py's shared decorator) and FK to call_attempt.id;
call_transcript additionally carries a 3-column UNIQUE constraint guarding against a
duplicated direct-call write (.claude/specs/phase-3-backend-implementation-plan.md
Correction 2).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '21426cdfb25e'
down_revision: Union[str, Sequence[str], None] = '56806a477c19'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('call_transcript',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('call_attempt_id', sa.String(), nullable=False),
    sa.Column('turn_index', sa.Integer(), nullable=False),
    sa.Column('speaker', sa.String(), nullable=False),
    sa.Column('redacted_text', sa.String(), nullable=False),
    sa.Column('language', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['call_attempt_id'], ['call_attempt.id'], name=op.f('call_transcript_call_attempt_id_fkey')),
    sa.PrimaryKeyConstraint('id', name=op.f('call_transcript_pkey')),
    sa.UniqueConstraint('call_attempt_id', 'turn_index', 'speaker', name='call_transcript_call_attempt_id_turn_index_speaker_key')
    )
    op.create_index(op.f('call_transcript_call_attempt_id_idx'), 'call_transcript', ['call_attempt_id'], unique=False)

    op.create_table('call_summary',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('call_attempt_id', sa.String(), nullable=False),
    sa.Column('summary_text', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['call_attempt_id'], ['call_attempt.id'], name=op.f('call_summary_call_attempt_id_fkey')),
    sa.PrimaryKeyConstraint('id', name=op.f('call_summary_pkey'))
    )
    op.create_index(op.f('call_summary_call_attempt_id_idx'), 'call_summary', ['call_attempt_id'], unique=True)

    op.create_table('customer_intent',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('call_attempt_id', sa.String(), nullable=False),
    sa.Column('intent', sa.String(), nullable=False),
    sa.Column('topic', sa.String(), nullable=True),
    sa.Column('summary', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['call_attempt_id'], ['call_attempt.id'], name=op.f('customer_intent_call_attempt_id_fkey')),
    sa.PrimaryKeyConstraint('id', name=op.f('customer_intent_pkey'))
    )
    op.create_index(op.f('customer_intent_call_attempt_id_idx'), 'customer_intent', ['call_attempt_id'], unique=False)

    op.create_table('sentiment_event',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('call_attempt_id', sa.String(), nullable=False),
    sa.Column('turn_index', sa.Integer(), nullable=True),
    sa.Column('sentiment', sa.String(), nullable=True),
    sa.Column('signal', sa.String(), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['call_attempt_id'], ['call_attempt.id'], name=op.f('sentiment_event_call_attempt_id_fkey')),
    sa.PrimaryKeyConstraint('id', name=op.f('sentiment_event_pkey'))
    )
    op.create_index(op.f('sentiment_event_call_attempt_id_idx'), 'sentiment_event', ['call_attempt_id'], unique=False)

    op.create_table('call_latency_sample',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('call_attempt_id', sa.String(), nullable=False),
    sa.Column('turn_index', sa.Integer(), nullable=False),
    sa.Column('latency_ms', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['call_attempt_id'], ['call_attempt.id'], name=op.f('call_latency_sample_call_attempt_id_fkey')),
    sa.PrimaryKeyConstraint('id', name=op.f('call_latency_sample_pkey'))
    )
    op.create_index(op.f('call_latency_sample_call_attempt_id_idx'), 'call_latency_sample', ['call_attempt_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('call_latency_sample_call_attempt_id_idx'), table_name='call_latency_sample')
    op.drop_table('call_latency_sample')
    op.drop_index(op.f('sentiment_event_call_attempt_id_idx'), table_name='sentiment_event')
    op.drop_table('sentiment_event')
    op.drop_index(op.f('customer_intent_call_attempt_id_idx'), table_name='customer_intent')
    op.drop_table('customer_intent')
    op.drop_index(op.f('call_summary_call_attempt_id_idx'), table_name='call_summary')
    op.drop_table('call_summary')
    op.drop_index(op.f('call_transcript_call_attempt_id_idx'), table_name='call_transcript')
    op.drop_table('call_transcript')
