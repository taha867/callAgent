# CLAUDE.md — Coding Standards & Architecture

This file governs *how* code gets written in this repo. `IMPLEMENTATION_PLAN.md` governs
*what* gets built and in which phase. `Insurance_Outbound_AI_Call_Center_Motor_MVP_Developer_Spec_v1_3.md`
is the functional/compliance source of truth both of those are derived from — read all
three, but in that order: the spec tells you *why* a rule exists, the plan tells you *which
phase* it belongs to, this file tells you the *shape* the code for it should take.

Stack: **FastAPI** (backend, `src/`-layout per `zhanymkanov/fastapi-best-practices`) ·
**PostgreSQL** via **SQLAlchemy 2.0 (async)** · **Pydantic v2** (backend validation) ·
**Temporal.io** (durable call-state workflows, Python SDK) · **Pipecat** (real-time
STT↔LLM↔TTS voice pipeline) · **React 19 + Vite** (frontend) · **React Router v7** ·
**TanStack Query v5** · **react-hook-form + Yup** (frontend validation) · **shadcn/ui**
(Radix + Tailwind v4) · **react-hot-toast** · **jwt-decode**.

Sources for the patterns below: official FastAPI docs (`fastapi.tiangolo.com`),
`zhanymkanov/fastapi-best-practices`, official React docs (`react.dev`), Pydantic v2 docs,
Yup (`jquense/yup`), SQLAlchemy 2.0 async docs, Temporal Python SDK docs, Pipecat docs —
fetched via Context7, not memorized. When in doubt about a library detail, re-fetch rather
than guess; these libraries move.

This is a two-app repo, split at the root — nothing backend-related belongs under
`frontend/`, and nothing frontend-related belongs under `backend/`:

```
CallAgent/                                              # repo root
├── Insurance_Outbound_AI_Call_Center_Motor_MVP_Developer_Spec_v1_3.md   # why — the compliance/functional spec
├── IMPLEMENTATION_PLAN.md                                              # what, and which phase
├── CLAUDE.md                                                           # this file — how
├── backend/                                                            # FastAPI + Temporal + Pipecat — full tree in §2.1
└── frontend/                                                           # React ops dashboard — full tree in §3.2–3.3
```

Every backend tree in §2 starts *inside* `backend/`; every frontend tree in §3 starts
*inside* `frontend/`. The two apps talk to each other over HTTP only
(`frontend/src/middleware/fetchClient.js` → `VITE_API_BASE_URL` → the FastAPI app) — no
shared imports, no reaching across the boundary. The frontend never talks to Temporal, the
telephony/voice pipeline, or the STT/LLM/TTS vendors directly — it only ever sees the
backend's REST API and (for live-call monitoring) a read-only event stream the backend
exposes. This is deliberate: the dashboard is an **observer and configurator** of the
call system, never a participant in a live call's decision-making.

---

## 1. Architecture overview

This system has two request shapes, not one, and they're both real — don't force the
live-call path into the CRUD shape or vice versa.

**Shape A — Ops dashboard (CRUD/config/reporting):**

```
React component ──> React Query hook ──> API client ──> FastAPI router ──> service ──> SQLAlchemy model ──> PostgreSQL
     ▲                                         │
     └──────────── Yup validates ──────────────┘   (client-side, UX only)
                                                          Pydantic validates (server-side, the real gate)
```

**Shape B — Live call (the actual product):**

```
Telephony / browser audio
   ↓
Pipecat pipeline: STT adapter (streaming)
   ↓
LLM tool-use call — Pydantic-validated, allow-listed tool schema ONLY (spec §2.2.2)
   ↓
Temporal workflow (Master Call State Machine, spec §3) — decides the next state deterministically
   ↓
Domain service (idempotent, Pydantic-validated) ──> SQLAlchemy model ──> PostgreSQL
   ↓
Engine hands the LLM only the approved facts it selected — never raw DB access
   ↓
LLM phrases the response from those facts only
   ↓
TTS adapter (streaming) ──> audio out
   ↓
Every step above also emits a row into `audit.AuditEvent` (or a more specific event table) —
this is what the dashboard's Shape-A path later reads.
```

**Validation happens twice on the dashboard path, on purpose, and they are not equal.** Yup
on the frontend exists so an ops user gets an inline error before a network round-trip — a
courtesy. Pydantic on the backend is the actual gate; it re-validates everything as if the
frontend didn't exist, because a future script, a curl call, or a bug in a form should
never be able to write bad data. Never relax a Pydantic constraint "because Yup already
checks it."

**The live-call path has its own, stricter version of the same idea.** The LLM is the
"frontend" of Shape B — it produces intent, not truth. The Temporal workflow + Pydantic-
validated tool schema is the real gate: the LLM can only call functions the schema
declares, those functions are the *only* way anything customer-impacting happens, and the
workflow — not the model — decides whether a call transition is permitted. Never let a
"the LLM already asked for verification" assumption substitute for the workflow actually
checking `verification_level`. This is spec §36 rule 1 ("no authentication bypass by LLM")
translated into code shape, and it is the single most important rule in this file.

**Backend request lifecycle (Shape A — dashboard endpoints), every endpoint, no exceptions:**

1. `APIRouter` route receives the request; path/query params and body are typed with
   Pydantic `Create`/`Update` schemas — invalid input never reaches your function body.
2. `Depends()` injects a database session and the current ops user (auth, once wired).
3. The router calls a **service function** — the router itself contains no business logic,
   only orchestration (call service, translate service errors to `HTTPException`, return
   the `Read` schema).
4. The service function talks to SQLAlchemy models (for config/reporting domains) or
   signals/queries a **Temporal workflow** (for anything that touches an in-flight or
   historical call's state) and returns plain Python objects/ORM instances.
5. FastAPI serializes the return value through the endpoint's `response_model` — this is
   also a second, cheap defense against ever leaking a field you didn't mean to (an
   internal risk score, a redaction-pipeline internal token).

**Live-call lifecycle (Shape B), every call attempt, no exceptions:** see the diagram
above. The concrete rule for developers: **a domain service function that is reachable from
the live-call path must be idempotent and must accept an idempotency key** (spec §10.6.4) —
this is enforced mechanically, see `src/idempotency.py` in §2.1. A Temporal workflow itself
must stay deterministic (no direct network calls, no `datetime.now()` — use
`workflow.now()`); all side effects (DB writes, vendor calls) happen in **activities**, which
Temporal retries safely because they're idempotent by the rule above.

Keeping business logic in services (never routers, never workflows directly) is what makes
the generic CRUD engine from `IMPLEMENTATION_PLAN.md`'s config/lookup entities possible:
transactional endpoints (complaints, escalations, callbacks) are hand-written services;
lookup-table endpoints (CLI configurations, contact-calendar entries, knowledge articles,
disposition-code catalog) are the *same* generic service parameterized by model, reused
across every dynamic CRUD screen.

