# CallAgent Frontend — Running Locally

Phase 0 (tooling scaffold) of the Insurance Outbound AI Call Center ops dashboard — a Vite +
React 19 + Tailwind v4 + shadcn/ui project with one shared `fetchClient` and a health-check
page, and nothing else yet (no domain screens — see
`.claude/specs/phase-0-frontend-spec.md`, repo root, for why and what's deferred).

Unlike `backend/`, this app is **not** part of `docker-compose.yml` — it always runs locally
via `npm run dev`, per `IMPLEMENTATION_PLAN.md` §1.

## Prerequisites

- Node.js 20+ (this repo was scaffolded and verified against Node 20.20.2)
- The backend stack running — see `backend/README.md`. The quickest path is, from the
  **repo root**:
  ```bash
  docker compose up -d --wait
  ```

## Setup

From `frontend/`:

```bash
npm install
cp .env.example .env
```

`.env.example` points `VITE_API_BASE_URL` at `http://localhost:8001` — the backend's
compose-published port (see `backend/README.md`). Change it if you've overridden
`BACKEND_HOST_PORT`.

**One backend-side setting this depends on:** the backend's `CORS_ORIGINS` must include
`http://localhost:5173` (Vite's default dev port) or every browser-side call from this app
gets rejected at the CORS preflight, even though a plain `curl` to the same endpoint
succeeds. This repo's `docker-compose.yml` and `backend/.env.example` already set it — if
you're running the backend some other way, set `CORS_ORIGINS=["http://localhost:5173"]` (or
your `vite dev`'s actual origin) yourself.

## Running

```bash
npm run dev
```

Open `http://localhost:5173/` — you should see **"backend: ok"**, proving the full chain
(`HealthPage` → TanStack Query → `fetchClient` → `VITE_API_BASE_URL` → FastAPI `/health` →
Postgres) end-to-end. `"backend: unreachable"` almost always means either the backend stack
isn't up (`docker compose ps` from repo root) or the CORS setting above isn't applied to
whichever backend process you're actually hitting.

## Build / preview

```bash
npm run build      # outputs frontend/dist/
npm run preview    # serves the production build locally
```

## Linting

```bash
npm run lint
```

Runs automatically in `.github/workflows/frontend-ci.yml` on every PR touching
`frontend/**`, alongside `npm run build`.

## Adding a shadcn/ui component

`src/components/ui/` is intentionally empty in Phase 0 (see spec decision 11 in
`.claude/specs/phase-0-frontend-spec.md`). Add one when a real domain screen needs it:

```bash
npx shadcn@latest add <component>
```

## What's deliberately not here yet

No `pages/`/`containers/`/`components/<domain>/` beyond `HealthPage`, no real
authentication (`contexts/authContext.jsx` and `components/common/ProtectedRoute.jsx` are
pass-through stubs — no backend `auth/` package exists to wire them to yet), no
`hooks/`/`services/<domain>Service.js`/`validations/` for any business domain. These land
domain-by-domain starting whichever phase first produces data for that screen — see
`.claude/specs/phase-0-frontend-spec.md` §6 for the full deferral list.
