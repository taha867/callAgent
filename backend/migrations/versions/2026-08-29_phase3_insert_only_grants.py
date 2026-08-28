"""phase 3 insert only grants

Revision ID: 5df3ac54e432
Revises: 21426cdfb25e
Create Date: 2026-08-29 09:10:00.000000

Extends the same REVOKE UPDATE, DELETE, TRUNCATE pattern
migrations/versions/2026-08-27_audit_event_insert_only_grants.py already applies to
audit_event (and 2026-08-27_runtime_failure_and_complaint_sla_insert_only_grants.py
extended to runtime_failure_event/complaint_sla_event), now to Phase 3's six new
insert-only tables — all append-only for the same reason audit_event is (spec §26/§32,
CLAUDE.md §2.5). See the audit_event migration's own docstring for why TRUNCATE is
revoked alongside UPDATE/DELETE, and why the `IF EXISTS` guard exists.
"""

import os
import re
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '5df3ac54e432'
down_revision: Union[str, Sequence[str], None] = '21426cdfb25e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ROLE_NAME_PATTERN = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
_TABLES = (
    "pii_redaction_event",
    "call_transcript",
    "call_summary",
    "customer_intent",
    "sentiment_event",
    "call_latency_sample",
)


def _app_role() -> str:
    role = os.environ.get("APP_DB_ROLE", "callagent_app")
    if not _ROLE_NAME_PATTERN.fullmatch(role):
        raise ValueError(f"unsafe Postgres role name: {role!r}")
    return role


def upgrade() -> None:
    role = _app_role()
    for table in _TABLES:
        op.execute(f"""
            DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                REVOKE UPDATE, DELETE, TRUNCATE ON TABLE {table} FROM "{role}";
              END IF;
            END $$;
        """)


def downgrade() -> None:
    role = _app_role()
    for table in _TABLES:
        op.execute(f"""
            DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                GRANT UPDATE, DELETE, TRUNCATE ON TABLE {table} TO "{role}";
              END IF;
            END $$;
        """)