**Frontend data lifecycle**, every screen (see §3 for why it's split this many ways):

1. A **page** (`pages/`) renders a route and nothing else — no data fetching, no business
   logic.
2. A **container** (`containers/`) does the route-level work: reads/validates URL params,
   sets up Suspense/error boundaries, and composes the domain components that make up the
   screen.
3. **Domain components** (`components/<domain>/`) render the UI and hold local/
   presentational state; forms among them use **react-hook-form** with a **Yup** resolver.
4. **Domain hooks** (`hooks/<domain>Hooks/`) are the only things allowed to call TanStack
   Query — `*Queries.js` for reads, `*Mutations.js` for writes — and they're what
   components actually import.
5. **Domain services** (`services/<domain>Service.js`) are the only things allowed to know
   an API shape — pure functions, no React, no hooks — called exclusively by the hooks
   layer.
6. **One shared `middleware/fetchClient.js`** is the only thing allowed to call `fetch` —
   every service routes through it, which is what makes the 401-refresh-and-retry logic and
   toast notifications exist in exactly one place instead of every service reimplementing
   them.
7. A Yup schema that mirrors the backend's Pydantic `Create`/`Update` schema field-for-field
   guards the form before any of this runs — same required fields, same string lengths,
   same numeric bounds. If a Pydantic constraint changes, the matching Yup schema changes
   in the same commit.

---

## 2. Backend

### 2.1 Folder structure

This uses the domain-package layout documented in `zhanymkanov/fastapi-best-practices`
("FastAPI Best Practices and Conventions", explicitly modeled on Netflix's Dispatch) —
**every domain package carries its own full slice**: router, schemas, models, service,
dependencies, constants, exceptions, and (where the domain owns a durable process)
`workflows.py`/`activities.py`. Cross-domain, framework-wide concerns live as flat modules
directly under `src/`, sitting beside the domain packages rather than nested under a
`core/`.

Domain packages map directly onto the architecture diagram in spec §2 — each node in that
diagram is a package here:

```
backend/
├── migrations/                    # `alembic init -t async migrations` — async template, see §2.5
│   ├── versions/
│   │   └── 2026-08-27_add_complaint_sla_fields.py   # descriptive date-based filenames, not Alembic's hash
│   ├── env.py
│   └── script.py.mako
├── src/
│   ├── auth/                      # ops-dashboard staff Users — login/refresh-token issuance.
│   │                               #   Distinct from customer verification (that's verification/): this is
│   │                               #   RBAC for human staff — ops agent, compliance officer, SIU reviewer,
│   │                               #   complaint owner — who log into the dashboard, not who calls in.
│   ├── customers/                  # Customer, CustomerContactPreference, CustomerAuthFactor,
│   │                               #   CommunicationSuppression — ONE customer record, referenced by id from
│   │                               #   every other domain. No domain owns a duplicate customer profile.
│   ├── claims/                     # MotorPolicy, MotorClaim, ClaimStatusEvent, ClaimDocument, ClaimParty,
│   │                               #   RepairGarage — the Authoritative Data Layer (spec §2.3). MVP owns this
│   │                               #   data directly (synthetic demo claims); production becomes a read-through
│   │                               #   proxy/cache in front of the insurer's real Claims API, not the system of
│   │                               #   record — keep the service interface stable so that swap doesn't ripple.
│   ├── campaigns/                  # OutboundCampaign, CallJob — pre-call trigger + the no-answer/retry
│   │                               #   scheduler workflow (spec §6) as a Temporal workflow keyed by call_job_id
│   │   ├── router.py
│   │   ├── schemas.py
│   │   ├── models.py
│   │   ├── service.py
│   │   ├── workflows.py          # RetrySchedulerWorkflow — durable timers for attempt 2/3, critical-status override
│   │   ├── activities.py         # side-effecting steps the workflow calls (send SMS, create human follow-up task)
│   │   ├── dependencies.py
│   │   ├── constants.py
│   │   └── exceptions.py
│   ├── telephony/                  # TelephonyCliConfiguration, BusinessContactCalendar, DistributedVoiceLock —
│   │                               #   the pre-call gate (spec §4/§4.1, architecture node Q). CLI is NEVER chosen
│   │                               #   at the app/model level — this package is the only place that validates it.
│   ├── calls/                      # CallAttempt, CallSession, CallEvent, CallTranscript, CallSummary,
│   │                               #   CustomerIntent, SentimentEvent — owns the Master Call State Machine
│   │                               #   (spec §3) as a Temporal workflow, one per call attempt, workflow ID
│   │                               #   derived from customer_id so a second workflow for the same customer is
│   │                               #   REJECTED by Temporal itself — this is the distributed voice lock (spec
│   │                               #   §4.1), not a separate lock service.
│   │   ├── router.py             # mostly read endpoints (GET call session/events/transcript) — mutation
│   │   │                          #   happens via workflow signals, not PUT/PATCH
│   │   ├── schemas.py
│   │   ├── models.py
│   │   ├── service.py
│   │   ├── workflows.py          # CallSessionWorkflow — the state machine from spec §3, signals for every
│   │   │                          #   global interrupt in spec §3.1 (HUMAN_REQUEST, CALL_DROPPED, etc.)
│   │   ├── activities.py         # persist CallEvent, fetch claim status, request verification, etc.
│   │   ├── dependencies.py       # valid_call_session — see §2.2
│   │   ├── constants.py          # disposition codes (spec §24), state names
│   │   └── exceptions.py
│   ├── verification/                # VerificationAttempt, OtpChallenge — Level 0/1/2 auth engine (spec §10),
│   │                               #   MAX_AUTH_ATTEMPTS / OTP TTL / resend-cooldown / lockout state machine.
│   │                               #   Reads CustomerAuthFactor from customers/ by id; verification_level lives
│   │                               #   on CallSession, NOT on Customer — auth authority expires when the call
│   │                               #   session ends (spec §10.6.3), so it can never be a Customer-row property.
│   ├── voice/                       # NOT a database domain — the real-time Pipecat pipeline + vendor adapters.
│   │                               #   See §2.6. This is where architecture nodes G (Conversation/LLM Engine),
│   │                               #   O (Input Guard/Prompt Injection Detection), and P (PII-Minimised Context
│   │                               #   Builder) live.
│   │   ├── pipeline.py            # Pipecat pipeline assembly: STT -> guard -> LLM tool-use -> TTS
│   │   ├── tools.py               # the allow-listed LLM tool schema (spec §2.2.2) — the literal enforcement
│   │   │                          #   point of "the LLM cannot create its own authority"
│   │   ├── guard.py               # adversarial-input classifier -> ADVERSARIAL_INPUT_DETECTED signal only,
│   │   │                          #   never a state transition (spec §2.2.2 rule 5)
│   │   ├── adapters/
│   │   │   ├── stt/               # base.py (Protocol) + whisper.py, deepgram.py — swappable per IMPLEMENTATION_PLAN.md
│   │   │   ├── tts/               # base.py + piper.py, elevenlabs.py, azure.py
│   │   │   ├── llm/                # base.py + gemini.py, groq.py, claude.py
│   │   │   └── telephony/          # base.py + browser_webrtc.py (demo), twilio.py (production)
│   │   └── config.py              # VoiceConfig(BaseSettings) — STT_PROVIDER/TTS_PROVIDER/LLM_PROVIDER/
│   │                              #   TELEPHONY_PROVIDER + provider API keys, see §2.7
│   ├── actions/                     # ClaimAction, Escalation, Callback — Action & Escalation Service +
│   │                               #   Callback Scheduler (architecture nodes J and L)
│   ├── complaints/                  # Complaint, ComplaintSlaEvent — Complaint Service (node K) + the SLA
│   │                               #   clock (spec §18.1). acknowledgment_due_at/resolution_due_at are computed
│   │                               #   deterministically by service.py from insurer policy at creation — NEVER
│   │                               #   by the LLM — and monitored by a Temporal workflow that fires
│   │                               #   COMPLAINT_SLA_AT_RISK / COMPLAINT_SLA_BREACHED on durable timers.
│   ├── risk/                        # FraudRoutingEvent, VulnerabilityRoutingEvent, LegalSensitivityEvent,
│   │                               #   EvidencePreservationRequest, LegalHold — Fraud/Vulnerability/Legal-
│   │                               #   Sensitivity Router (node T). Restricted RBAC: only SIU/Legal/Compliance
│   │                               #   roles (see auth/) can read the contents of this package's tables.
│   ├── privacy/                     # PrivacyRequest (DSAR), RecordingConsent, PiiRedactionEvent — recording/
│   │                               #   transcription disclosure (spec §7.1), DSAR routing (Type D.1), and the
│   │                               #   redaction pipeline's event log (spec §28)
│   ├── knowledge/                   # KnowledgeArticle — Knowledge/FAQ Service (node I)
│   ├── audit/                       # AuditEvent, SecurityEvent, AccessibilityRoutingEvent,
│   │                               #   RuntimeFailureEvent, DependencyHealthEvent — append-only, INSERT ONLY.
│   │                               #   Every other domain imports INTO audit/ to post an event; audit/ never
│   │                               #   imports them back. Same role as a `ledger/` package in a financial
│   │                               #   system: what keeps it trustworthy as the compliance audit trail (spec
│   │                               #   §32) is that nothing downstream can reinterpret or mutate it.
│   ├── middlewares/                 # ASGI/HTTP middleware — cross-cutting, runs before any router. See §2.3
│   │   ├── __init__.py            # register_middlewares(app) — the single call main.py makes
│   │   ├── cors.py
│   │   ├── request_context.py     # request-id generation + injection, for log/audit correlation
│   │   └── logging.py
│   ├── config.py                  # global Config(BaseSettings) — DATABASE_URL, CORS, ENVIRONMENT,
│   │                              #   TEMPORAL_HOST, global kill-switch flags (GLOBAL_OUTBOUND_ENABLED etc.)
│   ├── models.py                  # shared DeclarativeBase + Postgres naming-convention metadata
│   ├── exceptions.py               # shared exception base classes, error response schema
│   ├── pagination.py                # shared pagination params/response wrapper
│   ├── idempotency.py               # IdempotencyRecord model + @idempotent decorator/dependency — every
│   │                              #   write reachable from the live-call path (actions/, complaints/,
│   │                              #   privacy/, verification/) goes through this, per spec §10.6.4
│   ├── database.py                 # async engine, async_sessionmaker, get_db() dependency
│   ├── crud.py                     # generic CRUD router/service factory — used by telephony/ CLI configs,
│   │                              #   business-calendar entries, knowledge/ articles, and the disposition/
│   │                              #   action code catalog, exactly the way IMPLEMENTATION_PLAN.md's lookup
│   │                              #   entities are meant to reuse one engine instead of N hand-written CRUDs
│   └── main.py                     # creates FastAPI(), registers middlewares, includes every domain's router
├── worker.py                       # Temporal worker process — registers every domain's workflows/activities
│                                    #   (calls/, campaigns/, complaints/). Runs as a separate deployable process
│                                    #   from main.py's HTTP server; both import the same src/ domain code.
├── voice_server.py                  # Pipecat real-time server — accepts telephony/browser audio, runs
│                                    #   src/voice/pipeline.py, signals into calls/ Temporal workflows as the
│                                    #   conversation progresses. Also a separate process from main.py.
├── requirements/
│   ├── base.txt                   # fastapi, sqlalchemy[asyncio], asyncpg, pydantic, pydantic-settings,
│   │                              #   temporalio, pipecat-ai, alembic, redis, presidio-analyzer,
│   │                              #   presidio-anonymizer — installed everywhere
│   ├── dev.txt                     # + lint tools, imports base.txt
│   └── prod.txt                    # imports base.txt, nothing extra
├── logging.ini
├── alembic.ini                     # script_location = migrations
└── .env                            # never committed
```

Two packages are deliberately one-way, the same principle a `ledger/`/`parties/` split
would use in a financial system:

- **`audit/`** — every other domain imports *into* it (to post an event) but it never
  imports back. That's what keeps it trustworthy as an audit trail rather than something
  every module reads and reinterprets.
- **`customers/`** — `claims/`, `campaigns/`, `calls/`, `complaints/`, `actions/` all
  import `Customer`/`CustomerContactPreference` by id from here; `customers/` never imports
  them. One customer, one record, referenced everywhere — never duplicated per domain.

**Where a lookup/config entity lives**: a lookup table belongs in the domain that primarily
consumes it, not in a domain of its own. `RepairGarage` lives in `claims/` (it's read at
status-delivery time). The exceptions are exactly the two cases above plus `audit/` and
`voice/` — packages that exist specifically because sharing-by-reference (not duplication)
or process-isolation (not a DB table) is the point.

Two details worth keeping deliberately, same reasoning as any FastAPI project at this scale:

- **Give SQLAlchemy's `MetaData` an explicit index/constraint naming convention** in
  `src/models.py`, so every migration produces predictable, greppable constraint names:

```python
# src/models.py
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

POSTGRES_INDEXES_NAMING_CONVENTION = {
    "ix": "%(column_0_label)s_idx",
    "uq": "%(table_name)s_%(column_0_name)s_key",
    "ck": "%(table_name)s_%(constraint_name)s_check",
    "fk": "%(table_name)s_%(column_0_name)s_fkey",
    "pk": "%(table_name)s_pkey",
}

class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=POSTGRES_INDEXES_NAMING_CONVENTION)
```

- **Split `requirements/` by environment** — `dev.txt` pulls in linters/local tooling on
  top of `base.txt`; `prod.txt` stays minimal. Keeps a stray dev-only or demo-only dependency
  (e.g. a local Whisper checkpoint downloader) from ever reaching the production image.

### 2.2 FastAPI conventions

- **Routers are thin.** A router function does exactly three things: validate input (via
  the Pydantic parameter type — already done by the time your code runs), call one service
  function, and return. If a router function is more than ~10 lines, logic has leaked into
  it that belongs in `service.py`.
- **Always set `response_model`** on every route. It's your outbound contract and it
  silently strips fields the schema doesn't declare — an actual safety net (e.g. a
  `risk.FraudRoutingEvent` internal score field must never leak into a response schema an
  ops-agent-role user can call).
- **Use `Depends()` for anything cross-cutting** — the DB session, the current user, the
  outbound kill-switch check, shared pagination params. Don't reconstruct a session or
  re-check a flag inside a route body.
- **Use `Annotated[Type, Depends(...)]`** — the current FastAPI idiom, not the older
  default-value style.
- **One `APIRouter` per domain**, included in `main.py` with its own `prefix` and `tags`:

```python
app.include_router(complaints_router, prefix="/complaints", tags=["complaints"])
app.include_router(calls_router, prefix="/calls", tags=["calls"])
```

- **Raise `HTTPException` from services, not bare exceptions** — or better, raise a domain
  exception in the service and translate it to `HTTPException` in the router, so the
  service layer stays framework-agnostic and testable without spinning up FastAPI (and
  reusable from `worker.py`/`voice_server.py`, which never touch FastAPI at all).
- **Push repeated "does this exist" checks into a dependency**, not into every route body:

```python
# src/calls/dependencies.py
from fastapi import Depends
from src.calls import service
from src.calls.exceptions import CallSessionNotFound

async def valid_call_session(call_id: str) -> CallSession:
    session = await service.get_by_id(call_id)
    if not session:
        raise CallSessionNotFound()
    return session
```

```python
# src/calls/router.py
@router.get("/{call_id}", response_model=CallSessionRead)
async def get_call_session(session: CallSession = Depends(valid_call_session)):
    return session

@router.get("/{call_id}/transcript", response_model=CallTranscriptRead)
async def get_call_transcript(session: CallSession = Depends(valid_call_session)):
    return await service.get_redacted_transcript(session.id)
```

Every route that touches `call_id` reuses `valid_call_session` instead of re-writing the
same "fetch or 404" three times — and the same shape applies to `valid_complaint`,
`valid_customer`, `valid_campaign`, anywhere a route path carries an id.

- **Kill switch is a dependency, not a scattered `if`.** Any endpoint (or activity) that can
  originate an outbound dial goes through `Depends(require_outbound_enabled)`, which checks
  `GLOBAL_OUTBOUND_ENABLED`/`CAMPAIGN_ENABLED`/`CLI_ENABLED`/`AI_AUTOMATION_ENABLED` from
  `src/config.py` (spec §39). One place, checked the same way everywhere, so the kill switch
  can never be accidentally bypassed by a code path that forgot the check.

### 2.3 Middleware

Middleware runs before any router sees the request and after any router produces a response
— it's for concerns that apply to *every* endpoint, not one domain's business logic. Keep
each concern in its own file under `src/middlewares/`, registered from one place:

```python
# src/middlewares/__init__.py
from fastapi import FastAPI
from src.config import settings
from src.middlewares.cors import add_cors_middleware
from src.middlewares.request_context import RequestContextMiddleware
from src.middlewares.logging import AccessLogMiddleware

def register_middlewares(app: FastAPI) -> None:
    # add_middleware() stacks LIFO: the LAST one added runs FIRST on the way in,
    # and LAST on the way out — so request-id must be added last to wrap everything else.
    add_cors_middleware(app, origins=settings.CORS_ORIGINS)
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestContextMiddleware)
```

```python
# src/middlewares/request_context.py
import uuid
from starlette.middleware.base import BaseHTTPMiddleware

class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request.state.request_id = str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response
```

```python
# src/main.py
from fastapi import FastAPI
from src.middlewares import register_middlewares
from src.complaints.router import router as complaints_router

app = FastAPI(title="Insurance Outbound AI Call Center")
register_middlewares(app)
app.include_router(complaints_router, prefix="/complaints", tags=["complaints"])
```

`request_context.py`'s request id isn't a column on `audit.AuditEvent` — it's what a
service writes into the log line alongside a commit, so a specific `AuditEvent` or
`ComplaintSlaEvent` row can be traced back to the dashboard HTTP request that triggered it
via logs, without adding a field to the table itself. The **live-call path has its own
correlation id** — `call_id`/Temporal `workflow_id` — which *is* a column on every table it
touches (`CallEvent`, `AuditEvent`, `ComplaintSlaEvent`), because a call's audit trail must
be reconstructable from the data alone, not just from logs (spec §32).

### 2.4 Pydantic conventions

- **Three schemas per entity, minimum**: `XCreate` (what the client sends to create),
  `XRead` (what the API returns — includes `id`, timestamps, computed fields), `XUpdate`
  (usually every field optional). Never reuse `XCreate` as a response model — that's how
  internal-only fields leak.
- **`XRead` needs `model_config = ConfigDict(from_attributes=True)`** so it can be built
  directly from a SQLAlchemy ORM instance (`XRead.model_validate(db_complaint)`), not a
  manual dict.
- **Use `Annotated[type, Field(...)]` for constraints**, not bare `Field()` defaults, and
  prefer it over ad hoc `@field_validator` when a plain bound will do:

```python
from datetime import datetime
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field

class ComplaintCreate(BaseModel):
    claim_id: str
    complaint_category: Annotated[str, Field(max_length=64)]
    customer_statement_summary: Annotated[str, Field(max_length=2000)]
    customer_expected_resolution: Annotated[str | None, Field(max_length=500)] = None
    severity: Annotated[str, Field(pattern="^(LOW|MEDIUM|HIGH)$")]
    preferred_contact_method: Annotated[str, Field(pattern="^(PHONE|EMAIL|SMS)$")]
    source_call_id: str

class ComplaintRead(ComplaintCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    acknowledgment_due_at: datetime
    resolution_due_at: datetime
    sla_source: str
    status: str

class ComplaintUpdate(BaseModel):
    status: Annotated[str | None, Field(pattern="^(OPEN|ACKNOWLEDGED|RESOLVED)$")] = None
```

- **Reach for `@field_validator` only for cross-field or business-rule checks** a plain
  bound can't express — e.g. "a `Complaint.severity` of `HIGH` must always route to a named
  human owner" is a validator, not a `Field()` constraint.
- **`acknowledgment_due_at`/`resolution_due_at` are never client-supplied** on
  `ComplaintCreate` — they're computed server-side in `service.py` from insurer SLA policy
  at creation time (spec §18.1) and only ever appear on `ComplaintRead`. If a schema lets a
  caller set an SLA deadline directly, that's a bug: the deterministic engine owns that
  clock, not the caller, not the LLM.
- **Money is `Decimal`, never `float`**, on every schema that touches a settlement/payment
  amount pulled from the claims data (spec §13 Journey E) — this system doesn't originate
  financial transactions, but it does report figures from the insurer's core system, and a
  `float` round-trip can still silently corrupt them.

### 2.5 SQLAlchemy (2.0, async) conventions

- **Async engine + `async_sessionmaker`, one session per request**, injected via `Depends`:

```python
# src/database.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

engine = create_async_engine(settings.database_url, echo=settings.debug)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
```

- **Declare models with `Mapped[]` / `mapped_column()`**, the SQLAlchemy 2.0 typed style —
  not the legacy `Column(...)` class-attribute style:

```python
# src/complaints/models.py
from datetime import datetime
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from src.models import Base  # shared DeclarativeBase with the naming convention, not a local one

class Complaint(Base):
    __tablename__ = "complaint"
    id: Mapped[str] = mapped_column(primary_key=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("motor_claim.id"))
    severity: Mapped[str]
    status: Mapped[str] = mapped_column(default="OPEN")
    acknowledgment_due_at: Mapped[datetime]
    resolution_due_at: Mapped[datetime]
    sla_source: Mapped[str]
```

- **Audit/event tables are insert-only.** `audit.AuditEvent`, `calls.CallEvent`,
  `complaints.ComplaintSlaEvent` are never updated or deleted from application code — a
  service function that calls `session.delete()` or mutates a row on one of these models is
  a bug, not a cleanup task. Everything else (`Customer`, `MotorClaim`, `Complaint`'s own
  `status` field) uses a soft-delete/status-transition pattern (`is_active: Mapped[bool]`
  where deactivation makes sense) — history (an old call referencing a since-updated claim
  status) must never break.
- **Wrap writes in `async with session.begin():`** so a partially-applied multi-table write
  (e.g. creating a `Complaint` and its first `ComplaintSlaEvent` in one action) can't commit
  half-finished.
- **Load relationships explicitly with `selectinload`/`joinedload`** on the query that needs
  them — never rely on lazy-load inside an async context, it will throw. This matters most
  for `calls/` (a `CallSession` with its `CallEvent`s and `CallTranscript`) and `claims/` (a
  `MotorClaim` with its `ClaimStatusEvent` history), which are the two places this system's
  queries get genuinely relational.
- **Never call a synchronous ORM session from inside an `async def`.** It blocks the event
  loop and can deadlock the connection pool — this matters even more here than in a typical
  CRUD app, because a blocked event loop during a live call is dead air (spec §2.2.1's P95
  latency budget), not just a slow dashboard page.
- **Migrations live in `migrations/`, not the default `alembic/`.** Set it up with the async
  template: `alembic init -t async migrations`. Use descriptive, date-prefixed revision
  filenames instead of Alembic's default hash. Every schema change is a migration, generated
  and reviewed by eye before applying — autogenerate misses some constraint changes,
  especially around new enum/status values on `Complaint.status` or `CallEvent.event_type`.

### 2.6 Temporal workflows & activities

This is the one structural addition versus a typical FastAPI CRUD app, and it's the backbone
of the whole system per `IMPLEMENTATION_PLAN.md` §1 — the spec's hardest requirements
(distributed voice lock, idempotent writes, crash-safe session recovery, complaint SLA
clocks, no-answer retry scheduling) are what Temporal exists to solve, so don't route around
it with hand-rolled cron jobs or Postgres row locks.

- **One `CallSessionWorkflow` per call attempt**, `workflow_id` derived from `customer_id`.
  Starting a second workflow for the same customer while one is running is rejected by
  Temporal itself — that rejection *is* the distributed voice lock and the
  `CONCURRENT_CALL_CONFLICT` disposition (spec §4.1), not a separate lock table to maintain.
- **Workflows stay deterministic.** No direct DB/HTTP/vendor calls inside `workflows.py` —
  those live in `activities.py` and are called via `workflow.execute_activity(...)`. No
  `datetime.now()`/`random()` inside workflow code — use `workflow.now()`. This is a hard
  Temporal requirement (replay correctness), not a style preference.
- **Activities are the idempotency boundary.** Every activity that performs a
  customer-impacting write accepts (and forwards to the service layer) an idempotency key —
  Temporal's own retry-on-failure semantics plus `src/idempotency.py`'s replay-safe service
  functions together satisfy spec §10.6.4 end to end.
- **Durable timers replace cron for SLA/retry logic.** `campaigns.RetrySchedulerWorkflow`
  sleeps until the next permitted contact window (spec §6.1) using `workflow.sleep(...)`;
  `complaints`'s SLA-monitoring workflow sleeps until the configured warning threshold before
  `acknowledgment_due_at`/`resolution_due_at` and fires `COMPLAINT_SLA_AT_RISK`/
  `COMPLAINT_SLA_BREACHED` — both survive a process restart because Temporal persists
  workflow state, satisfying spec §10.6.2's session-recovery requirement without custom
  checkpointing code.
- **`worker.py` registers every domain's workflows/activities in one place**, the same way
  `main.py` registers every domain's router — one line per domain, nothing more.

### 2.7 Voice pipeline & vendor adapters (Pipecat)

Per `IMPLEMENTATION_PLAN.md` §1's cost strategy, every vendor-backed component (STT, TTS,
LLM, telephony transport) sits behind a swappable adapter so the demo→production vendor
swap in Phase 6 is a config change, not a rewrite. The code shape that enforces this:

