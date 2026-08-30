# Phase 4 — Frontend Engineering Spec (Demo Hardening & Governed Regression)

**Status:** Draft — ready for implementation
**Depends on:** `.claude/specs/phase-4-backend-spec.md` (defines every endpoint/field cited
below — this document does not re-derive them from the phase file's prose)
**Spec references:** §35 Phase 4, §29–30 (Nine Mandatory Demo Journeys)
**Code-shape references:** `CLAUDE.md` §3 (frontend layering, §3.5 forms/validation, §3.7
responsive design)
**Phase file:** [`phases/phase-4-demo-hardening.md`](../../phases/phase-4-demo-hardening.md)
**Unblocked by:** `phase-4-backend-spec.md`'s `qa/` domain (§2–4 of that document) — same
gating discipline `phase-3-frontend-spec.md` §0.1 already established: verify against
shipped endpoints before building, don't build against phase-file prose.

---

## 0. Design decisions (read this before implementing)

### 0.1 The phase file never mentions a dashboard screen — this is a deliberate inference, stated as one

`phases/phase-4-demo-hardening.md`'s exit criteria say the defect log "exists and is
reviewable" and that this is "the artifact that proves the phase is done, not a subjective
'feels solid' judgment" (lines 94–95). Nothing in that file names a UI. `frontend-explorer`
confirmed there is currently **no** existing concept of "test run," "scenario,"
"regression," or "QA" anywhere in `frontend/` — this is genuinely new ground, not a gap in
an existing screen. The inference this spec makes — that "reviewable" for a project whose
entire ops surface (`CLAUDE.md` §3.3) is already a dashboard means "reviewable on the
dashboard," not "reviewable by reading a database with `psql`" — is consistent with how
every other domain in this app already works, but it is an inference, and is called out as
one rather than presented as something the phase file explicitly asked for.

### 0.2 `frontend-explorer` confirmed the exact starting state — no admin page, no RBAC, no generic CRUD engine to reuse

- `AdminPage.jsx` and `components/admin/` **do not exist at all** — `ProtectedRoute.jsx` is
  a literal pass-through (`return children;`, comment: "Pass-through until real auth exists
  — do not wire a redirect against a backend that isn't there yet"), no `RoleGate.jsx`
  exists, backend `src/auth/` doesn't exist either. Nothing is RBAC-gated in this app yet
  (`phase-3-frontend-spec.md` §0.8 already noted this for `reporting/`; it's still true).
  **The QA governance page follows suit — unauthenticated, exactly like every other route.**
  This is not a new gap Phase 4 introduces; it's the same inherited constraint every prior
  phase has correctly left alone until Phase 5 builds real auth.
- `components/common/CrudTable.jsx`/`CrudDrawer.jsx` **do not exist** — `CLAUDE.md` §3.3
  documents them as the target shape for lookup/config screens, but nothing has built them
  yet (`phase-1-frontend-spec.md:853` explicitly deferred them). There is nothing to reuse.
  The defect log is also not really a config/lookup entity in the `CrudTable` sense anyway —
  it has real domain-specific status logic (§0.4 below) closer to `Complaint`'s shape than a
  flat CLI-config row. This phase hand-builds `qa/` components the same way `complaints/`
  and `reporting/` were hand-built, rather than either (a) inventing `CrudTable` under
  time-pressure as a side effect of an unrelated phase, or (b) waiting on it.
- `reporting/` is the best-fit precedent for structure: shipped, read-heavy, table + badge +
  stat-tile components already exist there to copy the *shape* of (not the code) —
  `StatusAnalyticsTable.jsx` (shadcn `Table`, loading/error/empty guards),
  `DispositionBadge.jsx` (a `Set`-based severity→variant map feeding a shadcn `Badge`),
  `StatTile.jsx` (label/value/hint card). `qa/`'s own components follow these exact
  patterns — this phase does not invent a new table/badge/tile shape.

### 0.3 `qa/` is the first domain that actually needs `.lists()/.list()/.detail()` query keys — every existing domain has sidestepped it so far

`utils/queryKeys.js` today has `claimKeys`/`callKeys` (single-record detail only, no list
pagination), `complaintKeys` (`all`/`detail` only, no `.lists()`), and `reportingKeys`
(date-range-keyed report fetches, not a paginated list). `CLAUDE.md` §3.3 documents the
`.all/.lists()/.list()/.detail()` factory shape, but `frontend-explorer` confirmed **no
domain in this codebase currently implements it** — every prior domain either had no list
view or had one small enough not to need real pagination params in its key. `GET
/qa/defect-log` is genuinely paginated (per `phase-4-backend-spec.md` §4, via
`src/pagination.py`) and filterable by `status`/`demo_journey_id` — `qaKeys` is written
against the documented convention for the first time, becoming the concrete precedent the
next domain that needs real pagination can finally copy verbatim instead of reading the
convention out of `CLAUDE.md` cold.

### 0.4 Two forms, two mutation shapes — mirroring `complaints/`'s status-transition precedent, not `campaigns/`'s create-only precedent

A defect log entry has two distinct write actions with different payloads and different
call sites, matching `phase-4-backend-spec.md`'s two POST endpoints exactly:

- **Logging a new defect** (`POST /qa/defect-log`) — a form, used the first time a defect is
  found during a hardening session.
- **Recording a repeat occurrence** (`POST /qa/defect-log/{shape_key}/occurrences`) — a much
  smaller action (pick the existing shape key, optionally add a note), used every time the
  *same* defect shape is seen again. This is deliberately not the same form reused with an
  `id` pre-filled — the whole point of the two-strike rule is that a human is asked "have I
  seen this shape before?" as a real decision each time, not defaulted into "create new."
- **Updating status / attaching a compiled artifact** (`PATCH /qa/defect-log/{id}`) — the
  `ComplaintStatusUpdateForm.jsx` precedent exactly: a small form on the detail view, status
  dropdown plus (conditionally, only once `compilation_required` is true — see §0.5) the
  artifact-type/ref fields.

### 0.5 `compilation_required` drives the UI the same way `SlaCountdown`-style computed fields drive Complaints — a read-only server-computed flag, never a form input

`DefectLogEntryRead.compilation_required` (backend spec §3.1) is exactly the kind of
server-computed boolean `CLAUDE.md` §2.4 says must never be client-settable. The frontend
never sends it — it only *reads* it, to decide whether `DefectStatusUpdateForm`'s
artifact-type/ref fields render as required (Yup: `.when('status', { is: 'COMPILED', then:
schema => schema.required() })`) and to drive `DefectStatusBadge`'s "compilation required"
visual state. This mirrors `CLAUDE.md` §3.5's warning about `complaintSchemas.js` mirroring
compliance-facing backend fields verbatim — getting this one wrong (letting a form silently
allow `status: "COMPILED"` with no artifact ref) would defeat the entire mechanical
enforcement point of `phase-4-backend-spec.md` §6.2's CI gate.

### 0.6 No new charting library, no new shadcn components beyond what `reporting/` already added

`Table`, `Badge`, and the stat-tile pattern already exist in this codebase
(`phase-3-frontend-spec.md` §0.4 added `table`/`skeleton`; `Badge` predates that). This
phase's one new UI need — a 9-journey pass/fail grid — is a `grid grid-cols-3` of small
status cards (reusing `StatTile.jsx`'s shape with a pass/fail badge instead of a numeric
value), not a chart. No `npx shadcn add` is needed this phase.

---

## 1. Frontend package layout — the Phase 3 → Phase 4 diff

```
frontend/src/
├── pages/
│   └── QaGovernancePage.jsx                # NEW — "/qa", renders QaGovernanceContainer, nothing else
│
├── containers/
│   └── QaGovernanceContainer.jsx           # NEW — status/journey filter state, composes qa/ components
│
├── components/
│   └── qa/                                  # NEW domain folder
│       ├── GovernanceSummaryHeader.jsx      # 4 stat tiles: total/open/compilation-required/journeys-passing
│       ├── JourneyStatusGrid.jsx            # 9-card grid, one per DemoJourneyId, latest cooperative-run badge
│       ├── DefectLogTable.jsx                # paginated table — StatusAnalyticsTable.jsx shape
│       ├── DefectDetailPanel.jsx             # shown on row click — occurrence history, status form
│       ├── DefectStatusBadge.jsx             # DispositionBadge.jsx shape: status → shadcn Badge variant
│       └── form/
│           ├── DefectLogEntryForm.jsx        # POST /qa/defect-log
│           ├── DefectOccurrenceForm.jsx      # POST /qa/defect-log/{shape_key}/occurrences
│           └── DefectStatusUpdateForm.jsx    # PATCH /qa/defect-log/{id}
│
├── hooks/
│   └── qaHooks/
│       ├── qaQueries.js                     # useDefectLogList, useDefectLogEntry, useJourneyRuns, useGovernanceSummary
│       └── qaMutations.js                   # useCreateDefect, useRecordOccurrence, useUpdateDefectStatus
│
├── services/
│   └── qaService.js                          # raw API calls — no fetch() outside this file (CLAUDE.md §3.4)
│
├── validations/
│   └── qaSchemas.js                          # defectLogEntryCreateSchema, defectOccurrenceCreateSchema,
│                                              #   defectStatusUpdateSchema (mirrors backend Update schema
│                                              #   field-for-field, including the conditional artifact-ref rule)
│
├── utils/
│   ├── constants.js                          # + DEMO_JOURNEY_IDS, ADVERSARIAL_SCENARIO_IDS, DEFECT_STATUSES,
│   │                                          #   COMPILED_ARTIFACT_TYPES — mirrors backend qa/constants.py verbatim
│   └── queryKeys.js                          # + qaKeys (first real .all/.lists()/.list()/.detail() factory, §0.3)
│
├── App.jsx                                   # MODIFIED — adds `/qa` route
└── components/Navbar.jsx                     # MODIFIED — adds "Governance" nav link
```

---

## 2. Route & navigation

```jsx
// App.jsx — one addition, same flat unauthenticated shape every other route already uses
<Route path="/qa" element={<QaGovernancePage />} />
```

`Navbar.jsx` gets one new link, labeled "Governance" (not "QA" — an ops user reviewing this
during/after a client demo session is not a QA engineer; "Governance" matches the phase
file's own framing: this is the Judgment Compiler governance artifact, not a bug tracker).
Per `CLAUDE.md` §3.7, the nav addition must not break the existing mobile-collapse behavior
— it's one more item in the same collapsing list, not a special case.

---

## 3. Key components

### 3.1 `GovernanceSummaryHeader.jsx` — reads `GET /qa/governance-summary`

Four stat tiles, reusing `StatTile.jsx` verbatim: **Total Defects**, **Open**,
**Compilation Required** (the number the CI gate in `phase-4-backend-spec.md` §6.2 checks
is zero before phase sign-off — rendered with a warning accent when > 0, success accent at
0), **Journeys Passing** (`journeys_passing / journeys_total`, e.g. "7 / 9").

### 3.2 `JourneyStatusGrid.jsx` — reads `GET /qa/journey-runs` (latest cooperative run per journey)

```jsx
// components/qa/JourneyStatusGrid.jsx
import { DEMO_JOURNEY_IDS } from '@/utils/constants';
import { useJourneyRuns } from '@/hooks/qaHooks/qaQueries';
import { StatTile } from '@/components/common/StatTile';
import { Badge } from '@/components/ui/badge';

export function JourneyStatusGrid() {
  const { data: runs, isLoading } = useJourneyRuns({ latestCooperativeOnly: true });
  if (isLoading) return <JourneyStatusGridSkeleton />;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
      {DEMO_JOURNEY_IDS.map((id) => {
        const run = runs?.find((r) => r.demo_journey_id === id);
        return (
          <div key={id} className="rounded-lg border p-3">
            <p className="text-sm font-medium">{formatJourneyLabel(id)}</p>
            <Badge variant={run?.passed ? 'success' : run ? 'destructive' : 'secondary'}>
              {run ? (run.passed ? 'Passing' : 'Failing') : 'Not yet run'}
            </Badge>
          </div>
        );
      })}
    </div>
  );
}
```

Mobile-first per `CLAUDE.md` §3.7: single column below `sm`, 3-column grid at `sm` and
above — 9 cards never need a table/`overflow-x-auto` treatment since each card is small and
self-contained, unlike the wide multi-column tables §3.7 specifically warns about.

### 3.3 `DefectLogTable.jsx` — `StatusAnalyticsTable.jsx`'s shape, paginated this time

```jsx
// components/qa/DefectLogTable.jsx
import { Table, TableHeader, TableBody, TableRow, TableCell } from '@/components/ui/table';
import { DefectStatusBadge } from './DefectStatusBadge';
import { useDefectLogList } from '@/hooks/qaHooks/qaQueries';
import { PaginationControls } from '@/components/common/PaginationControls';

export function DefectLogTable({ statusFilter, page, onPageChange, onRowClick }) {
  const { data, isLoading, isError } = useDefectLogList({ status: statusFilter, page });
  if (isLoading) return <DefectLogTableSkeleton />;
  if (isError) return <p role="alert">Could not load the defect log.</p>;
  if (!data.items.length) return <p className="text-muted-foreground">No defects logged yet.</p>;

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableCell>Title</TableCell>
            <TableCell>Journey</TableCell>
            <TableCell>Occurrences</TableCell>
            <TableCell>Status</TableCell>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.items.map((entry) => (
            <TableRow key={entry.id} onClick={() => onRowClick(entry.id)} className="cursor-pointer">
              <TableCell>{entry.title}</TableCell>
              <TableCell>{formatJourneyLabel(entry.demo_journey_id)}</TableCell>
              <TableCell>{entry.occurrence_count}</TableCell>
              <TableCell><DefectStatusBadge entry={entry} /></TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <PaginationControls page={page} totalPages={data.total_pages} onPageChange={onPageChange} />
    </div>
  );
}
```

`GET /qa/defect-log` returns the shared paginated envelope from `src/pagination.py`
(`{items, total, page, total_pages}`), not the bare array `StatusAnalyticsTable.jsx`'s own
comment flags as a `reporting/`-specific quirk — `qaService.js::listDefects()` should not
copy that bare-array unwrapping, it's this domain's own genuinely different response shape.
Wrapped in `overflow-x-auto` per `CLAUDE.md` §3.7's table rule, since Title/Journey/
Occurrences/Status is exactly the kind of column count that overflows a phone screen.

### 3.4 `DefectStatusBadge.jsx` — `DispositionBadge.jsx`'s exact shape

```jsx
// components/qa/DefectStatusBadge.jsx
import { Badge } from '@/components/ui/badge';

const VARIANT_BY_STATUS = {
  OPEN: 'secondary',
  FIX_APPLIED: 'outline',
  COMPILED: 'success',
  WONT_FIX: 'muted',
};

export function DefectStatusBadge({ entry }) {
  if (entry.compilation_required) {
    return <Badge variant="destructive">Compilation required ({entry.occurrence_count}×)</Badge>;
  }
  return <Badge variant={VARIANT_BY_STATUS[entry.status] ?? 'secondary'}>{entry.status}</Badge>;
}
```

The `compilation_required` short-circuit takes priority over the plain status mapping —
this is the one visual signal on the whole page an ops lead scanning the table needs to
catch first (per §0.5, it's the thing the CI gate actually enforces).

### 3.5 `DefectStatusUpdateForm.jsx` — the conditional-required-field precedent

```jsx
// components/qa/form/DefectStatusUpdateForm.jsx
import { useForm, Controller } from 'react-hook-form';
import { yupResolver } from '@hookform/resolvers/yup';
import { defectStatusUpdateSchema } from '@/validations/qaSchemas';
import { useUpdateDefectStatus } from '@/hooks/qaHooks/qaMutations';
import { FormSelect, FormField } from '@/components/custom';
import { COMPILED_ARTIFACT_TYPES } from '@/utils/constants';

export function DefectStatusUpdateForm({ entry, onSuccess }) {
  const { control, handleSubmit, watch, formState: { errors, isSubmitting } } = useForm({
    resolver: yupResolver(defectStatusUpdateSchema),
    defaultValues: {
      status: entry.status,
      compiled_artifact_type: entry.compiled_artifact_type ?? '',
      compiled_artifact_ref: entry.compiled_artifact_ref ?? '',
    },
  });
  const { mutateAsync: updateStatus } = useUpdateDefectStatus(entry.id);
  const wantsCompiled = watch('status') === 'COMPILED';

  const onSubmit = async (values) => { await updateStatus(values); onSuccess?.(); };

  return (
    <form onSubmit={handleSubmit(onSubmit)}>
      <Controller name="status" control={control} render={({ field }) => (
        <FormSelect {...field} label="Status" options={STATUS_OPTIONS} error={errors.status?.message} />
      )} />
      {wantsCompiled && (
        <>
          <Controller name="compiled_artifact_type" control={control} render={({ field }) => (
            <FormSelect {...field} label="Artifact type" options={COMPILED_ARTIFACT_TYPES}
              error={errors.compiled_artifact_type?.message} />
          )} />
          <Controller name="compiled_artifact_ref" control={control} render={({ field }) => (
            <FormField {...field} label="Artifact reference"
              placeholder="tests/scripted_conversations/adversarial/test_x.py::test_y"
              error={errors.compiled_artifact_ref?.message} />
          )} />
        </>
      )}
      <button type="submit" disabled={isSubmitting}>Save</button>
    </form>
  );
}
```

```javascript
// validations/qaSchemas.js
import { object, string, number, boolean } from 'yup';

export const defectLogEntryCreateSchema = object({
  title: string().required().max(200),
  defect_shape_key: string().required().max(100),
  demo_journey_id: string().nullable().default(null),
  adversarial_scenario_id: string().nullable().default(null),
  language: string().oneOf(['EN', 'AR', 'CODE_SWITCH']).default('EN'),
  severity: string().oneOf(['LOW', 'MEDIUM', 'HIGH']).default('MEDIUM'),
  notes: string().nullable().max(2000),
});

export const defectOccurrenceCreateSchema = object({
  demo_journey_id: string().nullable().default(null),
  adversarial_scenario_id: string().nullable().default(null),
  notes: string().nullable().max(2000),
});

// mirrors the backend's DefectLogEntryUpdate, plus the conditional-required rule that
// enforces phase-4-backend-spec.md §0.5's paperwork requirement client-side too (courtesy
// only — the backend still re-validates; see CLAUDE.md §1's "Yup is a courtesy" rule)
export const defectStatusUpdateSchema = object({
  status: string().oneOf(['OPEN', 'FIX_APPLIED', 'COMPILED', 'WONT_FIX']).required(),
  compiled_artifact_type: string().when('status', {
    is: 'COMPILED',
    then: (schema) => schema.oneOf(['REGRESSION_TEST', 'GUARD_PHRASE_RULE', 'TOOL_ALLOWLIST_RULE', 'NON_NEGOTIABLE_RULE']).required(),
    otherwise: (schema) => schema.nullable(),
  }),
  compiled_artifact_ref: string().when('status', {
    is: 'COMPILED',
    then: (schema) => schema.required().max(300),
    otherwise: (schema) => schema.nullable().max(300),
  }),
  notes: string().nullable().max(2000),
});
```

Note the `.when('status', ...)` nested-conditional pattern — this is exactly the "nested-
optional-object gotcha" `CLAUDE.md` §3.5 warns about (Yup casts before validating), handled
here the documented way: explicit `otherwise` branches with `.nullable()` rather than
leaving the conditional fields to fail validation when `status` isn't `COMPILED`.

### 3.6 `qaKeys` — the first real `.all/.lists()/.list()/.detail()` factory (§0.3)

```javascript
// utils/queryKeys.js — addition
export const qaKeys = {
  all: ['qa'],
  defectLists: () => [...qaKeys.all, 'defects', 'list'],
  defectList: (filters) => [...qaKeys.defectLists(), filters],   // { status, demo_journey_id, page }
  defectDetail: (id) => [...qaKeys.all, 'defects', 'detail', id],
  journeyRuns: () => [...qaKeys.all, 'journey-runs'],
  governanceSummary: () => [...qaKeys.all, 'governance-summary'],
};
```

`useUpdateDefectStatus`/`useRecordOccurrence`/`useCreateDefect` all invalidate
`qaKeys.defectLists()` (every list-filter variant) and `qaKeys.governanceSummary()` — the
summary header's counts must never go stale after a status change, mirroring `CLAUDE.md`
§3.4's `CallbackForm`→`CallbackQueue` invalidation precedent exactly.

---

## 4. Responsive design checklist (`CLAUDE.md` §3.7)

- `JourneyStatusGrid`: 1 column below `sm`, 3 columns at `sm`+ (§3.2).
- `DefectLogTable`: wrapped in `overflow-x-auto`, never widens the page body (§3.3).
- `DefectLogEntryForm`/`DefectStatusUpdateForm`: single column below `md`, matching every
  other form in this app (`CLAUDE.md` §3.5's own rule, not a new one).
- Checked at ~375px/~768px/~1280px before calling the page done, per `CLAUDE.md` §3.7's
  explicit three-width rule.

---

## 5. Exit-criteria mapping

| Phase file exit criterion | Frontend surface |
|---|---|
| "All 9 demo journeys pass repeatedly..." | `JourneyStatusGrid` (§3.2) |
| "Every defect found twice has a corresponding permanent automated check" | `DefectStatusBadge`'s compilation-required state (§3.4) + `DefectStatusUpdateForm`'s enforced artifact fields (§3.5) |
| "The defect log itself exists and is reviewable" | `QaGovernancePage` as a whole — the concrete answer to §0.1's inference |

---

## 6. Out of scope this phase

- Any RBAC/role gating on `/qa` — inherited constraint, not a new gap (§0.2).
- A drill-down view correlating a `JourneyRunResult` back to the specific `CallSession`/
  transcript it ran against — `test_node_id` is captured for traceability in the backend
  model, but no such call ever really happened (these are scripted, non-pipeline test runs
  per `phase-4-backend-spec.md` §0.2), so there is no `CallDetailContainer` tab to link to.
  Surfacing `test_node_id` as plain text on `DefectDetailPanel` is enough.
- `CrudTable`/`CrudDrawer` — still not built; `qa/`'s hand-built components don't block or
  require that generic engine existing (§0.2).

---
**Previous:** [Phase 3 — Frontend Spec](./phase-3-frontend-spec.md)
**Companion:** [Phase 4 — Backend Spec](./phase-4-backend-spec.md)
