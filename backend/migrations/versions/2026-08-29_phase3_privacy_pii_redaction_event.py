"""Phase 3 batch 1 — pii_redaction_event table.

Revision ID: 56806a477c19
Revises: 9e2f4a7c1b6d
Create Date: 2026-08-29 09:00:00.000000

Hand-written (no live DB to autogenerate against), following the exact shape of
migrations/versions/2026-08-27_phase1_runtime_failure_event.py — a single insert-only
table, indexed on call_id (not an FK — see src/privacy/models.py's module docstring).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '56806a477c19'
down_revision: Union[str, Sequence[str], None] = '9e2f4a7c1b6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('pii_redaction_event',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('call_id', sa.String(), nullable=False),
    sa.Column('turn_index', sa.Integer(), nullable=False),
    sa.Column('category', sa.Enum('EMIRATES_ID', 'PASSPORT_NUMBER', 'DATE_OF_BIRTH', 'IBAN', 'CARD_NUMBER', 'OTP_PIN_CVV_PASSWORD', 'PHONE_NUMBER', 'EMAIL_ADDRESS', 'PHYSICAL_ADDRESS', 'POLICY_CLAIM_ID', 'PERSON_NAME', name='pii_category', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('detector', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pii_redaction_event_pkey'))
    )
    op.create_index(op.f('pii_redaction_event_call_id_idx'), 'pii_redaction_event', ['call_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('pii_redaction_event_call_id_idx'), table_name='pii_redaction_event')
    op.drop_table('pii_redaction_event')
