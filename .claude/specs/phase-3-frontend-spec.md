# Phase 3 — Frontend Engineering Spec (Operational Intelligence)

**Status:** Draft — ready for implementation
**Depends on:** `.claude/specs/phase-3-backend-spec.md` (implemented — 12 batches, 348
backend tests passing) and `.claude/plans/phase-3-backend-implementation-plan.md`, which is
the as-shipped source of truth for every endpoint/field name cited below
**Spec references:** §31 (MVP Dashboard Requirements), §18/§28 (Dissatisfaction/Conversation
Event Log — for the transcript/sentiment views), §35 Phase 3
**Code-shape references:** `CLAUDE.md` §3 (frontend layering, §3.7 responsive design)
**Phase file:** [`phases/phase-3-operational-intelligence.md`](../../phases/phase-3-operational-intelligence.md)
**Unblocked by:** `phase-2-frontend-spec.md` §3 named this exact gating condition — "wait for
Phase 3's backend spec to land the routes, then write `phase-3-frontend-spec.md` against the
real, as-shipped endpoints." That's what this document is.

---

## 0. Design decisions (read this before implementing)

### 0.1 Verified against the actual shipped backend, not the spec's prose

Every endpoint, field name, and response shape below was checked against the real code —
`backend/src/reporting/router.py`/`schemas.py`/`service.py` and
`backend/src/calls/router.py`/`schemas.py` — not re-derived from
`phase-3-backend-spec.md`'s own design-time sketches, which is the same discipline
`phase-1-frontend-spec.md` and `phase-2-frontend-spec.md` both already established for this
repo. Field names are **snake_case, verbatim** — this app has never introduced a
camelCase transform layer (`CallAttemptSummary.jsx` reads `attempt.customer_reached`
directly), and Phase 3 does not start one.

### 0.2 New `reporting` domain — read-only, no mutations, mirrors `claimHooks`'s shape

All 6 `reporting/router.py` endpoints are `GET`, and reporting/ owns no tables backend-side
— there is nothing to create/update/delete. `hooks/reportingHooks/` therefore gets only a
`reportingQueries.js`, no `reportingMutations.js` — the same shape `claimHooks/` and
`callHooks/` already have (`claimHooks` has no mutations file either; see `CLAUDE.md` §3.3's
own note that some domains are read-only from the dashboard).

### 0.3 `since`/`until` are required on every reporting call — no silent default at the fetch layer

The backend rejects a missing `since`/`until` with a 422 (`.claude/specs/
phase-3-backend-spec.md` §5.1's own design: "an implicit 'last 24h' default would silently
hide a stale/empty range"). The frontend respects that: `services/reportingService.js`'s
functions take `since`/`until` as required arguments, never default them internally. The
**UI** picks an initial value (last 7 days) purely as a starting point for the date-range
control — that default lives in `DashboardContainer`/`AnalyticsContainer` state, not in the
service layer, so it's visible and changeable, never silently baked in.

ISO datetime strings contain `:`/`+` characters `encodeURIComponent` must escape — the
existing `getClaimStatus(claimId, verificationLevel)` precedent
(`services/claimService.js`) interpolates its query param raw because a plain enum string
never needs escaping; `since`/`until` do, and every reporting service function uses
`encodeURIComponent` explicitly rather than copying that precedent verbatim.

### 0.4 Charting: shadcn's `chart` component (Recharts), not a new charting library chosen ad hoc

No charting library exists in `package.json` yet. This repo is shadcn-first for every other
UI primitive (`components.json` confirms `style: "radix-nova"`, `iconLibrary: "lucide"`) —
shadcn's own `chart` component (`npx shadcn add chart`) is a thin Tailwind-styled wrapper
around **Recharts**, which becomes a real `package.json` dependency the moment that
component is added (not bundled invisibly). This is the only new runtime dependency this
phase introduces. Used for exactly two views: the Outcome Funnel (a horizontal bar/funnel
chart) and the latency P50/P95/P99 trio (a small bar chart) — every other metric in this
phase is a stat tile or a table, which don't need a charting library at all.

Two more shadcn components are added: `table` (status analytics, no-answer-by-day/hour) and
`skeleton` (loading states for the dashboard's stat-tile grid, nicer than a bare "Loading…"
given how many independent queries one dashboard view fires).

### 0.5 `DashboardPage` becomes the landing route; `HealthPage` moves to `/health`

`CLAUDE.md` §3.3 names `DashboardPage` explicitly as "operations overview + outcome funnel
(spec §31), landing page." Today `/` renders `HealthPage` (a one-line backend-reachability
check) — Phase 0's placeholder, never revisited since. This phase finally has something
real to put at `/`. `HealthPage`'s existing check remains reachable at `/health`, not
deleted — an ops user still occasionally needs "is the backend even up" as a distinct,
lighter-weight question from "how are we performing," and the existing `getHealth()` service
call and 10-second poll are untouched.

