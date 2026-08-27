"""Session-scoped fixtures that provision a dedicated `callagent_test` database, apply the
two-role setup, and run Alembic migrations for real — NEVER Base.metadata.create_all(),
which would silently produce a mutable audit_event and make the immutability tests pass
for the wrong reason.
"""

import asyncio
import os
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_INIT_ROLES_SQL = _BACKEND_DIR / "scripts" / "db" / "00-init-roles.sql"

# Superuser credentials are fixed by docker-compose.yml's POSTGRES_USER/POSTGRES_PASSWORD —
# used here only to provision/drop the dedicated test database, never for app traffic.
_SUPERUSER = "callagent"
_SUPERUSER_PASSWORD = "callagent"
_TEST_DB_NAME = "callagent_test"


def _swap_db(url: str, db_name: str) -> str:
    # str(URL) masks the password (render_as_string(hide_password=True) is the default
    # __str__ behavior) — explicit render_as_string(hide_password=False) is required or
    # every connection attempt authenticates with the literal string "***".
    parsed = make_url(url)
    return parsed.set(database=db_name).render_as_string(hide_password=False)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def migrated_test_db():
    app_url = make_url(str(settings.DATABASE_URL))
    host, port = app_url.host, app_url.port

    # 1. (Re)create the test database as the superuser. CREATE/DROP DATABASE cannot run
    # inside a transaction — raw asyncpg (autocommit by default per-statement), not a
    # SQLAlchemy session.
    admin_conn = await asyncpg.connect(
        user=_SUPERUSER, password=_SUPERUSER_PASSWORD, host=host, port=port, database="postgres"
    )
    try:
        await admin_conn.execute(f'DROP DATABASE IF EXISTS "{_TEST_DB_NAME}" WITH (FORCE)')
        await admin_conn.execute(f'CREATE DATABASE "{_TEST_DB_NAME}" OWNER "{_SUPERUSER}"')
    finally:
        await admin_conn.close()

    # 2. Apply the two-role setup against the new database (idempotent by design — see
    # scripts/db/00-init-roles.sql's own docstring).
    test_admin_conn = await asyncpg.connect(
        user=_SUPERUSER, password=_SUPERUSER_PASSWORD, host=host, port=port, database=_TEST_DB_NAME
    )
    try:
        await test_admin_conn.execute(_INIT_ROLES_SQL.read_text())
    finally:
        await test_admin_conn.close()

    # 3. Run Alembic migrations for real. alembic.command.upgrade is sync and its async
    # env.py calls asyncio.run() internally — calling it directly from a running event
    # loop raises "asyncio.run() cannot be called from a running event loop", so this MUST
    # go through asyncio.to_thread.
    migration_url = _swap_db(settings.migration_url, _TEST_DB_NAME)

    def _run_upgrade() -> None:
        os.environ["APP_DB_ROLE"] = settings.APP_DB_ROLE
        alembic_cfg = AlembicConfig(str(_BACKEND_DIR / "alembic.ini"))
        alembic_cfg.set_main_option("sqlalchemy.url", migration_url)
        # env.py itself overrides sqlalchemy.url from settings.migration_url — force it to
        # the test DB via an env var env.py doesn't otherwise consult, then monkeypatch
        # settings for the duration of this call.
        settings.MIGRATION_DATABASE_URL = migration_url  # type: ignore[assignment]
        command.upgrade(alembic_cfg, "head")

    await asyncio.to_thread(_run_upgrade)

    yield {
        "app_url": _swap_db(str(settings.DATABASE_URL), _TEST_DB_NAME),
        "migration_url": migration_url,
    }

    admin_conn = await asyncpg.connect(
        user=_SUPERUSER, password=_SUPERUSER_PASSWORD, host=host, port=port, database="postgres"
    )
    try:
        await admin_conn.execute(f'DROP DATABASE IF EXISTS "{_TEST_DB_NAME}" WITH (FORCE)')
    finally:
        await admin_conn.close()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db_engine(migrated_test_db):
    engine = create_async_engine(migrated_test_db["app_url"])
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def admin_engine(migrated_test_db):
    """Connects as callagent_migrator — cleanup + the layer-3 audit-immutability test only.
    The app role cannot TRUNCATE audit_event (that is the point of the migration in
    migrations/versions/*_audit_event_insert_only_grants.py)."""
    engine = create_async_engine(migrated_test_db["migration_url"])
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Rollback-isolated via a SAVEPOINT. Use for most unit tests — nothing committed here
    survives the test."""
    async with db_engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()


@pytest_asyncio.fixture
async def db_session_committed(db_engine, admin_engine, monkeypatch):
    """Really commits. Needed by the e2e test (tests/integration/test_phase0_e2e.py):
    the Temporal activity writes through its OWN independent session and would never see
    an uncommitted outer transaction from a rollback-isolated fixture.

    Also monkeypatches src.database.SessionLocal to a sessionmaker bound to the TEST
    engine: get_session_factory() (used by scripts/seed_demo_data.py and
    src/calls/activities.py) reads that module-level name at call time, and by default it
    points at settings.DATABASE_URL — the real `callagent` database, not `callagent_test`.
    Without this, the seed script and the Temporal activity would silently write to the
    wrong database during tests.
    """
    import src.database as database_module

    test_session_factory = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr(database_module, "SessionLocal", test_session_factory)

    session = test_session_factory()
    try:
        yield session
    finally:
        await session.close()
        async with admin_engine.begin() as conn:
            # TRUNCATE, not DELETE: matches the REVOKE'd privilege set exactly, and
            # requires the migrator role — the app role cannot do this (see the migration).
            await conn.execute(
                text(
                    "TRUNCATE audit_event, idempotency_record, motor_claim, "
                    "motor_policy, customer, repair_garage, claim_document, "
                    "claim_status_event, claim_party RESTART IDENTITY CASCADE"
                )
            )


@pytest_asyncio.fixture
async def seeded_db(db_session_committed):
    from scripts.seed_demo_data import main as seed_main

    await seed_main()
    yield db_session_committed


@pytest.fixture
def set_flags(monkeypatch):
    """set_flags(GLOBAL_OUTBOUND_ENABLED=False) — settings is a module-level singleton."""

    def _set(**overrides):
        for key, value in overrides.items():
            monkeypatch.setattr(settings, key, value)

    return _set
