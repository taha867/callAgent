"""Phase 2 — call_session.language column (spec §2.2.3).

Revision ID: 9e2f4a7c1b6d
Revises: d1f6a2c9e8b4
Create Date: 2026-08-28 00:00:00.000000

Additive only, hand-reviewed per CLAUDE.md §2.5 — a single NOT NULL column with a server
default so the migration applies cleanly against existing rows.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9e2f4a7c1b6d'
down_revision: Union[str, None] = 'd1f6a2c9e8b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'call_session',
        sa.Column('language', sa.String(), nullable=False, server_default='en'),
    )


def downgrade() -> None:
    op.drop_column('call_session', 'language')
