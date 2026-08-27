# Phase 0 — Frontend Engineering Spec

**Derived from:** `phases/phase-0-foundations.md` (task 1: repo scaffolding) ·
`.claude/specs/phase-0-backend-spec.md` §1 (which already scoped frontend out of Phase 0's
real work) · `CLAUDE.md` §3 (frontend conventions) · `IMPLEMENTATION_PLAN.md` §1 (stack/cost
table)

**Purpose of this document:** `phases/phase-0-foundations.md` gives the frontend exactly one
line of Phase 0 work — "repo scaffolding: ... `frontend/` (React 19 + Vite) per `CLAUDE.md`
§2.1/§3.2–3.3" — and `phase-0-backend-spec.md` already confirmed why: *"the dashboard has
nothing to show until Phase 1 produces real call data ... its scaffold is created empty ...
it does no work and has no exit criteria [in the backend spec]."* This document is that
scaffold's own build-ready blueprint, so it doesn't get built ad hoc or skipped.

**Scope discipline (read this before implementing):** this phase creates **tooling and the
cross-cutting mechanism layer only** — package config, the routing shell, the one shared
`fetchClient`, and enough of the layer skeleton to prove the mechanism works end-to-end. It
does **not** create `pages/`, `containers/`, or `components/<domain>/` for any business
domain (customers, claims, campaigns, calls, complaints, escalations, callbacks, security,
admin, reporting) — those folders come into existence the phase that first needs the screen
they hold, the same way `phase-0-backend-spec.md` gave `calls/` only a `constants.py` stub
instead of the full domain slice `CLAUDE.md` describes. Pre-creating empty domain folders
now would be scaffolding cruft with nothing to review against, which is exactly what
`CLAUDE.md`'s "no half-finished implementations" rule exists to prevent.

---

## 0. Design decisions

1. **No auth flow in this phase — flagged as an open question, not silently skipped.**
   `CLAUDE.md` §2.1 assigns ops-staff login/RBAC to a backend `auth/` domain package, and §3
   assumes `contexts/authContext.jsx`, `SignInPage`, `ProtectedRoute`, and `fetchClient`'s
   401-refresh-retry logic exist from early on. But **no phase file** —
   `phase-0-foundations.md` through `phase-7-intelligence-layer.md` — schedules building
   `src/auth/` on the backend, and `phase-0-backend-spec.md`'s own file tree (§1) does not
   include it. Building real sign-in/sign-up screens against an API that doesn't exist yet
   would be dead code. This spec therefore scaffolds the *shape* (`contexts/authContext.jsx`
   holding an unauthenticated stub state, `common/ProtectedRoute.jsx` that currently passes
   every request through) so later phases slot real logic in without restructuring, but
   ships no sign-in form and no token logic. **Raise with whoever owns
   `IMPLEMENTATION_PLAN.md`: which phase is meant to build ops-dashboard authentication?** —
   it's currently unscheduled.
2. **`fetchClient.js` ships without 401-refresh-retry.** `CLAUDE.md` §3.3 describes that
   behavior as part of the shared client, but it depends on the same not-yet-scheduled
   `auth/` backend from decision 1 (refresh-token endpoint, token storage contract). Phase 0
   ships the base client — URL building, timeout via `AbortSignal`, the normalized
   `{data, status, ok, headers}` return shape, and toast-on-error — with a single documented
   extension point (`onUnauthorized` hook, currently a no-op) where that logic attaches once
   `auth/` exists.
3. **The Phase-0 proof-of-life is a health page, not a domain screen.** Backend Phase 0's
   exit criteria center on one end-to-end proof (fake call → disposition → `AuditEvent` row,
   queryable). Frontend has no equivalent domain proof available yet, so its proof is the one
   thing that *is* real at this phase: the shared HTTP mechanism. `pages/HealthPage.jsx`
   calls the backend's `/health` route (built in `phase-0-backend-spec.md` §5) through
   `fetchClient` and renders the result — proving `services/` → `fetchClient` →
   `VITE_API_BASE_URL` → FastAPI actually works before any real service file depends on it.
4. **Tailwind v4 is CSS-first — no `tailwind.config.js`.** Tailwind v4's Vite plugin
   (`@tailwindcss/vite`) reads configuration from the CSS file itself
   (`@import "tailwindcss";` in `src/index.css`, `@theme` blocks for design tokens) rather
   than a JS config file. `CLAUDE.md`'s root-config tree lists `tailwind.config.js`, written
   when v3 was the default assumption; this spec follows the current Tailwind v4 mechanism
   instead since it's what `npx shadcn@latest init -t vite` and `@tailwindcss/vite` actually
   produce today — an empty/legacy `tailwind.config.js` would just be dead weight. `postcss.
   config.js` is likewise unnecessary (the Vite plugin replaces the PostCSS pipeline) and is
   omitted.