```python
# src/voice/adapters/stt/base.py
from typing import Protocol, AsyncIterator

class SpeechToTextAdapter(Protocol):
    async def stream(self, audio: AsyncIterator[bytes]) -> AsyncIterator["Transcript"]: ...
```

Each provider (`whisper.py`, `deepgram.py`) implements the same `Protocol`; `voice/config.py`
picks one by name at process start — nothing in `pipeline.py` imports a provider module
directly. The same pattern applies to `tts/`, `llm/`, and `telephony/`.

```python
# src/voice/config.py
from pydantic_settings import BaseSettings

class VoiceConfig(BaseSettings):
    STT_PROVIDER: str = "whisper"          # "whisper" | "deepgram"
    TTS_PROVIDER: str = "piper"            # "piper" | "elevenlabs" | "azure"
    LLM_PROVIDER: str = "gemini"           # "gemini" | "groq" | "claude"
    TELEPHONY_PROVIDER: str = "browser"    # "browser" | "twilio"
    # provider-specific keys, all optional so demo mode needs none of the paid ones set
    DEEPGRAM_API_KEY: str | None = None
    ELEVENLABS_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None

voice_settings = VoiceConfig()
```

**`voice/tools.py` is the literal enforcement of spec §2.2.2.** It defines the complete,
Pydantic-validated set of functions the LLM is allowed to call (`get_claim_status`,
`create_action`, `schedule_callback`, `request_verification`, …). No adapter, no prompt, no
runtime code path may add a tool the schema doesn't declare. `voice/guard.py`'s adversarial-
input classifier feeds `ADVERSARIAL_INPUT_DETECTED` as a *signal* into the `calls/` workflow
— it never itself changes call state, per spec §2.2.2 rule 5.