### 0.6 `CallDetailContainer` gains four new tabs, not a new route

The four new calls/ endpoints (`/{call_id}/transcript`, `/summary`, `/intents`,
`/sentiment`) are all keyed by a `call_id` the container already has via `useParams()`.
Per `ClaimDetailContainer.jsx`'s own established pattern — five independent tab queries,
each fired by its own component, so one missing/null response never blocks the others —
this phase converts `CallDetailContainer` from a flat `CallAttemptSummary` +
`EscalationCreateForm` stack into a `Tabs` layout: **Summary** (unchanged content),
**Transcript**, **Intents**, **Sentiment**. `EscalationCreateForm` stays visible outside the
tabs (it's an action available regardless of which tab is open, not tab-scoped content).

### 0.7 Transcript text is already redacted server-side — the frontend has no redaction responsibility, but does have a logging one

`GET /calls/{call_id}/transcript` returns `CallTranscript.redacted_text` —
`privacy/service.py::redact()`'s output, never raw STT/TTS text (spec §36 rule 17, enforced
mechanically backend-side by `scripts/ci/check_transcript_redaction.py`). The frontend
renders this string as-is; no client-side scrubbing is needed or correct to add (scrubbing
already-redacted text again would be redundant, and a client-side "second redaction pass"
would wrongly suggest the frontend is a compliance boundary when it isn't — the backend is).
The one real obligation this phase adds: **never pass transcript/summary text through
`console.log`, an analytics SDK, or a third-party error reporter** — redacted or not, it's
still customer conversation content. `CallTranscriptViewer`/`CallSummaryPanel`'s own code
comments should say this, not just this spec.

### 0.8 No RBAC/auth this phase — `reporting/` and the new `calls/` endpoints are unauthenticated, matching the backend

`src/auth/` (backend) still does not exist. `RoleGate`/`SecurityReviewPage` stay out of
scope, unchanged from every prior phase's deferral — no Phase 3 screen here reads
`risk/`-domain data (fraud/vulnerability referrals appear only as a **count** inside
Operations Overview, which is not restricted data, per `reporting/service.py`'s own query —
it's an aggregate number, not the underlying `ClaimAction` rows with case detail).

### 0.9 No live per-call latency drill-down this phase — only the aggregate P50/P95/P99

`CLAUDE.md` §3.3 names a `LatencyMetricsPanel` on the call-detail screen showing
"P50/P95/P99, spec §2.2.1." That per-call, per-turn breakdown has **no backend endpoint** —
`reporting/service.py::_latency_percentiles()` only exposes the aggregate across a
`since`/`until` range on `/operations-overview`, never a single call's own
`CallLatencySample` rows (`calls/router.py` was not given a `/{call_id}/latency` endpoint —
confirmed absent from `.claude/specs/phase-3-backend-spec.md` §3.5's four new routes). The
dashboard's aggregate P50/P95/P99 stat tiles are this phase's actual latency UI; a
per-call `LatencyMetricsPanel` on `CallDetailContainer` is deferred (§8) until a matching
backend endpoint exists — building it against a manual DB query would be exactly the kind
of frontend-invents-an-endpoint drift `phase-1-frontend-spec.md`'s own decisions warn
against.

### 0.10 Date-range validation is Yup, mirroring `CLAUDE.md` §3.5 — `until` must be after `since`

The one form this phase adds (`DateRangeFilter`) gets a real `validations/
reportingSchemas.js` Yup schema, not ad hoc component-local validation — `until` must be
strictly after `since`, both required. This is the same "Yup is the courtesy layer" rule
every other form in this app already follows; the backend's own 422 on a missing param is
the actual gate, this is just so an ops user gets an inline error before the round trip.

---

## 1. Frontend package layout — the Phase 2 → Phase 3 diff

```
frontend/src/
├── pages/
│   ├── DashboardPage.jsx                 # NEW — new landing route "/"
│   ├── AnalyticsPage.jsx                  # NEW — "/analytics"
│   └── HealthPage.jsx                      # moved: "/" → "/health" in App.jsx (file unchanged)
│
├── containers/
│   ├── DashboardContainer.jsx              # NEW — date-range state, renders reporting/ components
│   ├── AnalyticsContainer.jsx               # NEW — date-range state + Tabs for the 4 analytics views
│   └── CallDetailContainer.jsx               # MODIFIED — Tabs: Summary/Transcript/Intents/Sentiment
│
├── components/
│   ├── reporting/                             # NEW domain folder
│   │   ├── DateRangeFilter.jsx                  # shared by Dashboard + Analytics containers
│   │   ├── OperationsOverviewGrid.jsx             # stat-tile grid, GET /reporting/operations-overview
│   │   ├── OutcomeFunnelChart.jsx                  # shadcn chart, GET /reporting/outcome-funnel
│   │   ├── LatencyPercentileChart.jsx               # shadcn chart, reads operations-overview's p50/p95/p99
│   │   ├── NoAnswerAnalyticsPanel.jsx                # GET /reporting/no-answer-analytics
│   │   ├── StatusAnalyticsTable.jsx                   # GET /reporting/status-analytics
│   │   ├── CustomerExperiencePanel.jsx                 # GET /reporting/customer-experience
│   │   └── EscalationAnalyticsPanel.jsx                 # GET /reporting/escalation-analytics
│   ├── calls/
│   │   ├── CallTranscriptViewer.jsx                      # NEW — GET /calls/{id}/transcript
│   │   ├── CallSummaryPanel.jsx                           # NEW — GET /calls/{id}/summary
│   │   ├── CustomerIntentList.jsx                          # NEW — GET /calls/{id}/intents
│   │   └── SentimentTimeline.jsx                            # NEW — GET /calls/{id}/sentiment
│   └── common/
│       ├── StatTile.jsx                                       # NEW — reusable labeled-metric card
│       ├── SentimentBadge.jsx                                  # NEW — mirrors DispositionBadge's pattern
│       └── SpeakerBadge.jsx                                     # NEW — CUSTOMER | AI, for the transcript view
│
├── hooks/
│   ├── reportingHooks/
│   │   └── reportingQueries.js                # NEW — 6 query hooks, one per endpoint
│   └── callHooks/
│       └── callQueries.js                     # MODIFIED — +4 query hooks (transcript/summary/intents/sentiment)
│
├── services/
│   ├── reportingService.js                    # NEW
│   └── callService.js                         # MODIFIED — +4 fetch functions
│
├── validations/
│   └── reportingSchemas.js                    # NEW — dateRangeFilterSchema
│
├── utils/
│   ├── queryKeys.js                           # MODIFIED — +reportingKeys, +callKeys transcript/summary/intents/sentiment
│   └── metricsUtils.js                        # NEW — formatPercent, formatMs, formatRate
│
├── components/Navbar.jsx                       # MODIFIED — +Dashboard, +Analytics links
└── App.jsx                                      # MODIFIED — routing diff, §6
```

---

## 2. Dependencies added

```bash
cd frontend
npx shadcn@latest add chart table skeleton
```

`chart` pulls in `recharts` as a real `package.json` dependency (confirm the exact pinned
version the CLI resolves at implementation time — do not hand-pin a version number in this
spec that the CLI might not actually choose). `table` and `skeleton` add no new npm
dependencies (pure Tailwind/Radix, like every other shadcn primitive already in
`components/ui/`). No other `package.json` changes this phase.

---

## 3. `reporting/` domain

### 3.1 `services/reportingService.js`

One function per endpoint, mirroring `claimService.js`'s flat-function style exactly (no
class, no object namespace):

```javascript
import { fetchClient } from "@/middleware/fetchClient";
import { unwrapResponse } from "@/utils/unwrapResponse";

function rangeQuery(since, until) {
  return `since=${encodeURIComponent(since)}&until=${encodeURIComponent(until)}`;
}

export const getOperationsOverview = (since, until) =>
  unwrapResponse(fetchClient(`/reporting/operations-overview?${rangeQuery(since, until)}`));

export const getOutcomeFunnel = (since, until) =>
  unwrapResponse(fetchClient(`/reporting/outcome-funnel?${rangeQuery(since, until)}`));

export const getNoAnswerAnalytics = (since, until) =>
  unwrapResponse(fetchClient(`/reporting/no-answer-analytics?${rangeQuery(since, until)}`));

export const getStatusAnalytics = (since, until) =>
  unwrapResponse(fetchClient(`/reporting/status-analytics?${rangeQuery(since, until)}`));

export const getCustomerExperience = (since, until) =>
  unwrapResponse(fetchClient(`/reporting/customer-experience?${rangeQuery(since, until)}`));

export const getEscalationAnalytics = (since, until) =>
  unwrapResponse(fetchClient(`/reporting/escalation-analytics?${rangeQuery(since, until)}`));
```

`rangeQuery` is a private module helper, not exported — every reporting service function
needs it, no other domain does, so it stays local rather than joining `utils/`.

### 3.2 `utils/queryKeys.js` addition

```javascript
export const reportingKeys = {
  all: ["reporting"],
  operationsOverview: (since, until) => [...reportingKeys.all, "operations-overview", since, until],
  outcomeFunnel: (since, until) => [...reportingKeys.all, "outcome-funnel", since, until],
  noAnswerAnalytics: (since, until) => [...reportingKeys.all, "no-answer-analytics", since, until],
  statusAnalytics: (since, until) => [...reportingKeys.all, "status-analytics", since, until],
  customerExperience: (since, until) => [...reportingKeys.all, "customer-experience", since, until],
  escalationAnalytics: (since, until) => [...reportingKeys.all, "escalation-analytics", since, until],
};
```

`since`/`until` are part of the key deliberately — changing the date range must be a cache
miss, not a stale re-render of the previous range's numbers.

### 3.3 `hooks/reportingHooks/reportingQueries.js`

```javascript
import { useQuery } from "@tanstack/react-query";
import * as reportingService from "@/services/reportingService";
import { reportingKeys } from "@/utils/queryKeys";

export function useOperationsOverview(since, until) {
  return useQuery({
    queryKey: reportingKeys.operationsOverview(since, until),
    queryFn: () => reportingService.getOperationsOverview(since, until),
    enabled: Boolean(since && until),
  });
}
// ...one more useQuery per endpoint, identical shape, swapping the service function/key factory.
```

`enabled: Boolean(since && until)` on every hook — `DashboardContainer`/`AnalyticsContainer`
hold `since`/`until` in state seeded from `DateRangeFilter`'s default (§0.3); this guards
the one render frame before that state is set, rather than firing a request FastAPI will
422 on.

### 3.4 Response shapes (field names verbatim from `reporting/schemas.py`)

Cited here once so every component below can be written against the real shape without
re-deriving it:

- **`OperationsOverviewRead`**: `calls_scheduled`, `calls_attempted`, `human_answer_rate`,
  `right_party_contact_rate`, `verification_success_rate`, `statuses_delivered`,
  `ai_contained_calls`, `actions_created`, `complaints_created`, `human_escalations`,
  `callbacks_scheduled`, `no_answer_rate`, `avg_call_duration_seconds` (nullable),
  `latency_p50_ms`/`latency_p95_ms`/`latency_p99_ms` (nullable),
  `silent_call_technical_failure_rate`, `backend_dependency_failure_rate`,
  `model_stt_tts_failure_rate`, `dtmf_fallback_rate`, `concurrent_call_conflicts_prevented`,
  `dropped_call_rate`, `otp_lockouts`, `fraud_siu_referrals`, `vulnerable_customer_referrals`
  — all `_rate` fields are floats in `[0, 1]`, not already-multiplied percentages (§3.6's
  `formatPercent` multiplies by 100).
- **`OutcomeFunnelRead`**: `{ stages: [{ stage, count, conversion_from_previous }] }` —
  `conversion_from_previous` is `null` on the first stage only.
- **`NoAnswerAnalyticsRead`**: `by_hour: [{ hour, no_answer_count, total_count }]`,
  `by_day: [{ day, no_answer_count, total_count }]` (`day` is an ISO date string),
  `by_attempt_number: [{ attempt_number, answer_rate, total_count }]`, plus
  `rejected_count`/`voicemail_count`/`unreachable_count`/`successful_callbacks`.
- **`list[StatusAnalyticsRow]`** (the endpoint returns a bare array, not an object):
  `[{ status, total_calls, question_rate, escalation_rate }]`.
- **`CustomerExperienceRead`**: `initial_sentiment_breakdown`/`final_sentiment_breakdown`
  (`{ [sentiment]: count }` dicts — keys are `POSITIVE`/`NEUTRAL`/`NEGATIVE`, absent keys
  mean zero, never assume all three are present), `dissatisfaction_rate`, `complaint_rate`,
  `repeated_contact_customers`, `calls_requiring_humans`.
- **`EscalationAnalyticsRead`**: `total_escalations`, `by_status`/`by_reason` (`{ [key]:
  count }` dicts, same "absent key = zero" rule), `warm_transfer_count`.

### 3.5 `components/reporting/DateRangeFilter.jsx`

react-hook-form + `validations/reportingSchemas.js`'s Yup resolver, per `CLAUDE.md` §3.5 —
two native `<input type="datetime-local">` fields (no new date-picker dependency needed at
demo scale) wired through `FormField` (`components/custom`, already exists per `CLAUDE.md`
§3.2's target tree — confirm it's been built by Phase 1/2; if not, a plain labeled `<input>`
is an acceptable substitute, but reuse `FormField` if present, don't fork a second pattern).
Calls `onChange(since, until)` on valid submit; `DashboardContainer`/`AnalyticsContainer`
own the actual `since`/`until` state and pass the current value back in as the form's
`defaultValues` so navigating away and back doesn't lose the selection mid-session (no
persistence beyond the React tree — a page refresh resets to the 7-day default, which is
fine for a demo-tier dashboard).

```javascript
// validations/reportingSchemas.js
import { object, date } from "yup";

export const dateRangeFilterSchema = object({
  since: date().required(),
  until: date()
    .required()
    .min(yupRef("since"), "Until must be after since") // use .test() for the strict-after
                                                          // comparison if yup's built-in
                                                          // min() semantics (>=) aren't
                                                          // strict enough at implementation time
});
```

### 3.6 `utils/metricsUtils.js`

```javascript
export const formatPercent = (rate) => (rate == null ? "—" : `${(rate * 100).toFixed(1)}%`);
export const formatMs = (ms) => (ms == null ? "—" : `${Math.round(ms)}ms`);
export const formatDuration = (seconds) =>
  seconds == null ? "—" : `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
```

Every `_rate` field and every `_ms` field in §3.4's shapes goes through one of these — no
component hand-rolls its own `.toFixed()` call, the same "one shared place" reasoning
`fetchClient.js` already applies to HTTP concerns.

### 3.7 `components/common/StatTile.jsx`

```jsx
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function StatTile({ label, value, hint }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-2xl font-semibold">{value}</p>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  );
}
```

`OperationsOverviewGrid.jsx` renders ~24 of these in a responsive grid (`grid-cols-2
sm:grid-cols-3 lg:grid-cols-4`, per `CLAUDE.md` §3.7's mobile-first rule) — the honestly-zero
metrics from `phase-3-backend-spec.md` §0.10 (fraud/SIU referrals, silent-call failure rate)
render with their real `0`/`0.0%` value, same tile styling as every other metric — **never**
a "coming soon" placeholder or a hidden tile, which would misrepresent a real (if currently
empty) number as unavailable.

### 3.8 `components/reporting/OutcomeFunnelChart.jsx` and `LatencyPercentileChart.jsx`

Both use shadcn's `chart` primitives (`ChartContainer`/`ChartTooltip` from
`components/ui/chart`, added in §2) wrapping Recharts' `BarChart`. `OutcomeFunnelChart`
plots `stages[].count` with `stages[].stage` as the category axis and a tooltip showing
`conversion_from_previous` (formatted via `formatPercent`) alongside the raw count.
`LatencyPercentileChart` plots the three `latency_p50_ms`/`p95_ms`/`p99_ms` values from
`OperationsOverviewRead` as three bars — this is **not** a separate query, it reads the
same `useOperationsOverview` result `OperationsOverviewGrid` already fetched (co-located in
`DashboardContainer`, passed down as props — one query, two components, per TanStack
Query's own cache-sharing behavior when both call `useOperationsOverview` with the same key
this is automatic even without prop-drilling, but passing it down avoids a redundant
`useQuery` call site for a value the parent already has in hand).

### 3.9 `components/reporting/NoAnswerAnalyticsPanel.jsx`, `StatusAnalyticsTable.jsx`, `CustomerExperiencePanel.jsx`, `EscalationAnalyticsPanel.jsx`

- `NoAnswerAnalyticsPanel` — a small bar chart for `by_hour` (24 bars), a table for `by_day`
  (shadcn `table`, per §2), and a `StatTile` row for `by_attempt_number` +
  rejected/voicemail/unreachable/successful-callback counts.
- `StatusAnalyticsTable` — a plain shadcn `table` over the bare array response, columns
  `status | total_calls | question_rate | escalation_rate` (last two via `formatPercent`).
- `CustomerExperiencePanel` — two small stacked-bar or pie breakdowns (initial vs. final
  sentiment) plus `StatTile`s for the four scalar metrics. Iterate
  `Object.entries(breakdown)` for the sentiment dicts — never assume
  `POSITIVE`/`NEUTRAL`/`NEGATIVE` are all present (§3.4's own warning).
- `EscalationAnalyticsPanel` — `StatTile` for `total_escalations`/`warm_transfer_count`, two
  small tables or bar charts for `by_status`/`by_reason`.

### 3.10 `pages/AnalyticsPage.jsx` + `containers/AnalyticsContainer.jsx`

```jsx
// containers/AnalyticsContainer.jsx
import { useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DateRangeFilter } from "@/components/reporting/DateRangeFilter";
import { NoAnswerAnalyticsPanel } from "@/components/reporting/NoAnswerAnalyticsPanel";
import { StatusAnalyticsTable } from "@/components/reporting/StatusAnalyticsTable";
import { CustomerExperiencePanel } from "@/components/reporting/CustomerExperiencePanel";
import { EscalationAnalyticsPanel } from "@/components/reporting/EscalationAnalyticsPanel";
import { defaultDateRange } from "@/utils/metricsUtils"; // last-7-days helper, §0.3

export default function AnalyticsContainer() {
  const [{ since, until }, setRange] = useState(defaultDateRange());

  return (
    <div className="space-y-4">
      <DateRangeFilter since={since} until={until} onChange={(s, u) => setRange({ since: s, until: u })} />
      <Tabs defaultValue="no-answer">
        <TabsList>
          <TabsTrigger value="no-answer">No-Answer</TabsTrigger>
          <TabsTrigger value="status">Status</TabsTrigger>
          <TabsTrigger value="experience">Customer Experience</TabsTrigger>
          <TabsTrigger value="escalations">Escalations</TabsTrigger>
        </TabsList>
        <TabsContent value="no-answer"><NoAnswerAnalyticsPanel since={since} until={until} /></TabsContent>
        <TabsContent value="status"><StatusAnalyticsTable since={since} until={until} /></TabsContent>
        <TabsContent value="experience"><CustomerExperiencePanel since={since} until={until} /></TabsContent>
        <TabsContent value="escalations"><EscalationAnalyticsPanel since={since} until={until} /></TabsContent>
      </Tabs>
    </div>
  );
}
```

Same independent-per-tab-query discipline as `ClaimDetailContainer` — each panel calls its
own hook internally rather than the container fetching all four and prop-drilling, so
switching tabs doesn't wait on data the hidden tabs don't need yet (TanStack Query only
fires a query once its owning component mounts; an inactive `TabsContent` still mounts by
default in Radix, so this is really about keeping each panel self-contained and
independently loading/erroring, not about deferring the fetch — confirm at implementation
time whether `forceMount`/lazy-mount is desired for the four-tabs-worth-of-simultaneous-
queries cost, and if so add it deliberately, not as an afterthought).

`pages/AnalyticsPage.jsx` is the usual thin wrapper (`<main>` + the container), matching
`CallDetailPage.jsx`'s one-line shape exactly.

### 3.11 `pages/DashboardPage.jsx` + `containers/DashboardContainer.jsx`

Same `DateRangeFilter` + `since`/`until` state shape as `AnalyticsContainer`, rendering
`OperationsOverviewGrid` + `OutcomeFunnelChart` + `LatencyPercentileChart` (the latter two
side-by-side or stacked depending on viewport — `CLAUDE.md` §3.7 applies here as much as
anywhere: this is the page most likely to be checked from a phone).

---

## 4. Call detail — transcript, summary, intents, sentiment

### 4.1 `services/callService.js` additions

```javascript
export const getCallTranscript = (callId) =>
  unwrapResponse(fetchClient(`/calls/${callId}/transcript`));

export const getCallSummary = (callId) =>
  unwrapResponse(fetchClient(`/calls/${callId}/summary`));

export const getCallIntents = (callId) =>
  unwrapResponse(fetchClient(`/calls/${callId}/intents`));

export const getCallSentiment = (callId) =>
  unwrapResponse(fetchClient(`/calls/${callId}/sentiment`));
```

`getCallSummary` can resolve to `null` (the backend returns `null`, not 404, when
`generate_call_summary` hasn't produced a row yet — `.claude/specs/phase-3-backend-spec.md`
§3.5) — `unwrapResponse` already passes a `null` `data` value through unchanged as long as
`ok` is true, so no special-casing is needed here; `CallSummaryPanel` handles the `null`
case in its own render branch (§4.3).

### 4.2 `hooks/callHooks/callQueries.js` additions

```javascript
export function useCallTranscript(callId) {
  return useQuery({
    queryKey: callKeys.transcript(callId),
    queryFn: () => callService.getCallTranscript(callId),
  });
}
export function useCallSummary(callId) {
  return useQuery({
    queryKey: callKeys.summary(callId),
    queryFn: () => callService.getCallSummary(callId),
    // A summary generated after the call ends (best-effort, calls/workflows.py::_finalize) —
    // poll a few times in case the tab is opened moments after the call just finished and
    // the row hasn't landed yet; stop once a non-null value arrives, same shape
    // useCallAttempt already uses for disposition_code.
    refetchInterval: (query) => (query.state.data ? false : 3000),
  });
}
export function useCallIntents(callId) {
  return useQuery({ queryKey: callKeys.intents(callId), queryFn: () => callService.getCallIntents(callId) });
}
export function useCallSentiment(callId) {
  return useQuery({ queryKey: callKeys.sentiment(callId), queryFn: () => callService.getCallSentiment(callId) });
}
```

`utils/queryKeys.js`'s `callKeys` grows four factory functions
(`transcript`/`summary`/`intents`/`sentiment`), each `[...callKeys.detail(id), "<name>"]`,
matching `claimKeys`'s existing `status`/`timeline`/`documents`/`garage` shape exactly.

### 4.3 `components/calls/CallTranscriptViewer.jsx`, `CallSummaryPanel.jsx`, `CustomerIntentList.jsx`, `SentimentTimeline.jsx`

- **`CallTranscriptViewer`** — an ordered list of turns (`turn_index` ascending, already
  sorted server-side by `get_redacted_transcript`), each row showing `SpeakerBadge` +
  `redacted_text`. Empty array renders "No transcript recorded for this call" (a real,
  valid state — e.g. a `NO_ANSWER` call has no turns at all), not an error.
- **`CallSummaryPanel`** — `null` response renders "Summary not yet available" (§4.1); a
  present response renders `summary_text` in a `Card`.
- **`CustomerIntentList`** — a simple list, `intent` badge + `topic`/`summary` text,
  `created_at` timestamp. Empty array is valid (a call that never reached the follow-up
  stage, e.g. `WRONG_PARTY`, produced zero `CustomerIntent` rows).
- **`SentimentTimeline`** — per-turn rows (`turn_index` not null) plotted as a small
  sentiment-over-time chart or simple ordered list with `SentimentBadge` per row; the
  call-level rows (`turn_index` null — the call-start `REPEATED_CONTACT` marker and the
  call-end final-sentiment row, `.claude/specs/phase-3-backend-spec.md` §3.1) render
  separately, below the per-turn timeline, labeled "Repeated contact flagged" /
  "Final sentiment: {sentiment}" rather than mixed into the turn-indexed list where they'd
  imply a turn number they don't have.

### 4.4 `components/common/SentimentBadge.jsx` and `SpeakerBadge.jsx`

```jsx
// SentimentBadge — mirrors DispositionBadge.jsx's variantFor() pattern exactly
import { Badge } from "@/components/ui/badge";

const VARIANT_BY_SENTIMENT = { POSITIVE: "default", NEUTRAL: "secondary", NEGATIVE: "destructive" };

export function SentimentBadge({ sentiment }) {
  if (!sentiment) return <Badge variant="secondary">Unknown</Badge>;
  return <Badge variant={VARIANT_BY_SENTIMENT[sentiment] ?? "secondary"}>{sentiment}</Badge>;
}
```

```jsx
// SpeakerBadge — CUSTOMER | AI
import { Badge } from "@/components/ui/badge";

export function SpeakerBadge({ speaker }) {
  return <Badge variant={speaker === "AI" ? "default" : "outline"}>{speaker}</Badge>;
}
```

### 4.5 `containers/CallDetailContainer.jsx` — the Tabs conversion

```jsx
import { useParams } from "react-router";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useCallAttempt } from "@/hooks/callHooks/callQueries";
import { CallAttemptSummary } from "@/components/calls/CallAttemptSummary";
import { CallTranscriptViewer } from "@/components/calls/CallTranscriptViewer";
import { CallSummaryPanel } from "@/components/calls/CallSummaryPanel";
import { CustomerIntentList } from "@/components/calls/CustomerIntentList";
import { SentimentTimeline } from "@/components/calls/SentimentTimeline";
import { EscalationCreateForm } from "@/components/actions/form/EscalationCreateForm";

export default function CallDetailContainer() {
  const { callId } = useParams();
  const { data: attempt, isLoading, isError } = useCallAttempt(callId);

  if (isLoading) return <p>Loading…</p>;
  if (isError) return <p className="text-destructive">Could not load this call.</p>;
  if (!attempt) return null;

  return (
    <div className="space-y-6">
      <Tabs defaultValue="summary">
        <TabsList>
          <TabsTrigger value="summary">Summary</TabsTrigger>
          <TabsTrigger value="transcript">Transcript</TabsTrigger>
          <TabsTrigger value="intents">Intents</TabsTrigger>
          <TabsTrigger value="sentiment">Sentiment</TabsTrigger>
        </TabsList>
        <TabsContent value="summary">
          <CallAttemptSummary attempt={attempt} />
          <CallSummaryPanel callId={callId} />
        </TabsContent>
        <TabsContent value="transcript"><CallTranscriptViewer callId={callId} /></TabsContent>
        <TabsContent value="intents"><CustomerIntentList callId={callId} /></TabsContent>
        <TabsContent value="sentiment"><SentimentTimeline callId={callId} /></TabsContent>
      </Tabs>
      <EscalationCreateForm claimId={attempt.claim_id} callId={attempt.id} />
    </div>
  );
}
```

`CallAttemptSummary` and `CallSummaryPanel` share the "Summary" tab (the AI-generated
closing summary is conceptually part of "how did this call go," the same tab an ops user
already opens first) rather than `CallSummaryPanel` getting its own fifth tab.

---

## 5. Routing changes

```jsx
// App.jsx diff
import DashboardPage from "@/pages/DashboardPage";
import AnalyticsPage from "@/pages/AnalyticsPage";
// ...existing imports, HealthPage import stays

<Routes>
  <Route path="/" element={<DashboardPage />} />           {/* was HealthPage */}
  <Route path="/health" element={<HealthPage />} />         {/* moved */}
  <Route path="/analytics" element={<AnalyticsPage />} />   {/* new */}
  <Route path="/claims" element={<ClaimsPage />} />
  {/* ...unchanged routes... */}
</Routes>
```

`components/Navbar.jsx`'s `LINKS` array gains `{ to: "/", label: "Dashboard" }` (first
position) and `{ to: "/analytics", label: "Analytics" }` — no link to `/health` in primary
nav (it's a diagnostic page, not a workflow an ops user navigates to routinely; reachable by
typing the URL, matching how a health-check endpoint is usually surfaced).

---

## 6. Explicitly deferred to later phases

- **Per-call live latency breakdown** (`LatencyMetricsPanel` on `CallDetailContainer`) — no
  backend endpoint exists yet (§0.9). The dashboard's aggregate P50/P95/P99 is this phase's
  actual latency UI.
- **RBAC-gated screens** (`SecurityReviewPage`, `AdminPage`, restricted fraud/vulnerability
  case detail) — `src/auth/` still doesn't exist backend-side. Unchanged deferral from every
  prior frontend phase.
- **Real-time push updates** (a live-updating dashboard via websockets/SSE) — polling via
  TanStack Query's normal `staleTime` is the demo-tier answer; CLAUDE.md's own
  architecture note ("read-only event stream" for live-call monitoring) is a live-*call*
  concern, not a dashboard-metrics concern, and stays out of scope here regardless.
- **CallSummary/CustomerIntent/SentimentEvent editing** — every one of this phase's new
  reads has zero matching write endpoint backend-side (spec's reporting/ and the four new
  calls/ routes are all `GET`) — there is nothing to build an edit form against.
- **Exporting dashboard data** (CSV/PDF export of any reporting view) — not named in spec
  §31 or the phase file's task list; would be new scope, not implied by what's shipped.
- **Bulk multi-campaign or multi-CLI filters on the dashboard** — `since`/`until` are the
  only filter dimensions the backend query functions accept
  (`.claude/specs/phase-3-backend-spec.md` §5.1); adding a campaign/CLI filter control here
  would be UI with no backend query parameter to wire it to.

---

## 7. Manual verification (no domain test runner added this phase, matching Phase 1/2's own precedent)

1. `cd frontend && npm install && npm run dev` (backend + reporting endpoints already
   verified independently per `phase-3-backend-spec.md` §10 — confirm `docker compose up -d
   --wait` is running first, same as every prior phase's manual check).
2. Load `/` — confirm `OperationsOverviewGrid` renders real numbers (not zeros-everywhere
   unless the seeded demo data genuinely has none yet) for a 7-day default range; confirm
   the honestly-zero metrics (fraud/SIU referrals etc., §3.7) render as `0`/`0.0%`, not
   blank/hidden.
3. Change the date range via `DateRangeFilter`, confirm every stat tile and both charts
   re-fetch (network tab shows new `since`/`until` query params) and the URL's cache key
   changes (§3.2).
4. Load `/analytics`, click through all four tabs, confirm each loads independently (throttle
   network in devtools and confirm the other three tabs aren't blocked waiting on a slow
   one).
5. Open an existing call's detail page (`/calls/{id}` for a call that actually completed a
   conversation, not just `NO_ANSWER`), click through Transcript/Intents/Sentiment tabs —
   confirm transcript text shows redaction placeholders (`[EMIRATES_ID_REDACTED]` etc.) if
   the demo call spoke anything PII-shaped, never raw values.
6. Resize to ~375px (phone), ~768px (tablet), ~1280px (desktop) on `/`, `/analytics`, and a
   call detail page's Transcript tab — confirm no horizontal page-body scroll (`CLAUDE.md`
   §3.7); the stat-tile grid and any table should collapse/scroll internally, not the page.
7. Confirm `Navbar`'s mobile menu includes the two new links and collapses correctly at
   `md`.

---

## 8. Exit criteria traceability

| Exit criterion (phase file / spec §31) | Mechanism |
|---|---|
| Operations Overview — every listed metric visible | §3.7 `OperationsOverviewGrid`, all `OperationsOverviewRead` fields rendered as `StatTile`s |
| Outcome Funnel with conversion at each stage | §3.8 `OutcomeFunnelChart` |
| No-Answer Analytics (by hour/day, attempt number, rejected/voicemail/unreachable/callbacks) | §3.9 `NoAnswerAnalyticsPanel` |
| Status Analytics (question/escalation rate by status) | §3.9 `StatusAnalyticsTable` |
| Customer Experience Analytics | §3.9 `CustomerExperiencePanel` |
| "None of the above are placeholder/mocked numbers" | Every component in §3 reads live TanStack Query data off the real backend endpoints verified in `phase-3-backend-spec.md` §10 — no hardcoded demo numbers anywhere in this spec's component sketches |
| Redaction pipeline's output actually visible/inspectable, not just backend-tested | §4.3 `CallTranscriptViewer` — the human-facing half of `phase-3-backend-spec.md`'s own "manually inspect a sample of persisted transcripts" exit item |
| Attempt/escalation analytics views (phase file task) | §3.9 `NoAnswerAnalyticsPanel`'s `by_attempt_number` section + `EscalationAnalyticsPanel` |
