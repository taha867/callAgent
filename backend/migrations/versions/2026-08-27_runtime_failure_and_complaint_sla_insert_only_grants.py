"""runtime failure and complaint sla insert only grants

Revision ID: d1f6a2c9e8b4
Revises: c3b80a2109d3
Create Date: 2026-08-27 17:19:00.000000

Extends the same REVOKE UPDATE, DELETE, TRUNCATE pattern
migrations/versions/2026-08-27_audit_event_insert_only_grants.py already applies to
audit_event, now to runtime_failure_event and complaint_sla_event — both are append-only
for the same reason audit_event is (spec §26/§32, CLAUDE.md §2.5). See that migration's own
docstring for why TRUNCATE is revoked alongside UPDATE/DELETE, and why the `IF EXISTS`
guard exists.
"""

import os
import re
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd1f6a2c9e8b4'
down_revision: Union[str, Sequence[str], None] = 'c3b80a2109d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ROLE_NAME_PATTERN = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
_TABLES = ("runtime_failure_event", "complaint_sla_event")


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