### 2.8 Settings & config

Use `pydantic-settings` for `src/config.py` — a `Config(BaseSettings)` class reading from
`.env`, typed, validated at startup (a missing `DATABASE_URL` or `TEMPORAL_HOST` should fail
immediately on boot, not on the first call). Keep it decoupled: global, cross-domain settings
(`DATABASE_URL`, `CORS_ORIGINS`, `ENVIRONMENT`, `TEMPORAL_HOST`, the outbound kill-switch
flags) live in `src/config.py`; a domain that genuinely needs its own settings (`voice/
config.py` above is the clearest example) gets its own small `BaseSettings` subclass instead
of bloating the global one.

```python
# src/config.py
from pydantic import PostgresDsn
from pydantic_settings import BaseSettings

class Config(BaseSettings):
    DATABASE_URL: PostgresDsn
    CORS_ORIGINS: list[str] = []
    ENVIRONMENT: str = "development"
    TEMPORAL_HOST: str = "localhost:7233"
    GLOBAL_OUTBOUND_ENABLED: bool = True
    AI_AUTOMATION_ENABLED: bool = True

settings = Config()
```

---

## 3. Frontend

### 3.1 Stack

React 19 + Vite · React Router v7 · TanStack Query v5 · react-hook-form + Yup resolver ·
shadcn/ui (Radix + Tailwind v4) · react-hot-toast · jwt-decode.