5. **React Compiler via the standard Babel plugin path** (`babel-plugin-react-compiler`
   passed to `@vitejs/plugin-react`'s `babel.plugins` option) — the well-established,
   documented mechanism referenced by `CLAUDE.md` §3.6, not the newer Oxc/Rolldown-based
   `@vitejs/plugin-react` v6 + `reactCompilerPreset` path (that pairs with Vite 8, which is
   too new to commit to for this project's stack right now).
6. **No Docker service for the frontend in Phase 0.** `IMPLEMENTATION_PLAN.md` §1 runs the
   demo dashboard locally (`npm run dev`) or on a free static host — it's never
   containerized alongside Postgres/Redis/Temporal. `docker-compose.yml` (already defined in
   `phase-0-backend-spec.md` §1.1) is not touched by this phase.

---

## 1. Repo & tooling scaffolding

```
CallAgent/
├── docker-compose.yml                # unchanged — backend-only, see decision 6
├── backend/                          # phase-0-backend-spec.md
├── frontend/
│   ├── src/
│   │   ├── main.jsx                  # createRoot + QueryClientProvider + Toaster + App
│   │   ├── App.jsx                   # <Routes> — one public route to HealthPage (§4.2)
│   │   ├── index.css                 # @import "tailwindcss"; + @theme design tokens
│   │   ├── pages/
│   │   │   └── HealthPage.jsx        # the Phase 0 proof-of-life, see decision 3
│   │   ├── components/
│   │   │   ├── ui/                   # shadcn primitives — generated by `shadcn init`, empty
│   │   │   │                          #   until the first `shadcn add <component>` in Phase 1
│   │   │   └── common/
│   │   │       └── ProtectedRoute.jsx  # pass-through stub, see decision 1
│   │   ├── contexts/
│   │   │   └── authContext.jsx        # unauthenticated stub state, see decision 1
│   │   ├── middleware/
│   │   │   └── fetchClient.js         # the one shared HTTP client, see §3
│   │   ├── services/
│   │   │   └── healthService.js       # getHealth() — the only service file this phase needs
│   │   └── lib/
│   │       └── utils.js               # shadcn's cn() helper
│   ├── index.html
│   ├── vite.config.js                 # @/ alias, @tailwindcss/vite, react() + compiler babel plugin
│   ├── jsconfig.json                  # matches the @/ alias for editor intellisense
│   ├── components.json                # shadcn/ui config — style: new-york
│   ├── eslint.config.js
│   ├── package.json
│   └── .env.example                   # VITE_API_BASE_URL=http://localhost:8000
└── .github/workflows/
    ├── backend-ci.yml                 # phase-0-backend-spec.md §6
    └── frontend-ci.yml                # §5 below
```

Everything else `CLAUDE.md` §3.3 lists — `containers/`, per-domain `components/<domain>/`,
`hooks/<domain>Hooks/`, per-domain `services/<domain>Service.js`, `validations/`,
`reducers/authReducer.js`, `utils/queryKeys.js`, `utils/constants.js` — is **explicitly
deferred**; see §6.

### 1.1 `package.json` (dependency shape, not a lockfile)

```json
{
  "name": "callagent-frontend",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "lint": "eslint ."
  },
  "dependencies": {
    "react": "^19",
    "react-dom": "^19",
    "react-router": "^7",
    "@tanstack/react-query": "^5",
    "react-hot-toast": "^2"
  },
  "devDependencies": {
    "vite": "^6",
    "@vitejs/plugin-react": "^4",
    "babel-plugin-react-compiler": "latest",
    "tailwindcss": "^4",
    "@tailwindcss/vite": "^4",
    "eslint": "^9",
    "eslint-plugin-react-hooks": "^5",
    "eslint-plugin-react-refresh": "^0"
  }
}
```

`react-hook-form`, `yup`, `@hookform/resolvers`, and any `@radix-ui/*`/`class-variance-
authority`/`clsx`/`tailwind-merge`/`lucide-react` packages land the moment the first form or
the first `shadcn add <component>` needs them (Phase 1+) — installing them now with nothing
that uses them is exactly the unused-dependency problem `CLAUDE.md` §2.1 calls out for the
backend's `requirements/dev.txt` split, applied to the frontend.

### 1.2 `vite.config.js`

```javascript
import path from "path";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [
    react({
      babel: {
        plugins: [["babel-plugin-react-compiler", {}]],
      },
    }),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
```

### 1.3 `jsconfig.json`

```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["src"]
}
```

### 1.4 `src/index.css` — Tailwind v4 CSS-first config

```css
@import "tailwindcss";

@theme {
  /* design tokens land here as components need them — none required for a health page */
}
```

Per decision 4, no `tailwind.config.js` and no `postcss.config.js` — the `@tailwindcss/vite`
plugin in §1.2 replaces both.

### 1.5 `components.json` (shadcn/ui)

```json
{
  "style": "new-york",
  "rsc": false,
  "tsx": false,
  "tailwind": {
    "config": "",
    "css": "src/index.css",
    "baseColor": "neutral",
    "cssVariables": true
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui"
  }
}
```

`"config": ""` is deliberate — Tailwind v4 has no JS config file for the CLI to point at
(decision 4). Generated with `npx shadcn@latest init -t vite`, then left with an empty
`components/ui/` until Phase 1's first form needs a real primitive.

### 1.6 `.env.example`

```
VITE_API_BASE_URL=http://localhost:8000
```

---

## 2. `src/lib/utils.js`

```javascript
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}
```

Generated by the shadcn CLI in §1.5 — not hand-written, but listed here since it's a real
file this phase ships (`components/ui/` will need it the moment Phase 1 adds its first
primitive).

---

## 3. `src/middleware/fetchClient.js` — the one shared HTTP client

Per decision 2, this ships the base mechanism, not the full contract `CLAUDE.md` §3.3
eventually describes:

```javascript
import toast from "react-hot-toast";

const BASE_URL = import.meta.env.VITE_API_BASE_URL;
const DEFAULT_TIMEOUT_MS = 10_000;

// No-op until an auth/ backend exists (see phase-0-frontend-spec.md decision 1/2) —
// whichever phase adds token refresh replaces this, not fetchClient's callers.
let onUnauthorized = () => {};
export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

export async function fetchClient(path, { method = "GET", body, headers = {}, timeoutMs = DEFAULT_TIMEOUT_MS, silent = false } = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers: { "Content-Type": "application/json", ...headers },
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });

    if (response.status === 401) {
      onUnauthorized();
    }

    const data = response.status === 204 ? null : await response.json().catch(() => null);

    if (!response.ok && !silent) {
      toast.error(data?.detail ?? `Request failed (${response.status})`);
    }

    return { data, status: response.status, ok: response.ok, headers: response.headers };
  } catch (error) {
    if (!silent) {
      toast.error(error.name === "AbortError" ? "Request timed out" : "Network error");
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}
```

`services/healthService.js` is the only file allowed to import this in Phase 0:

```javascript
import { fetchClient } from "@/middleware/fetchClient";

export async function getHealth() {
  return fetchClient("/health", { silent: true });
}
```

---

## 4. Routing shell & the Phase 0 proof-of-life

### 4.1 `src/main.jsx`

```jsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "react-hot-toast";
import App from "@/App";
import "@/index.css";

const queryClient = new QueryClient();

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
        <Toaster />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
```

### 4.2 `src/App.jsx` + `src/pages/HealthPage.jsx`

```jsx
// App.jsx
import { Routes, Route } from "react-router";
import HealthPage from "@/pages/HealthPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HealthPage />} />
    </Routes>
  );
}
```

```jsx
// pages/HealthPage.jsx
import { useQuery } from "@tanstack/react-query";
import { getHealth } from "@/services/healthService";

export default function HealthPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    refetchInterval: 10_000,
  });

  const status = isLoading ? "checking…" : data?.ok ? "backend: ok" : "backend: unreachable";

  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <p className="text-sm text-neutral-600">{status}</p>
    </main>
  );
}
```

This is the frontend's version of `phase-0-backend-spec.md` §4.3's end-to-end proof: it
exercises the full real chain — `HealthPage` → TanStack Query → `healthService` →
`fetchClient` → `VITE_API_BASE_URL` → FastAPI's `/health` route → Postgres `SELECT 1` — with
nothing mocked, before any real domain service is written against the same chain.

### 4.3 `src/contexts/authContext.jsx` + `src/components/common/ProtectedRoute.jsx`

Shape only, per decision 1 — no login, no token, no redirect logic yet:

```jsx
// contexts/authContext.jsx
import { createContext, useContext } from "react";

const AuthContext = createContext({ user: null, isAuthenticated: false });

export function AuthProvider({ children }) {
  // Replaced once src/auth/ exists on the backend — see phase-0-frontend-spec.md decision 1.
  return <AuthContext.Provider value={{ user: null, isAuthenticated: false }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
```

```jsx
// components/common/ProtectedRoute.jsx
export function ProtectedRoute({ children }) {
  // Pass-through until real auth exists — do not wire a redirect against a backend that
  // isn't there yet (see phase-0-frontend-spec.md decision 1).
  return children;
}
```

Neither is wired into `App.jsx` in Phase 0 (there's nothing to protect yet) — they exist so
Phase 1+ imports them instead of inventing the shape mid-feature.

---

## 5. CI (`.github/workflows/frontend-ci.yml`)

Runs on every PR touching `frontend/`:

```yaml
name: frontend-ci
on:
  pull_request:
    paths: ["frontend/**"]

jobs:
  build:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npm run lint
      - run: npm run build
```

No backend, no Postgres, no Docker needed for this job — a pure static-site lint+build,
matching decision 6. Deliberately no test step: there is no component logic yet to unit-test
beyond `HealthPage`, and a single manual smoke check (§7) covers it more cheaply than adding
a test runner for one file.

---

## 6. Explicitly deferred to later phases

Same discipline as `phase-0-backend-spec.md` §8, applied to the frontend:

- Every `pages/`, `containers/`, and `components/<domain>/` folder for customers, claims,
  campaigns, calls, complaints, escalations, callbacks, security, admin, reporting — begins
  the phase that first produces data for that screen (mostly Phase 1 onward, per
  `IMPLEMENTATION_PLAN.md`'s phase index).
- Every `hooks/<domain>Hooks/`, `services/<domain>Service.js`, and
  `validations/<domain>Schemas.js` file — same trigger as above; `CLAUDE.md` §3.5's rule
  that a Yup schema must mirror its backend Pydantic schema field-for-field means these
  can't be written before the backend schema they mirror exists.
- Real ops-dashboard authentication — `SignInPage`/`SignUpPage`/`ForgotPasswordPage`/
  `ResetPasswordPage`, `reducers/authReducer.js`, `fetchClient`'s 401-refresh-retry, and
  `common/RoleGate.jsx` — blocked on a backend `auth/` domain package that **no phase file
  currently schedules** (decision 1). Needs an owner decision before Phase 1 closes, since
  every RBAC-gated screen in `CLAUDE.md` §3.3 (`SecurityReviewPage` especially) depends on
  it existing.
- `utils/queryKeys.js`'s per-domain key factories, `utils/constants.js`'s disposition/action
  code enums (mirroring `calls/constants.py`/`actions/constants.py` from
  `phase-0-backend-spec.md` §3.4) — write these once there's a real query or a real code to
  render, not as empty registries with nothing in them yet.
- `Navbar.jsx`/`Footer.jsx` and the mobile-nav collapse behavior (`CLAUDE.md` §3.7) — wait
  for there to be more than one route to navigate between.
- Any `components/ui/` primitive beyond what `shadcn init` generates — added one
  `shadcn add <component>` at a time as each domain form/table needs it.
- Frontend hosting/deploy target (`IMPLEMENTATION_PLAN.md` §1 names Vercel/Netlify free tier
  as an option) — not needed until there's something worth showing someone outside the
  local dev machine.

---

## 7. Exit criteria traceability

`phases/phase-0-foundations.md` sets no dedicated frontend exit criteria (its three exit
criteria are all backend-only). This phase's own bar, matching the rigor
`phase-0-backend-spec.md` applied to its half:

| Check | Satisfied by |
|---|---|
| `npm run dev` boots from a clean checkout, zero manual steps beyond `npm install` + copying `.env.example` → `.env` | §1.1–§1.6 tooling config |
| The rendered page proves the full `fetchClient` → backend `/health` chain live, not mocked | §4.2 `HealthPage` |
| `npm run build` completes with zero errors | §1.2 `vite.config.js` |
| `npm run lint` passes clean | §1.1 ESLint deps, §5 CI |
| Folder skeleton matches this spec's §1 tree exactly (no domain folders pre-created) | manual review against §1 |
| CI fails a PR that breaks lint or build | §5 `frontend-ci.yml` |
