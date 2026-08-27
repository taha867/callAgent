-- Two-role Postgres setup: `callagent_migrator` owns the schema and is the only role
-- Alembic ever connects as; `callagent_app` is the runtime role FastAPI/worker.py/
-- seed_demo_data.py connect as. The audit-immutability migration
-- (migrations/versions/*_audit_event_insert_only_grants.py) later narrows callagent_app's
-- privileges on audit_event specifically — this file is what makes that REVOKE meaningful,
-- by first granting callagent_app broad default privileges on everything else.
--
-- Idempotent and free of psql meta-commands (no \connect) on purpose: it is consumed two
-- ways — mounted at /docker-entrypoint-initdb.d/ in docker-compose (runs once, against
-- $POSTGRES_DB) and applied explicitly via `psql -f` in CI, where GitHub Actions service
-- containers cannot mount volumes. Safe to re-run against an already-initialized database.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'callagent_migrator') THEN
        CREATE ROLE callagent_migrator LOGIN PASSWORD 'callagent_migrator';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'callagent_app') THEN
        CREATE ROLE callagent_app LOGIN PASSWORD 'callagent_app';
    END IF;
END
$$;

-- The migrator owns the schema; Postgres 15+ no longer lets non-owners CREATE in `public`.
ALTER SCHEMA public OWNER TO callagent_migrator;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- current_database() so this script works unmodified against both the primary `callagent`
-- database and a `callagent_test` database (see tests/conftest.py) without hardcoding a name.
DO $$
BEGIN
    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO callagent_app, callagent_migrator',
        current_database()
    );
END
$$;

GRANT USAGE ON SCHEMA public TO callagent_app;

-- Tables the migrator creates from now on (every Alembic migration) are readable/writable
-- by the app role by default.
ALTER DEFAULT PRIVILEGES FOR ROLE callagent_migrator IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO callagent_app;
ALTER DEFAULT PRIVILEGES FOR ROLE callagent_migrator IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO callagent_app;

-- Backfill for anything already present (makes re-running this script against a populated
-- database a correct no-op rather than a partial grant).
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO callagent_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO callagent_app;