This is a **layered-by-responsibility** structure, not the feature-first one — the layers
(`pages/` → `containers/` → `components/` → `hooks/` → `services/` → `middleware/`) are
fixed and shared by every domain, and *within* each layer things subdivide by domain
(`auth`, `customers`, `claims`, `campaigns`, `calls`, `complaints`, `escalations`,
`callbacks`, `security`, `admin`, `reporting`). The rule of thumb: if you're asking "where
does X live," first find the layer (is it a route? a query? a raw API call?), then find the
domain folder inside it.

### 3.2 Root config

```
frontend/
├── src/
├── index.html
├── vite.config.js        # @/ alias → ./src, react-compiler babel plugin
├── jsconfig.json         # matches @/ alias for editor intellisense
├── tailwind.config.js
├── postcss.config.js
├── components.json       # shadcn/ui config (style: new-york, aliases: @/components, @/lib, @/hooks)
├── eslint.config.js
└── .env                  # VITE_API_BASE_URL, etc. — never committed
```

Use the `@/` alias from the start (`@/components/...`, `@/hooks/...`) — it's wired in
`vite.config.js` and `jsconfig.json` already, and the shadcn CLI generates its output
against it, so there's no reason to fall back to `../../../` relative imports.

### 3.3 `src/` layout

```
src/
├── main.jsx                # ReactDOM.createRoot, wraps App with QueryClientProvider etc.
├── App.jsx                 # all routing lives here: <Routes> with Public / AuthRoute / ProtectedRoute groups
├── index.css                # Tailwind entry + design tokens/CSS variables
│
├── pages/                   # one thin file per route — renders a container, nothing else
│   ├── DashboardPage.jsx           # operations overview + outcome funnel (spec §31), landing page
│   ├── CampaignsPage.jsx / CampaignDetailPage.jsx
│   ├── CallsPage.jsx / CallDetailPage.jsx        # attempt history, live status, redacted transcript, events timeline
│   ├── CustomersPage.jsx / CustomerDetailPage.jsx  # profile + contact preferences + suppression status
│   ├── ClaimsPage.jsx / ClaimDetailPage.jsx        # status timeline, documents, garage
│   ├── ComplaintsPage.jsx / ComplaintDetailPage.jsx  # list + SLA countdown / at-risk / breached indicators
│   ├── EscalationsPage.jsx           # human escalation queue + warm-transfer context viewer
│   ├── CallbacksPage.jsx              # callback scheduling queue
│   ├── AnalyticsPage.jsx               # no-answer / status / customer-experience analytics (spec §31)
│   ├── SecurityReviewPage.jsx           # fraud/SIU + vulnerability + legal-hold review queues (RBAC-gated)
│   ├── AdminPage.jsx                     # kill-switch flags, CLI configs, contact calendar, code catalogs
│   └── AuthPages/
│       ├── SignInPage.jsx
│       ├── SignUpPage.jsx           # ops-staff account creation — RBAC roles: agent/compliance/SIU/complaint-owner
│       ├── ForgotPasswordPage.jsx
│       └── ResetPasswordPage.jsx
│
├── containers/              # route-level orchestration: reads URL params, validates them,
│   │                          sets up Suspense boundaries, composes components together
│   ├── CallDetailContainer.jsx            # callId param -> session + events + transcript
│   ├── ComplaintDetailContainer.jsx        # complaintId param -> complaint + its SLA event history
│   ├── CustomerDetailContainer.jsx         # customerId param -> customer + claims + call history
│   └── DashboardContainer.jsx
│
├── components/              # grouped by domain, plus shared "common"/"custom"/"ui" folders
│   ├── ui/                   # shadcn/ui primitives — generated, rarely hand-edited
│   ├── custom/                # reusable form-field wrappers on top of ui/, wired to react-hook-form
│   │   └── FormField.jsx / FormSelect.jsx / FormDateTimeRange.jsx / index.js   # barrel export
│   ├── common/                 # cross-domain shared components
│   │   ├── ProtectedRoute.jsx / RoleGate.jsx / AuthFallback.jsx / AppInitializer.jsx
│   │   ├── CrudTable.jsx / CrudDrawer.jsx     # the generic config-driven CRUD engine — every lookup screen
│   │   │                                        (CLI configs, contact-calendar entries, knowledge articles,
│   │   │                                        disposition/action code catalog) is this pair plus a config
│   │   │                                        object, not a new page
│   │   ├── PaginationControls.jsx / ConfirmDialog.jsx / ToastNotification.jsx
│   │   ├── SlaCountdown.jsx                   # AT_RISK/BREACHED-aware badge, reused on Complaints + Dashboard
│   │   └── DispositionBadge.jsx                # renders any spec §24 disposition code consistently
│   ├── auth/
│   │   ├── SignIn.jsx / SignUp.jsx / ForgotPassword.jsx / ResetPassword.jsx / AuthLayout.jsx
│   │   └── form/                # SignInForm, SignUpForm, ForgotPasswordForm, ResetPasswordForm
│   ├── customers/
│   │   ├── CustomerList.jsx / CustomerProfile.jsx / SuppressionStatusBadge.jsx
│   │   └── form/                # CustomerContactPreferenceForm.jsx
│   ├── claims/
│   │   ├── ClaimList.jsx / ClaimStatusTimeline.jsx / ClaimDocumentList.jsx
│   ├── campaigns/
│   │   ├── CampaignList.jsx / CampaignDetail.jsx / CallJobTable.jsx
│   │   └── form/                # CampaignForm.jsx
│   ├── calls/
│   │   ├── CallAttemptTimeline.jsx / CallEventLog.jsx / TranscriptViewer.jsx (redaction-aware rendering)
│   │   │   / LatencyMetricsPanel.jsx (P50/P95/P99, spec §2.2.1)
│   ├── complaints/
│   │   ├── ComplaintList.jsx / ComplaintDetail.jsx / ComplaintSlaTimeline.jsx
│   │   └── form/                # ComplaintStatusUpdateForm.jsx
│   ├── escalations/
│   │   ├── EscalationQueue.jsx / WarmTransferContextCard.jsx
│   ├── callbacks/
│   │   ├── CallbackQueue.jsx
│   │   └── form/                # CallbackForm.jsx
│   ├── security/                 # RBAC-gated: fraud/SIU + vulnerability + legal-hold review
│   │   ├── FraudReviewQueue.jsx / VulnerabilitySupportQueue.jsx / LegalHoldQueue.jsx
│   ├── admin/
│   │   ├── KillSwitchPanel.jsx (GLOBAL_OUTBOUND_ENABLED etc.) / CliConfigList.jsx / ContactCalendarList.jsx
│   │   └── form/                # CliConfigForm.jsx, ContactCalendarEntryForm.jsx
│   ├── reporting/
│   │   ├── OutcomeFunnelChart.jsx / NoAnswerAnalytics.jsx / StatusAnalytics.jsx / CustomerExperienceAnalytics.jsx
│   ├── home/Home.jsx
│   ├── Navbar.jsx
│   └── Footer.jsx
│
├── hooks/                   # one subfolder per domain; each domain splits queries vs mutations
│   ├── authHooks/
│   │   ├── authHooks.js          # useAuth() context accessor + derived hooks
│   │   └── authMutations.js      # useSignIn, useSignUp, useSignOut, useRefreshToken
│   ├── customerHooks/      (customerQueries.js, customerMutations.js)
│   ├── claimHooks/          (claimQueries.js — read-only, this domain has no mutations from the dashboard)
│   ├── campaignHooks/      (campaignQueries.js, campaignMutations.js)
│   ├── callHooks/           (callQueries.js — read-only; live-call state changes only via the voice pipeline)
│   ├── complaintHooks/     (complaintQueries.js, complaintMutations.js)
│   ├── escalationHooks/    (escalationQueries.js, escalationMutations.js)
│   ├── callbackHooks/      (callbackQueries.js, callbackMutations.js)
│   ├── securityHooks/       (securityQueries.js, securityMutations.js — RBAC-gated)
│   ├── adminHooks/          (adminQueries.js, adminMutations.js — kill switch, CLI config, calendar)
│   ├── reportingHooks/      (reportingQueries.js — read-only, this domain has no mutations)
│   └── useImperativeDialog.js    # generic reusable hook, not domain-specific
│
├── services/                 # one file per domain — pure API-call functions, no React.
│   │                           each function: build query string -> call fetchClient -> shape/return response.data
│   ├── authService.js
│   ├── customerService.js
│   ├── claimService.js
│   ├── campaignService.js
│   ├── callService.js
│   ├── complaintService.js
│   ├── escalationService.js
│   ├── callbackService.js
│   ├── securityService.js
│   ├── adminService.js
│   └── reportingService.js
│
├── middleware/
│   └── fetchClient.js         # single low-level fetch wrapper for the whole app:
│                                 base URL, auth header injection, 401 → refresh-token-and-retry
│                                 (single-flight refresh lock), timeout via AbortSignal, toast on
│                                 success/error, normalized {data, status, ok, headers} return shape
│
├── contexts/
│   └── authContext.jsx        # React context + provider for current ops user/auth state (incl. RBAC role)
│
├── reducers/
│   └── authReducer.js          # reducer consumed by authContext
│
├── validations/                # one schema file per domain (Yup), imported by forms and containers
│   ├── authSchemas.js
│   ├── customerSchemas.js
│   ├── campaignSchemas.js
│   ├── complaintSchemas.js
│   ├── callbackSchemas.js
│   ├── adminSchemas.js         # cliConfigCreate/Update, contactCalendarEntryCreate/Update
│   └── commonSchemas.js
│
├── utils/                     # pure helper functions, grouped by concern (not by domain necessarily)
│   ├── constants.js             # enums mirroring spec §24/§25: DISPOSITION_CODES, ACTION_CODES,
│   │                              VERIFICATION_LEVEL, COMPLAINT_SEVERITY, HTTP_STATUS, TOAST_MESSAGES
│   ├── queryKeys.js              # centralized TanStack Query key factories per domain
│   │                              (e.g. complaintKeys, callKeys, campaignKeys — each with .all/.lists()/.list()/.detail())
│   ├── queryParams.js             # buildQueryString(options)
│   ├── tokenUtils.js               # getToken/getRefreshToken/storeToken/removeTokens/hasValidRefreshToken
│   └── slaUtils.js, formSubmitWithToast.js   # SLA countdown math mirroring the backend's due-at fields
│
└── lib/
    └── utils.js                 # shadcn's cn() classnames helper (kept separate from utils/, which is app logic)
```

