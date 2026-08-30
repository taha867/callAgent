# CallAgent Backend — Running Locally

Phase 0 (governance/foundations) of the Insurance Outbound AI Call Center backend. This
covers how to boot the stack, run the app outside Docker, run tests, and use the tooling
built in this phase. See `.claude/specs/phase-0-backend-spec.md` (repo root) for the design
behind everything here.

## Prerequisites

- Docker + Docker Compose v2 (`docker compose version`)
- Python 3.12 (only needed if you want to run the app or tests outside Docker)

## Quickest path: full stack via Docker Compose

From the **repo root** (not `backend/`):

```bash
docker compose up -d --wait
```

This is the only command required on a clean checkout — no manual `.env` setup, no manual
migration/seed step. It brings up, in order:

| Service | What it is | Host port |
|---|---|---|
| `postgres` | Postgres 16, with the two-role setup applied on first boot | `55432` |
| `redis` | Redis 7 | `56379` |
| `temporal` | Temporal OSS (auto-setup) | `7233` |
| `temporal-ui` | Temporal Web UI | `8080` |
| `migrate` | One-shot: runs Alembic migrations + seeds demo data, then exits | — |
| `backend` | FastAPI app (`uvicorn`, reload on) | `8001` |
| `worker` | Temporal worker process | — |

Host ports are shifted from the Postgres/Redis/uvicorn defaults (`5432`/`6379`/`8000`)
because those are commonly already in use on a dev machine — override with
`POSTGRES_HOST_PORT` / `REDIS_HOST_PORT` / `TEMPORAL_HOST_PORT` / `TEMPORAL_UI_HOST_PORT` /
`BACKEND_HOST_PORT` env vars if you need different ones.

Verify it's up:

```bash
curl -f http://localhost:8001/health          # {"status":"ok"}
docker compose ps                              # migrate should show Exited (0)
open http://localhost:8080                     # Temporal Web UI
```

Tear down:

```bash
docker compose down -v      # -v also drops the postgres volume (fresh DB next time)
```

### Rebuilding after pulling new backend code

`docker compose up` alone does **not** rebuild images just because files on disk changed —
it only builds an image if one doesn't exist yet, otherwise it reuses whatever was last
built. Whenever you pull/switch to a commit that adds or changes backend files (new
migrations especially), rebuild explicitly:

```bash
docker compose up -d --wait --build
```

This matters most for the `migrate` service: unlike `backend` (which bind-mounts
`./backend:/app` and so always runs the current on-disk code), `migrate` has no live mount
and only ever sees whatever was baked into its image at the last build. If the Postgres
volume (which persists across `up`/`down`) has already been migrated to a revision that a
stale `migrate` image doesn't know about — e.g. by another session's local `alembic upgrade
head`, or by rebuilding `backend`/`worker` without also rebuilding `migrate` — you'll see:

```text
FAILED: Can't locate revision identified by '<revision>'
```

Fix: `docker compose build migrate backend worker voice && docker compose up -d --wait`.

**Note on first build:** the very first `docker compose build`/`up` has to `pip install`
everything inside the image, which can be slow depending on your network path into Docker's
build context (this took ~30 min once in a throttled sandbox environment; on a normal
connection it's a couple of minutes). It's a one-time cost — Docker layer-caches the
dependency install, so every subsequent `up`/`build` reuses it unless `requirements/*.txt`
changes.

## Running outside Docker (local dev loop)

Useful for iterating on the app with the compose-provided Postgres/Redis/Temporal but
without rebuilding a Docker image each time.

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements/dev.txt
.venv/bin/python -m spacy download en_core_web_sm   # Phase 3 — privacy/'s Presidio NER pass
cp .env.example .env        # points at the compose services' shifted host ports — no secrets in Phase 0
```

**Phase 3 note:** `requirements/base.txt` installs `presidio-analyzer` but deliberately not
`presidio-anonymizer` (its pinned `cryptography<49.0.0` conflicts with `aiortc`'s — pulled in
by `pipecat-ai[webrtc]` — `cryptography>=49.0.0` requirement; no single `cryptography`
version satisfies both). `privacy/scrubber.py` only needs entity spans from
`AnalyzerEngine.analyze()` and does its own `[CATEGORY_REDACTED]` replacement, so this costs
nothing. The `en_core_web_sm` download above is a separate step from `pip install` — a Docker
image build must run it too (see `Dockerfile`), not just this local-venv path.

Make sure at least `postgres`, `redis`, and `temporal` are up first:

```bash
docker compose up -d postgres redis temporal
```

Then, from `backend/`, with `.env` picked up (`export $(grep -v '^#' .env | xargs)` or use
your editor/IDE's env-file support):

```bash
# apply migrations + seed demo data (idempotent — safe to re-run)
.venv/bin/alembic upgrade head
.venv/bin/python -m scripts.seed_demo_data

# run the API
.venv/bin/uvicorn src.main:app --reload --port 8001

# run the Temporal worker (separate terminal)
.venv/bin/python worker.py
```

## Tests

```bash
cd backend
export $(grep -v '^#' .env | xargs)   # or otherwise load .env
.venv/bin/pytest tests -v
```

This provisions its own throwaway `callagent_test` database automatically (see
`tests/conftest.py`) — it does not touch the `callagent` database used by the running app.
Needs `postgres` up; the Temporal-dependent tests (`tests/integration/`) additionally need
either `temporal` up or network access to download Temporal's local dev server on first use.

Two tests are skipped unless you point them at a live compose stack:

```bash
COMPOSE_SMOKE=1 BACKEND_URL=http://localhost:8001 .venv/bin/pytest tests/integration/test_docker_compose_boot.py -v
```

## Linting / type-checking

```bash
cd backend
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy src        # non-blocking in CI for Phase 0, still worth checking locally
```

## The governance CI gates

Four static-analysis scripts enforce spec §36's rule corpus mechanically — they exit `0`
against clean code and `1` against their fixtures under `tests/fixtures/`:

```bash
cd backend
.venv/bin/python scripts/ci/check_tool_allowlist.py            # LLM tool calls must be in src/voice/tools.py's TOOL_REGISTRY
.venv/bin/python scripts/ci/check_disposition_action_codes.py  # disposition/action code strings must be in the shared enums
.venv/bin/python scripts/ci/check_no_raw_prompt_concat.py       # no raw caller text concatenated into a system/developer prompt
.venv/bin/python scripts/ci/check_transcript_redaction.py       # Phase 3 — record_transcript_turn() must always be fed redact()'s output, never raw text
```

All three run automatically in `.github/workflows/backend-ci.yml` on every PR.

## Migrations

```bash
cd backend
.venv/bin/alembic revision --autogenerate -m "description"   # after changing a models.py
.venv/bin/alembic upgrade head
.venv/bin/alembic downgrade -1                                 # step back one revision
```

Always hand-review an autogenerated migration before applying it — see
`migrations/versions/2026-08-27_initial_schema.py` and the hand-written
`2026-08-27_audit_event_insert_only_grants.py` for the pattern this repo follows.

## Poking at the database directly

```bash
docker compose exec postgres psql -U callagent -d callagent
```

`callagent_app` (the app's runtime role) intentionally cannot `UPDATE`/`DELETE`/`TRUNCATE`
`audit_event` — that's enforced at the database level, not just in application code. Use
`callagent_migrator` (via Alembic, or `psql -U callagent_migrator`) if you ever need to.
