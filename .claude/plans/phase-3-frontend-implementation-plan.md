# Phase 3 Frontend — Implementation Plan

## Context

`.claude/specs/phase-3-frontend-spec.md` is the finalized engineering design for Phase 3
("Operational Intelligence") of the Insurance Outbound AI Call Center **frontend** — a new
`reporting/` domain (dashboard + analytics screens, spec §31) and four new tabs on the call
detail screen (transcript/summary/intents/sentiment). It was written against the actual,
already-implemented Phase 3 **backend** (`.claude/specs/phase-3-backend-spec.md` +
`.claude/plans/phase-3-backend-implementation-plan.md` — 348 backend tests passing, 6 new
`GET /reporting/*` endpoints, 4 new `GET /calls/{id}/*` endpoints, all verified real) — this
is exactly the gating condition `phase-2-frontend-spec.md` §3 named: "wait for Phase 3's
backend spec to land the routes, then write `phase-3-frontend-spec.md` against the real,
as-shipped endpoints."

This plan turns that spec into an ordered sequence of implementation batches, the same way
`.claude/plans/phase-3-backend-implementation-plan.md` did for the backend. A dedicated
Plan-mode subagent, prompted specifically to validate batch sequencing and flag integration
risk against the actual current frontend code (not just the spec's own prose), found five
real, precisely-located issues in the spec's own sketches — folded in below as corrections,
the same way the backend plan handled its own spec corrections, rather than by editing the
spec file itself. Two of the five were independently re-verified directly (`yup.ref` exists,
`yup.yupRef` does not; only `Navbar.jsx`'s logo link touches `/`).

**No automated frontend test runner exists in this repo** (confirmed: no `vitest`, no test
script in `frontend/package.json`, no test files under `frontend/src` — Phase 1/2 frontend
both used manual verification only, and the spec's own §7 already follows that convention).
Every batch's verification is therefore `npm run lint` plus, for batches that produce
something reachable in the browser, an actual visual/network check using this session's
`claude-in-chrome` browser tools against the running dev server — per `CLAUDE.md`'s own
instruction to use a feature in a browser before calling frontend work complete, not just
trust that the code compiles.

**Execution:** all 10 batches are implemented in one continuous push, matching the backend
implementation's precedent earlier in this session — batch boundaries below are internal
checkpoints and review units, not pause points.

**Step 0 — persist this plan as a project artifact.** Write this plan's content to
`.claude/plans/phase-3-frontend-implementation-plan.md` in the repo root, mirroring how
`.claude/plans/phase-3-backend-implementation-plan.md` is kept as a durable repo artifact.

---

## Corrections to the spec (apply these, not the literal sketches)

1. **`yupRef` is not a real Yup export — `dateRangeFilterSchema`'s sketch would throw a
   `ReferenceError` at import time.** Confirmed directly against the installed `yup`
   package (`node -e "require('yup').yupRef"` → `undefined`; `.ref` is the real export).
   `.min(ref("since"))` is also the wrong semantics regardless (inclusive `>=`, not the
   spec's own prose of "strictly after"). Implement with `.test()`:
   ```javascript
   import { object, date } from "yup";

   export const dateRangeFilterSchema = object({
     since: date().required("Since is required"),
     until: date()
       .required("Until is required")
       .test("is-after-since", "Until must be after since", function (value) {
         const since = this.parent.since;
         return value && since && value > since;
       }),
   });
   ```

2. **`DateRangeFilter.onChange` must serialize `Date` → ISO string before calling back.**
   Yup's `date()` field casts the `<input type="datetime-local">` string into a native `Date`
   object during `handleSubmit`'s validation. `reportingService.js`'s functions
   template-interpolate `since`/`until` straight into a query string via
   `encodeURIComponent` — a raw `Date` there silently calls `.toString()` (a browser-locale
   string like `"Mon Aug 24 2026 00:00:00 GMT+0400"`), not an ISO string, which the backend
   422s on. `DateRangeFilter`'s `onSubmit` must call `.toISOString()` on both validated
   values before invoking `onChange(since, until)`. Not mentioned anywhere in the spec's
   §3.5/§3.10 sketches — an easy silent breakage caught only by actually watching the
   network tab (Batch 6's verification step does this).

3. **`utils/metricsUtils.js` naming: implement `formatDuration`, not `formatRate`.** The
   spec's §1 file-tree comment lists `formatPercent, formatMs, formatRate`; its §3.6 code
   block defines `formatPercent, formatMs, formatDuration`. `formatDuration` is correct —
   `avg_call_duration_seconds` is the only field needing minutes:seconds formatting, and
   `formatPercent` alone covers every `_rate` field. Also implement the `defaultDateRange()`
   helper §3.10 imports but §3.6 never shows: a last-7-days `{ since, until }` pair, both
   already `.toISOString()`-formatted (matching what Correction 2's fixed `onChange` also
   produces, so containers can pass either straight into the service functions).

4. **`useCallSummary`'s naive `refetchInterval` polls forever for calls that never get a
   summary.** The spec's sketch (`refetchInterval: (query) => (query.state.data ? false :
   3000)`) has no terminal condition beyond "data arrived." A call whose disposition means
   no conversation happened (`WRONG_PARTY`, `NO_ANSWER`, etc.) will poll every 3 seconds
   indefinitely for as long as the Summary tab — the *default* tab — stays mounted. Cap it:
   ```javascript
   export function useCallSummary(callId) {
     return useQuery({
       queryKey: callKeys.summary(callId),
       queryFn: () => callService.getCallSummary(callId),
       refetchInterval: (query) =>
         query.state.data || query.state.dataUpdateCount >= 5 ? false : 3000,
     });
   }
   ```
   (five attempts ≈ 15s ceiling — generous for a best-effort post-call summary, never
   infinite.) This is a real request-leak the naive version would ship, not a style nit —
   Batch 9's verification explicitly watches the network tab on a no-summary call to confirm
   the cap actually engages.

5. **Radix `Tabs.Content` does not force-mount inactive panels by default — the spec's §3.10
   "confirm whether `forceMount` is desired" hedge is already resolved, no decision needed.**
   Confirmed by reading `radix-ui`'s tabs source and this repo's own `components/ui/tabs.jsx`
   wrapper: neither passes `forceMount` anywhere, and Radix's default is lazy-mount. This
   means each tab's query already only fires once that tab is first clicked — exactly the
   independent-per-tab-query behavior the spec wants, and exactly what the already-shipped
   `ClaimDetailContainer` (5 tabs, Phase 1) already relies on with zero extra props.
   Implement `AnalyticsContainer`/`CallDetailContainer`'s `Tabs` identically — no
   `forceMount`, no workaround.

---

## Batches

### Batch 1 — shadcn primitives: `chart`, `table`, `skeleton`
- Run `npx shadcn@latest add chart table skeleton` from `frontend/`
- Touches: `components/ui/chart.jsx`, `table.jsx`, `skeleton.jsx`,
  `package.json`/lockfile (new `recharts` dependency — CSS chart-color tokens `--chart-1`
  through `--chart-5` already exist in `index.css`, confirmed, so no token work needed)
- Sequenced first — every reporting chart/table component and `CallSummaryPanel`'s loading
  state depend on these
- **Read the generated `chart.jsx` immediately after installing** and note its actual
  exported API (`ChartContainer`, `ChartTooltip`, etc.) — shadcn's chart component's shape
  has changed across releases; do not assume the spec's §3.8 naming is exactly right until
  this file is actually read.
- **Verify:** `npm run lint`; `npm run build` succeeds (proves `recharts` resolves); `npm run
  dev` boots with no console errors on any existing page (nothing imports the new files yet
  — a smoke check only, not a feature check).

### Batch 2 — pure utils, validations, query-key additions
- `utils/metricsUtils.js` (new): `formatPercent`, `formatMs`, `formatDuration`,
  `defaultDateRange` (Correction 3)
- `validations/reportingSchemas.js` (new): `dateRangeFilterSchema` (Correction 1)
- `utils/queryKeys.js` (+): `reportingKeys` factory (spec §3.2); `callKeys.transcript/
  summary/intents/sentiment` factories, matching `claimKeys`'s existing `status/timeline/
  documents/garage` shape
- Zero React, zero I/O, cheapest to review; every later batch depends on these
- **Verify:** `npm run lint`. No test runner exists — sanity-check
  `dateRangeFilterSchema` with a throwaway Node check (not committed): confirm `until`
  before `since` fails validation and the reverse passes. This is the one place a REPL
  substitutes for the missing test runner, since the schema's correctness (Correction 1)
  isn't otherwise verifiable before it's wired into a form.

### Batch 3 — `reporting/` service+hooks and `calls/` service+hook additions
- `services/reportingService.js` (new): 6 functions + private `rangeQuery` helper (spec
  §3.1)
- `hooks/reportingHooks/reportingQueries.js` (new): 6 query hooks (spec §3.3)
- `services/callService.js` (+): 4 functions (spec §4.1)
- `hooks/callHooks/callQueries.js` (+): 4 query hooks, `useCallSummary` implemented per
  Correction 4, not the spec's literal sketch
- Depends on Batch 2 (`reportingKeys`/`callKeys`); not yet wired into any route
- **Verify:** `npm run lint`. Cross-check each service function's URL path and query-string
  shape once more by eye against `backend/src/reporting/router.py`/`calls/router.py`'s real
  route decorators — a wrong path here fails silently as a 404 that a later browser check
  would otherwise have to debug from scratch.

### Batch 4 — shared presentational atoms
- `components/common/StatTile.jsx` (new, spec §3.7)
- `components/common/SentimentBadge.jsx` (new, spec §4.4)
- `components/common/SpeakerBadge.jsx` (new, spec §4.4)
- Depends only on existing `ui/card.jsx`/`ui/badge.jsx` — pure presentational, no hooks
- **Verify:** `npm run lint`. No standalone browser check needed (same category
  `DispositionBadge` already is — never independently browser-verified in isolation
  either); real visual confirmation happens naturally in Batch 6/9.

### Batch 5 — Dashboard-vertical reporting components
- `components/reporting/DateRangeFilter.jsx` (new, spec §3.5, with Correction 2's
  `.toISOString()` fix in `onSubmit`)
- `components/reporting/OperationsOverviewGrid.jsx` (new, spec §3.7)
- `components/reporting/OutcomeFunnelChart.jsx` (new, spec §3.8) — write against Batch 1's
  actually-read `chart.jsx` API, not the spec's assumed names
- `components/reporting/LatencyPercentileChart.jsx` (new, spec §3.8) — takes the
  `OperationsOverviewRead` result as a **prop**, does not call `useOperationsOverview`
  itself (per spec §3.8's cache-sharing note)
- Depends on Batch 1 (`ui/chart`), Batch 3 (`useOperationsOverview`/`useOutcomeFunnel`),
  Batch 4 (`StatTile`)
- **Verify:** `npm run lint`. Not yet routable — no browser check possible this batch,
  resolved immediately in Batch 6.

### Batch 6 — `DashboardContainer` + `DashboardPage` + partial routing (first browser checkpoint)
- `containers/DashboardContainer.jsx` (new, spec §3.11): `useState(defaultDateRange())`,
  renders `DateRangeFilter` + `OperationsOverviewGrid` + `OutcomeFunnelChart` +
  `LatencyPercentileChart`
- `pages/DashboardPage.jsx` (new): thin wrapper, matching `CallDetailPage.jsx`'s one-line
  shape
- `App.jsx` (+): `"/"` → `DashboardPage`, add `"/health"` → `HealthPage` (moved, file itself
  unchanged)
- `components/Navbar.jsx` (+): `{ to: "/", label: "Dashboard" }` as the first `LINKS` entry
  (leave `/analytics` out until Batch 8, so no dead nav link exists mid-implementation)
- First batch where anything built is actually reachable in a browser
- **Verify:** `npm run lint`. **Real browser check (claude-in-chrome):** with
  `docker compose up -d --wait` (backend) and `npm run dev` (frontend) running, navigate to
  `/`; confirm `OperationsOverviewGrid` renders real numbers for the 7-day default range,
  including the honestly-zero metrics (`fraud_siu_referrals` etc.) rendering as `0`/`0.0%`,
  not hidden; confirm both charts render with no console error (the real test of the
  chart-API-drift risk); change the date range via `DateRangeFilter` and read the network
  request to confirm the new `since`/`until` params are ISO-formatted (proves Correction 2);
  navigate to `/health` and confirm the original health check still works unchanged.

### Batch 7 — Analytics-vertical reporting components
- `components/reporting/NoAnswerAnalyticsPanel.jsx` (new, spec §3.9) — `ui/table` + a small
  bar chart
- `components/reporting/StatusAnalyticsTable.jsx` (new, spec §3.9) — plain `ui/table` over
  the bare-array response
- `components/reporting/CustomerExperiencePanel.jsx` (new, spec §3.9) —
  `Object.entries(breakdown)` iteration, never hardcoding `POSITIVE`/`NEUTRAL`/`NEGATIVE`
- `components/reporting/EscalationAnalyticsPanel.jsx` (new, spec §3.9) — same
  dict-iteration discipline for `by_status`/`by_reason`
- Reuses `DateRangeFilter` (Batch 5) as a prop-driven component, not reimplemented
- **Verify:** `npm run lint`. Not yet routable — deferred to Batch 8.

### Batch 8 — `AnalyticsContainer` + `AnalyticsPage` + remaining routing (second browser checkpoint)
- `containers/AnalyticsContainer.jsx` (new, spec §3.10): `Tabs` over the four Batch 7
  panels, per Correction 5 (no `forceMount`)
- `pages/AnalyticsPage.jsx` (new): thin wrapper
- `App.jsx` (+): `"/analytics"` route
- `components/Navbar.jsx` (+): `{ to: "/analytics", label: "Analytics" }`
- **Verify:** `npm run lint`. **Real browser check:** navigate to `/analytics`, click
  through all four tabs, confirm each panel loads independently (network tab confirms one
  slow tab doesn't block the others — the practical proof of Correction 5's lazy-mount
  claim); confirm dict-shaped fields render correctly even when demo data has a sparse or
  missing key for one enum value.

### Batch 9 — Call-detail vertical: transcript/summary/intents/sentiment + `CallDetailContainer` Tabs conversion (highest integration risk)
- `components/calls/CallTranscriptViewer.jsx` (new, spec §4.3) — code comment: never log
  transcript text (spec §0.7)
- `components/calls/CallSummaryPanel.jsx` (new, spec §4.3) — explicit null-response branch,
  same no-logging comment
- `components/calls/CustomerIntentList.jsx` (new, spec §4.3)
- `components/calls/SentimentTimeline.jsx` (new, spec §4.3) — splits `turn_index !== null`
  per-turn rows from the two `turn_index === null` call-level markers
- `containers/CallDetailContainer.jsx` (modified): flat layout → `Tabs`
  (Summary/Transcript/Intents/Sentiment), per spec §4.5. **`EscalationCreateForm` must stay
  a sibling after `</Tabs>`, never nested inside a `TabsContent`** — the spec's own sketch
  already gets this right; call it out explicitly in review as the one line easiest to get
  wrong while adapting the existing flat JSX.
- Depends on Batch 1 (`ui/skeleton`), Batch 3 (the 4 new call hooks, Correction 4 applied),
  Batch 4 (`SentimentBadge`/`SpeakerBadge`)
- **Verify:** `npm run lint`. **Real browser check:** open an existing call's detail page
  for a call that actually completed a conversation (not a bare `NO_ANSWER`); click through
  all four tabs; confirm `CallTranscriptViewer` shows redaction placeholders (e.g.
  `[EMIRATES_ID_REDACTED]`) if the demo call spoke anything PII-shaped, never raw values;
  confirm `EscalationCreateForm` stays visible and submittable regardless of which tab is
  active (the regression check for the risk above); watch the network tab for ~15–20s on a
  call whose disposition means no summary will ever exist (e.g. `WRONG_PARTY`) and confirm
  `useCallSummary`'s polling actually stops after 5 attempts (Correction 4) rather than
  continuing indefinitely; separately watch an in-progress (`disposition_code: null`) call
  and confirm only the two expected polls fire (`useCallAttempt`'s 2s + `useCallSummary`'s
  capped 3s) — not an unexpected multiplication from the two hooks coexisting on one page.

### Batch 10 — full-app regression pass and responsive check
- No new files — verification-only, closing out the phase against spec §7's manual
  checklist and `CLAUDE.md` §3.7
- **Verify:** `npm run lint` and `npm run build` (production build, catches anything
  dev-mode masks) across the whole diff; then in the browser: resize to ~375px/768px/1280px
  on `/`, `/analytics`, and a call detail page's Transcript tab, confirming no horizontal
  page-body scroll and that the stat-tile grid/tables collapse or scroll internally instead;
  confirm `Navbar`'s mobile hamburger menu includes both new links and collapses correctly
  at `md`; re-run the date-range-change check from Batch 6 once more end-to-end now that
  both `DashboardContainer` and `AnalyticsContainer` share `DateRangeFilter`, confirming
  each container's own state is independent (changing the range on `/analytics` must not
  affect `/`'s cached range or vice versa, since `since`/`until` live in per-container
  `useState`, not global state).

---

## Key risks & mitigations (condensed)

| # | Risk | Mitigation |
|---|---|---|
| 1 | `yupRef` is not a real Yup export; the spec's schema sketch would throw a `ReferenceError` at import time | Use `ref`/`.test()` per Correction 1 (Batch 2) — independently re-verified against the installed `yup` package |
| 2 | `DateRangeFilter.onChange` receiving cast `Date` objects instead of ISO strings, silently producing non-ISO query params the backend 422s on | `.toISOString()` in `onSubmit` per Correction 2; verified via network-tab check in Batch 6 |
| 3 | shadcn `chart` component's actual exported API differing from the spec's assumed names, given no pinned version | Read the generated `chart.jsx` immediately after `npx shadcn add chart` (Batch 1) before writing any component against it; first real render checked in Batch 6 |
| 4 | `useCallSummary` polling every 3s indefinitely for calls that will never produce a summary | Cap via `dataUpdateCount >= 5` per Correction 4; explicitly network-tab-verified in Batch 9 |
| 5 | Converting `CallDetailContainer` to `Tabs` accidentally nesting `EscalationCreateForm` inside a `TabsContent`, breaking its always-visible behavior | Explicit review callout in Batch 9; browser check confirms the form stays visible across all four tabs |
| 6 | `"/"` route change breaking something else that expected `HealthPage` there | Confirmed via grep: only `Navbar`'s logo link touches root, and it correctly lands on Dashboard now; `HealthPage` itself is untouched, just remounted at `/health` |
| 7 | Sentiment/status/reason dict fields (`by_status`, `by_reason`, sentiment breakdowns) assumed to always contain every enum key | `Object.entries()` iteration everywhere per spec §3.4's own warning; sparse-key case explicitly checked in Batch 8's browser pass |
| 8 | `GET /calls/{id}/summary`'s `null` (not 404) response mishandled as an error state | `unwrapResponse` already passes `null` through when `ok: true`; `CallSummaryPanel` renders an explicit "not yet available" branch, not an error branch |
| 9 | Transcript/summary text accidentally reaching `console.log`/an error reporter | Explicit no-logging code comments in `CallTranscriptViewer`/`CallSummaryPanel` (spec §0.7), enforced by review since there's no lint rule for it |
| 10 | Assuming Radix `Tabs.Content` force-mounts inactive panels, leading to an unnecessary workaround | Confirmed false by reading `radix-ui`'s tabs source and this repo's `ui/tabs.jsx` wrapper — default lazy-mount already matches the desired behavior (Correction 5) |
| 11 | Two independent polling hooks (`useCallAttempt`, `useCallSummary`) on the same page multiplying request volume unexpectedly | Each hook has its own bounded terminal condition; explicitly watched together in Batch 9's network-tab check, not assumed safe by inspection |

---

## Verification (overall, run after each batch and again at the end)

```bash
cd frontend
npm run lint
npm run build
```

Plus, at each batch marked with a real browser check above: `docker compose up -d --wait`
(repo root, backend running), `npm run dev` (frontend), and this session's
`claude-in-chrome` tools to navigate, click, and inspect network requests — not just "the
code compiles." End-of-phase acceptance is the traceability table in
`.claude/specs/phase-3-frontend-spec.md` §8, matching `phases/phase-3-operational-
intelligence.md`'s own exit criteria wording (every §31 metric visible, none placeholder).