### 3.4 Layering & conventions

1. **Layering is one-directional**: `pages/` (route entry, no logic) → `containers/`
   (param parsing, Suspense/error boundaries, composition) → `components/<domain>/`
   (presentational + local state) → `hooks/<domain>Hooks/` (TanStack Query queries/
   mutations) → `services/<domain>Service.js` (raw API calls) → `middleware/fetchClient.js`
   (the one shared HTTP client). A component never imports a service directly, and a
   service never imports a hook — each layer only talks to the one below it.
2. **Domain-first grouping** inside `components/`, `hooks/`, `services/`, `validations/` —
   each business domain gets its own folder/file so a feature stays co-located; `common/`,
   `custom/`, and `ui/` hold the cross-domain and generic pieces, including the
   `CrudTable`/`CrudDrawer` pair every dynamic lookup screen reuses.
3. **Queries vs. mutations split**: every domain's `hooks/` folder separates read hooks
   (`*Queries.js`) from write hooks (`*Mutations.js`), and mutations always invalidate
   through the centralized `utils/queryKeys.js` factory rather than hand-built key arrays —
   this is what keeps a `CallbackForm` submission correctly invalidating the
   `CallbackQueue` and the `CustomerDetailContainer`'s call-history view it eventually
   feeds, without every mutation needing to know every screen that might be showing stale
   data.
