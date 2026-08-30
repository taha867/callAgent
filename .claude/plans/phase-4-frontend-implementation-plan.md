# Phase 4 Frontend — Implementation Plan (as executed)

## Context

`.claude/specs/phase-4-frontend-spec.md` is the finalized design for a new "Governance"
page in the ops dashboard, backed by the `src/qa/` backend domain implemented and verified
live earlier this session (`.claude/plans/phase-4-backend-implementation-plan.md`). This
plan implements that page against the real, already-running frontend dev server
(`localhost:5173`) and the real, already-running backend (`localhost:8001`), verifying every
piece live in-browser rather than only by code review.

Fresh read-only exploration of the actual frontend code (not the spec's design-time prose)
found several places where the spec's assumptions didn't match reality — corrected below
before any code was written, the same discipline the backend plan applied.

## Corrections made (apply these, not the original spec's literal text)

1. **No `PaginationControls.jsx` existed** — built fresh (`components/common/`); `qa/` is
   genuinely the first paginated list view in this codebase.
2. **shadcn `Badge`'s real variants are `default|secondary|destructive|outline|ghost|link`**
   (verified by reading `ui/badge.jsx`'s `cva` config) — no `"success"`/`"muted"` variant
   exists. `DefectStatusBadge` uses only `default`/`secondary`/`outline`/`destructive`.
3. **`FormSelect`'s `options` prop is a flat array of strings**, not `{value,label}` objects
   (confirmed via `ComplaintCreateForm.jsx`) — every `FormSelect` usage here passes a flat
   constants array directly.
4. **This codebase's real conditional-Yup pattern is `.test()` + `this.parent`, not
   `.when()`** — zero `.when()` usages exist anywhere; `reportingSchemas.js`'s
   `dateRangeFilterSchema` is the real precedent. `defectStatusUpdateSchema` follows it.
5. **No mutation anywhere invalidated a query on success yet** — `qaMutations.js` is the
   first real `useQueryClient().invalidateQueries(...)` example in this codebase, verified
   live in-browser to actually refresh the summary tiles/table without a manual reload.
6. **Request bodies are hand-mapped from camelCase RHF field names to snake_case API keys
   inside the service function** (confirmed via `complaintService.js`) — `qaService.js`
   follows this exactly.
7. Backend response shapes were verified against the real, already-implemented `qa/` API
   (not re-derived from the spec's own sketch) — `Page[T]` envelope, exact
   `DefectLogEntryRead`/`JourneyRunRead`/`GovernanceSummary` field names, exact live query
   params.

## What shipped

- `src/utils/constants.js` — `DEMO_JOURNEY_IDS`, `DEFECT_STATUSES`, `COMPILED_ARTIFACT_TYPES`.
- `src/utils/queryKeys.js` — `qaKeys` (first `.list()`-with-params factory in this codebase).
- `src/services/qaService.js` (new) — 7 functions, `fetchClient`/`unwrapResponse` pattern.
- `src/validations/qaSchemas.js` (new) — 3 schemas, `.test()`/`this.parent` conditional
  pattern for the COMPILED-requires-artifact rule.
- `src/hooks/qaHooks/qaQueries.js` + `qaMutations.js` (new).
- `src/components/common/PaginationControls.jsx` (new).
- `src/components/qa/` (new domain folder) — `DefectStatusBadge`, `GovernanceSummaryHeader`,
  `JourneyStatusGrid`, `DefectLogTable`, `DefectDetailPanel`,
  `form/{DefectLogEntryForm,DefectOccurrenceForm,DefectStatusUpdateForm}`.
- `src/containers/QaGovernanceContainer.jsx`, `src/pages/QaGovernancePage.jsx` (new).
- `src/App.jsx` (+1 route), `src/components/Navbar.jsx` (+1 link) — edited.

## Verification performed

- `npx eslint` over every new/changed file — 0 errors (1 benign React Compiler warning about
  `react-hook-form`'s `watch()`, an inherent, known incompatibility noted in CLAUDE.md §3.6).
- **Full live browser verification** against the running dev server + backend (not just a
  static render check):
  - Page loads at `/qa`; summary tiles and 9-journey grid render with real data.
  - Created a defect via the form — table updated, summary's `total_defects`/`open_defects`
    incremented immediately (proves the new invalidate-on-success wiring actually works).
  - Recorded a second occurrence via shape key — `compilation_required` badge
    ("Compile required (2×)") appeared, summary's `compilation_required_count` incremented.
  - Opened the detail panel; selecting `COMPILED` correctly revealed the two conditional
    artifact fields; submitting with them empty correctly showed both `.test()` validation
    errors and did not PATCH; filling them in and resubmitting succeeded — table/summary/
    detail badge all updated to `COMPILED`/0 pending, live.
  - Confirmed via console message check: zero errors/warnings at any point.
- **Not verified**: visual responsive behavior at 375px/768px/1280px — `resize_window`
  did not change this tab's reported viewport (stayed 1854×909) after two attempts, an
  environment/tool limitation, not a code issue. In place of a visual check: every
  responsive class used (`grid-cols-1 sm:grid-cols-3` in `JourneyStatusGrid`,
  `grid-cols-1 md:grid-cols-2` in the forms) is a verbatim copy of the same breakpoint
  pattern already proven elsewhere in this exact codebase (`AnalyticsContainer`,
  `ComplaintCreateForm`). This should still be spot-checked manually in a real browser
  window before considering the page fully done.

## Test data left in place

Two defect-log rows now exist in the real database from manual verification (one from
backend testing earlier this session, one — "Browser verification test defect" — from this
frontend verification pass), both now `status: COMPILED`. No cleanup endpoint exists in
this domain by design (`DELETE` is deliberately absent); left in place rather than removed
via direct SQL, per this session's standing rule against destructive actions.