4. **`ui/` vs. `custom/`**: `ui/` is shadcn-generated primitives — don't hand-roll logic
   there, regenerate via the shadcn CLI instead. `custom/` wraps those primitives into
   form-aware components — this is the layer that actually knows about form state.
5. **One fetch client**: every network call funnels through `middleware/fetchClient.js`,
   which centralizes auth headers, 401/refresh-token retry, timeouts, and toast
   notifications. `services/*.js` never call `fetch` directly — if a new service file has a
   raw `fetch(...)` in it, that's a review flag.
6. **RBAC-gated screens** (`SecurityReviewPage`, anything reading `risk/`'s tables) check
   role via `common/RoleGate.jsx` at the component level — the dashboard's role check is a
   UX convenience only, the same way Yup is a courtesy on forms; the backend's `Depends()`
   role check on those routers is the real gate (§2.2), never the frontend alone.

### 3.5 Forms & validation (react-hook-form + Yup)

Forms use **react-hook-form** for field state and submission, with a **Yup** resolver for
validation — not raw `useState`-per-field, and not React 19's `useActionState` for this role
(react-hook-form's `formState.isSubmitting`/`errors` already cover what `useActionState`
would give you, and running both would just be two sources of truth for the same pending/
error state):

```jsx
// components/callbacks/form/CallbackForm.jsx
import { useForm, Controller } from 'react-hook-form';
import { yupResolver } from '@hookform/resolvers/yup';
import { callbackCreateSchema } from '@/validations/callbackSchemas';
import { useCreateCallback } from '@/hooks/callbackHooks/callbackMutations';
import { FormField, FormSelect, FormDateTimeRange } from '@/components/custom';

export function CallbackForm({ customerId, claimId, onSuccess }) {
  const { control, handleSubmit, formState: { errors, isSubmitting } } = useForm({
    resolver: yupResolver(callbackCreateSchema),
    defaultValues: { customerId, claimId, reason: '', callbackDate: null },
  });
  const { mutateAsync: createCallback } = useCreateCallback();

  const onSubmit = async (values) => {
    await createCallback(values);   // fetchClient toasts success/error; mutation invalidates callbackKeys
    onSuccess?.();
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)}>
      <Controller name="callbackDate" control={control} render={({ field }) => (
        <FormDateTimeRange {...field} label="Callback window" error={errors.callbackDate?.message} />
      )} />
      <Controller name="reason" control={control} render={({ field }) => (
        <FormSelect {...field} label="Reason" options={CALLBACK_REASON_OPTIONS} error={errors.reason?.message} />
      )} />
      <button type="submit" disabled={isSubmitting}>Schedule</button>
    </form>
  );
}
```

```javascript
// validations/callbackSchemas.js
import { object, string, date } from 'yup';

export const callbackCreateSchema = object({
  customerId: string().required(),
  claimId: string().required(),
  reason: string().oneOf(['CUSTOMER_DRIVING', 'CUSTOMER_UNAVAILABLE', 'CUSTOMER_REQUESTED']).required(),
  callbackDate: date().required().min(new Date(), 'Callback must be in the future'),
});

// mirrors backend CallbackUpdate — every field optional
export const callbackUpdateSchema = callbackCreateSchema.partial();
```

Yup conventions to keep consistent across every `validations/<domain>Schemas.js` file:

- **Build small reusable field validators, then compose** with `.shape()`/`.concat()` —
  don't repeat the same `string().required().max(120)` across five domain schema files.
- **Use `.pick()` / `.omit()`** rather than hand-duplicating a schema when a form only needs
  a subset of a bigger entity's fields.
- **Use `.partial()`** for every `*Update` schema instead of writing it by hand — it should
  always be a strict subset of the matching `*Create` schema, never a divergent one.
- **Use `.exact()`** on forms where a stray field indicates a bug (a mis-bound `Controller`
  name) rather than silently accepting it.
- **Watch the nested-optional-object gotcha**: Yup casts before validating, so an object
  field with its own `required()` children needs `.default(undefined)` or `.nullable()` at
  the parent, or a genuinely optional nested object fails validation on missing input. This
  will bite `CampaignForm`'s optional Ramadan/holiday calendar override if not handled
  explicitly.
- **Yup is the courtesy layer, Pydantic is the gate** (§1) — never encode a rule in a
  `validations/*Schemas.js` file that isn't also enforced by the matching backend schema in
  `src/<domain>/schemas.py`. This matters more here than in a typical CRUD app: several of
  this app's Yup schemas (e.g. `complaintSchemas.js`) mirror fields that are compliance-
  facing (SLA category, severity) — a frontend-only relaxation of one of these is a
  regulatory gap, not just a UX inconsistency.

### 3.6 React 19 features, used deliberately (not by default)

React 19 is in the stack for specific wins, not to replace react-hook-form/TanStack Query
wholesale:

- **React Compiler** (wired via the babel plugin in `vite.config.js`) handles memoization
  automatically — don't reach for manual `useMemo`/`useCallback` in new components purely
  for referential stability; let the compiler do it, and only hand-optimize where profiling
  actually shows a problem (e.g. `TranscriptViewer` re-rendering on every streamed event).
- **`useOptimistic`** for the handful of interactions where waiting on a round-trip would
  feel laggy and a rollback-on-failure is acceptable — e.g. marking an `Escalation` as
  "acknowledged" or a `Callback` as "completed" from the queue view. This sits inside the
  domain component, on top of the mutation from the hooks layer, not as a replacement for
  it.
- **`use()`** for reading a Suspense-boundary promise or context conditionally — e.g. a
  `CallDetailContainer`-style skeleton reading a live-call-status promise passed down from
  its container — instead of a `useEffect` + `useState` combo.

### 3.7 Responsive design

Every screen must work on a phone, not just a desk — a compliance officer or on-call ops
lead is far more likely to be checking a `COMPLAINT_SLA_AT_RISK` alert or an escalation
queue from a phone when it fires than to be sitting at a desktop with the dashboard already
open. Responsiveness is not optional polish here; treat it the same as any other
non-negotiable in §4.

- **Mobile-first, always.** Write the unprefixed Tailwind classes for the smallest screen
  first, then layer on `sm:`/`md:`/`lg:` for wider ones — never the reverse. shadcn/ui's
  primitives are unstyled Radix underneath; responsiveness is never inherited for free,
  it's on whoever builds each `components/<domain>/` piece to add the breakpoint classes.
- **Every form (§3.5) stacks to a single column below `md`.** A `CampaignForm` or
  `CliConfigForm` laid out `grid md:grid-cols-2` on desktop needs to fall back to one
  column, full-width inputs, on a phone.
- **Tables are the highest-risk component** — `CrudTable`, `CallAttemptTimeline`,
  `ComplaintSlaTimeline`, `CallEventLog` all carry enough columns (timestamp, disposition
  code, actor, latency) that they will overflow a phone screen. Pick one deliberately per
  table: wrap it in `overflow-x-auto` on its own container so it scrolls horizontally
  without ever widening the page body, or collapse it to a stacked card layout below `sm`
  for tables where the one column a phone user actually needs (usually SLA status or
  disposition) would otherwise be hidden off-screen.
- **Navigation collapses.** `Navbar.jsx` needs a mobile menu state below `md` — a
  desktop-width nav bar with this many domains (campaigns, calls, customers, claims,
  complaints, escalations, callbacks, analytics, security, admin) will not fit a phone's
  width un-collapsed.
- **Check at three widths before calling a screen done**: ~375px (phone), ~768px (tablet),
  ~1280px (desktop) — not just a resized desktop browser window.

---

## 4. Non-negotiables (cross-cutting, from spec §36 / IMPLEMENTATION_PLAN.md)

These apply in every domain, front and back, regardless of phase. Each one below is a spec
§36 rule translated into a concrete code-shape check — if you can't point to the mechanism
that enforces it, it isn't actually enforced yet.

- **No authentication bypass by LLM.** `verification_level` is read and written only by
  `verification/service.py`, called only from a `calls/` Temporal activity — never settable
  via an LLM tool call, never inferable from conversation text. If a code path lets the LLM
  or a caller's words change this value, that's the highest-severity bug this codebase can
  have (spec §36 rule 1).
- **No hallucinated customer-specific facts.** The LLM's context (`voice/pipeline.py`)
  receives only the specific fields the `calls/` workflow selected via a tool response —
  never a raw DB row, never "whatever's convenient." Every customer-specific sentence the
  AI speaks must trace to a Pydantic-validated tool response (spec §36 rules 3–4).
- **Every customer-impacting write is idempotent.** Every `actions/`, `complaints/`,
  `verification/`, `privacy/` service function that performs a create/mutate goes through
  `src/idempotency.py` with a caller-supplied idempotency key + correlation id — a retry
  after network uncertainty returns the original result, never a duplicate row (spec §36
  rule 27).
- **Audit/event tables are insert-only, immutable.** `audit.AuditEvent`, `calls.CallEvent`,
  `complaints.ComplaintSlaEvent` — no `UPDATE`, no `DELETE`, from any code path, ever
  (§2.5). This is what makes them usable as a compliance audit trail (spec §36 rule 10,
  §32).
- **Never log OTP, PIN, CVV, password, or full payment-card data — anywhere.** Not in
  `logging.ini` output, not in a debug print, not in a Temporal workflow's event history
  (which persists). `verification/` compares OTP values server-side against a short-lived
  Redis-backed record only (spec §36 rule 18, §10.3.2).
- **Raw transcripts pass through redaction before persisting long-term.** The `calls/`
  transcript-persistence path never accepts raw STT output directly — only the output of
  `privacy/`'s redaction pipeline (Presidio + custom validators). A code path that writes
  to `CallTranscript` without going through that pipeline first is a bug, not a
  short-term-storage optimization (spec §36 rule 17, §28).
- **Authentication authority is bound to the live call session.** `verification_level` lives
  on `CallSession`, never on `Customer`. A new call always starts unverified regardless of
  what a prior, disconnected call achieved (spec §36 rule 28, §10.6.3).
- **The kill switch is checked at the top of every outbound-triggering code path** —
  `Depends(require_outbound_enabled)` on the relevant `campaigns/`/`telephony/` endpoints
  and the equivalent check at the top of the corresponding Temporal activity, not a
  scattered `if` copied into each call site (spec §39).
- **Money pulled from claims data is `Decimal`, never `float`** — backend schema through
  frontend display formatting (`utils/slaUtils.js`'s neighbor, a `currencyUtils.js` if one
  is added once Journey E ships) — even though this system doesn't originate the figures
  itself, a lossy round-trip on a settlement amount is still a real customer-facing error.
- **A formal complaint's SLA clock is computed deterministically by `complaints/service.py`
  from insurer-configured policy, never estimated by the LLM and never client-settable**
  (spec §36 rule 36, §18.1) — see §2.4's `ComplaintCreate` schema, which has no
  `acknowledgment_due_at`/`resolution_due_at` field for exactly this reason.

---

## 5. How this file relates to IMPLEMENTATION_PLAN.md and the spec

`Insurance_Outbound_AI_Call_Center_Motor_MVP_Developer_Spec_v1_3.md` is the compliance/
functional source of truth — when in doubt about *whether* a behavior is required, that
document wins. `IMPLEMENTATION_PLAN.md` tells you *what* to build this phase — which
entities, which vendor (demo-free vs. production-paid), which "exit criteria" line to
satisfy. This file tells you *how* to write it once you know what it is. When they seem to
conflict, the spec wins on required behavior; `IMPLEMENTATION_PLAN.md`'s technology choices
win on which library/vendor; this file wins on code shape and layering.
