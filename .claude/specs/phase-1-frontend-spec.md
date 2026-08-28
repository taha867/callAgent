# Phase 1 — Frontend Engineering Spec (Deterministic Core)

**Derived from:** `.claude/specs/phase-1-backend-spec.md` §17 ("Frontend work of any kind —
nothing in `frontend/` changes in [the backend] phase... wiring dashboard screens against
[Phase 1's real call data] is `phase-1-frontend-spec.md`'s job") · `.claude/specs/phase-0-
frontend-spec.md` (this phase's actual starting code state) · `CLAUDE.md` §1/§3 (frontend
conventions) · `phases/phase-3-operational-intelligence.md` (confirms the full analytics
Dashboard/AnalyticsPage/outcome-funnel work is *that* phase's job, not this one's — see
decision 0.1) · **the actual Phase 1 backend code in `backend/src/`**, read in full before
drafting this spec, not the backend spec's design intent (every route/schema/model below is
named by its real, as-implemented shape — see §0.2 for the gap between the two).

**Purpose of this document:** `CLAUDE.md` §3.3 describes a full ten-domain dashboard
(customers, claims, campaigns, calls, complaints, escalations, callbacks, security, admin,
reporting). Phase 1's backend does not build HTTP surface for most of that yet — it builds
`CallAttempt`/`CallSession`, read-only claim data, action/escalation creation, and complaint
creation/read. This document is the frontend's build-ready blueprint for *exactly that
slice* — which screens get built now, which stay stubs, and why — so nobody wires a
`CampaignsPage` or a `CustomerList` against an endpoint that doesn't exist.

---

## 0. Design decisions (read this before implementing)

### 0.1 Scope boundary: this is not the Phase 3 dashboard

`phases/phase-3-operational-intelligence.md` explicitly owns "Dashboard (React 19 + Vite):
operations overview, outcome funnel, no-answer analytics, status analytics, customer
experience analytics" and states its exit criteria require "every metric... populated from
real Phase 1+2 data" — sentiment, transcripts, and conversation summaries that don't exist
until Phase 2/3. Building `DashboardPage`/`AnalyticsPage`/`OutcomeFunnelChart` now would mean
either faking that data or building empty shells — both are exactly the "half-finished
implementation" `CLAUDE.md` warns against. This phase builds **operational screens that read
and write real Phase 1 rows one at a time** (a claim, a call attempt, a complaint) — not
aggregate reporting. `pages/DashboardPage.jsx` is not created in this phase.

### 0.2 The backend Phase 1 actually shipped is narrower than `phase-1-backend-spec.md`'s
plan — this spec is written against the real code, not the plan

Reading `backend/src/` directly (not `.claude/specs/phase-1-backend-spec.md`, which is a
design document, not as-built documentation) surfaces four gaps between what was planned and
what exists. Each is a real constraint on this spec, not a nitpick:

1. **No `campaigns/router.py`, `telephony/router.py`, or `customers/router.py` exist at
   all** — those three domains have models/services (campaigns also has its Temporal
   workflow) but zero HTTP surface. `main.py` registers exactly four routers: `claims`,
   `actions` (mounted under the `/claims` prefix), `calls`, `complaints`. There is nothing
   for a `CampaignsPage`, `CliConfigList`, `ContactCalendarList`, or `CustomerList` to call.
2. **No list endpoint exists anywhere** — not `GET /claims`, not `GET /calls`, not
   `GET /complaints`. Every existing route takes a specific id in its path. `src/
   pagination.py` (`CLAUDE.md`'s shared pagination wrapper) has no consumer yet.
3. **No `src/auth/` and no `src/crud.py`** — confirmed absent, same as Phase 0. Ops-dashboard
   login is still unscheduled (see `phase-0-frontend-spec.md` decision 1, still open) and the
   generic CRUD engine `CLAUDE.md` describes for lookup tables has no first caller yet.
4. **No admin/kill-switch endpoint** — `src/config.py` has all five kill-switch flags and
   `src/kill_switch.py::require_outbound_enabled(...)` gates `POST /calls`, but nothing reads
   or toggles those flags over HTTP. A `KillSwitchPanel` has nothing to bind to.

Consequence: this spec builds **only** `claims/`, `calls/`, `actions/` (which also covers
escalations), and `complaints/` on the frontend. Every other `CLAUDE.md` §3.3 domain folder
stays uncreated — see §8 for the full deferred list, same discipline
`phase-0-frontend-spec.md` used for its own scope cut.

### 0.3 No list endpoints means no list screens — every screen is a detail view or a form,
reached by a known id

`CLAUDE.md`'s target pages (`ClaimsPage`, `CallsPage`, `ComplaintsPage`) are normally list
screens with a detail drill-down. Without `GET /claims`/`GET /calls`/`GET /complaints`, that
shape doesn't exist yet. This phase's index pages are **lookup-by-id forms**, not tables:

- `ClaimsPage` — a single "look up a claim" field; submitting navigates to
  `/claims/:claimId`.
- `CallsPage` — a "start a new call" form (§4) plus a "look up a call attempt" field;
  submitting the latter navigates to `/calls/:callId`.
- `ComplaintsPage` — a "file a complaint" form (§6) plus a "look up a complaint" field.

All three lookup fields share one component, `common/IdLookupForm.jsx` (§7.1), instead of
three near-identical hand-rolled forms — the kind of "three similar lines" `CLAUDE.md` says
is fine, but a fourth would not be. The ops user gets the id either by pasting one they
already have (from `scripts/seed_demo_data.py`'s fixed-ID synthetic dataset, same fixture the
backend's own integration tests use) or by following a link this app produces after a create
action (§4.2, §6.2). **This is a known, temporary shape** — the moment Phase 3 needs
pagination for its dashboard, a real `GET /claims`/`GET /calls`/`GET /complaints` list
endpoint lands on the backend and these pages gain a table above the lookup field; nothing
about `services/claimService.js`'s existing functions changes when that happens, so this
isn't work that gets thrown away.

### 0.4 `ClaimStatusPanel`'s verification-level selector is a QA control, not a login

`GET /claims/{claim_id}/status` takes `verification_level` as a plain query parameter
(`L0` default) because Phase 1 has no dashboard auth and no live-call session to read a real
verification level from (`CLAUDE.md` §4: `verification_level` lives on `CallSession`, bound
to a live call, never guessable from a dashboard request). `ClaimStatusPanel` exposes this as
a `<select>` (`L0`/`L1`/`L2`, default `L0`) purely so an ops user or QA reviewer can
**observe** `claims/service.py::get_disclosable_status()`'s redaction rule (§0.8 of the
backend spec — `settlement_amount` withheld below `L2`) without needing a real call session.
This is explicitly a testing/inspection tool, not a simulation of customer authentication —
the component's own label says "Preview as verification level," never "Verify as."

### 0.5 `Idempotency-Key` is a mutation-hook concern, not a form-field concern

`POST /claims/{claim_id}/actions` and `POST /claims/{claim_id}/escalations` both **require**
an `Idempotency-Key` header (confirmed in `backend/src/actions/router.py` — not optional).
`POST /complaints` does not — its idempotency key is derived server-side from
`source_call_id`/`claim_id` (backend spec §8.1). This is a real, asymmetric integration
detail no Yup schema captures, so it's handled once, at the hook layer:

```javascript
// utils/idempotency.js
export function newIdempotencyKey() {
  return crypto.randomUUID();
}
```

```javascript
// hooks/actionHooks/actionMutations.js
import { useMutation } from "@tanstack/react-query";
import { useRef } from "react";
import { createAction } from "@/services/actionService";
import { newIdempotencyKey } from "@/utils/idempotency";

export function useCreateAction(claimId) {
  const idempotencyKey = useRef(newIdempotencyKey());
  return useMutation({
    mutationFn: (values) => createAction(claimId, values, idempotencyKey.current),
  });
}
```

The key is generated **once per mount** of the owning form, not once per click — a TanStack
Query retry or a double-submit reuses the same key (so the backend's idempotency record
returns the original row instead of creating a duplicate `ClaimAction`), and a fresh key is
only minted when the form actually remounts (e.g., the ops user navigates away and back to
file a genuinely new action). `services/actionService.js::createAction` passes it straight
through as a header, never as a body field:

```javascript
// services/actionService.js
import { fetchClient } from "@/middleware/fetchClient";

export async function createAction(claimId, { actionCode, summary, sourceCallId }, idempotencyKey) {
  return fetchClient(`/claims/${claimId}/actions`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: { claim_id: claimId, action_code: actionCode, summary, source_call_id: sourceCallId ?? null },
  });
}
```

### 0.6 `CallDetailPage` polls until the call attempt resolves

`POST /calls` starts a `CallSessionWorkflow` and returns immediately
(`StartCallOutput{call_id, workflow_id}`) — the workflow runs the fake/text harness
asynchronously against the signal surface `phase-1-backend-spec.md` §0.5 describes.
`CallAttemptRead.disposition_code` is `null` until the workflow's terminal activity writes
it. `hooks/callHooks/callQueries.js::useCallAttempt` polls on that field, matching TanStack
Query v5's function-form `refetchInterval`:

```javascript
// hooks/callHooks/callQueries.js
import { useQuery } from "@tanstack/react-query";
import { getCallAttempt } from "@/services/callService";
import { callKeys } from "@/utils/queryKeys";

export function useCallAttempt(callId) {
  return useQuery({
    queryKey: callKeys.detail(callId),
    queryFn: () => getCallAttempt(callId),
    refetchInterval: (query) => (query.state.data?.disposition_code ? false : 2000),
  });
}
```

No WebSocket/SSE stream is introduced for this — Phase 1 has no live-call event stream to
subscribe to yet (`CallEvent` doesn't exist as a model; `CLAUDE.md`'s "read-only event
stream" for live-call monitoring is a later-phase capability), and 2-second polling on a
single-row detail view is cheap enough not to need one.

### 0.7 `simulated_answer_result` on `StartCallForm` exposes the fake harness deliberately

`StartCallInput.simulated_answer_result` is a plain, backend-unconstrained `str` defaulting
to `"HUMAN_ANSWERED"` — the field the fake/text harness uses to drive the 15-branch exit
criteria without real telephony (backend spec §0.5). Exposing it as a dropdown on
`StartCallForm` turns this into a genuinely useful ops/QA tool: a reviewer can manually drive
`NO_ANSWER`, `VOICEMAIL`, or `FAILED` outcomes from the dashboard instead of only from
`tests/integration/test_phase1_e2e.py`. The dropdown's options
(`HUMAN_ANSWERED`/`NO_ANSWER`/`VOICEMAIL`/`FAILED`) are the dial-outcome subset of
`calls/constants.py::CallState`, chosen client-side as a courtesy allow-list — **the backend
does not enforce this set** (it's an unconstrained string), which is a real validation gap
worth flagging back to whoever owns the backend spec, not something this frontend spec can
fix by itself (`CLAUDE.md` §1: Pydantic is the real gate; Yup narrowing a field the backend
leaves wide open is a courtesy that stops working the moment someone bypasses the form).

### 0.8 Complaint `severity`/`preferred_contact_method` are backend-unconstrained strings —
Yup still narrows them, flagged as a courtesy over a gap, not a mirror of a real constraint

`ComplaintCreate.severity` and `.preferred_contact_method` are plain `str` fields in
`backend/src/complaints/schemas.py` — no `Field(pattern=...)`, unlike `CLAUDE.md` §2.4's own
worked example for this exact schema. `validations/complaintSchemas.js` (§6.3) still
constrains them to `LOW|MEDIUM|HIGH` and `PHONE|EMAIL|SMS` via `.oneOf(...)`, because that's
what the spec's severity/contact-method vocabulary actually is and a free-text severity field
would be a worse ops UX regardless of what the backend currently accepts — but this is
recorded here as **the frontend compensating for a backend gap**, not as the normal
Yup-mirrors-Pydantic relationship `CLAUDE.md` §3.5 describes elsewhere. It should not be read
as evidence the backend already enforces this; whoever owns `complaints/schemas.py` should
add the matching `Field(pattern=...)` in a follow-up.

### 0.9 `settlement_amount` is rendered as an opaque formatted string, never used in
arithmetic — and the wire format itself is flagged

`CLAUDE.md` §4 requires money from claims data to be `Decimal`, never `float`, "backend
schema through frontend display formatting." Pydantic v2's default JSON encoding of a
`Decimal` field is a JSON number, not a string — meaning `ClaimStatusRead.settlement_amount`
already round-trips through a `float`-shaped wire format by the time it reaches the browser,
regardless of what the frontend does. This spec cannot fix that from the frontend side, so it
does the next best thing and contains the damage: `utils/currencyUtils.js::formatAedAmount`
takes the parsed JSON number, formats it with `Intl.NumberFormat` for display, and the
codebase rule is **no component ever performs arithmetic on `settlement_amount`** (no
summing, no percentage calculations) — it is a display-only value everywhere in this phase.
The wire-format gap itself (Pydantic should serialize `Decimal` as a string, e.g. via a
`field_serializer`, to make the "never `float`" guarantee end-to-end) is flagged back to the
backend spec owner, not silently worked around here.

---

## 1. Frontend package layout — the Phase 0 → Phase 1 diff

Everything in `frontend/src/` from `phase-0-frontend-spec.md` stays; this is what's added.
Unmarked files are new; `(+)` marks a Phase-0 file gaining new content.

```
frontend/
├── src/
│   ├── main.jsx                          # unchanged
│   ├── App.jsx (+)                       # + routes for claims/calls/complaints, <Navbar/>
│   ├── index.css (+)                     # + @theme tokens the new components' badges/cards need
│   ├── pages/
│   │   ├── HealthPage.jsx                # unchanged
│   │   ├── ClaimsPage.jsx                # lookup-by-id only — see 0.3
│   │   ├── ClaimDetailPage.jsx
│   │   ├── CallsPage.jsx                 # start-call form + lookup-by-id — see 0.3
│   │   ├── CallDetailPage.jsx
│   │   ├── ComplaintsPage.jsx            # file-complaint form + lookup-by-id — see 0.3
│   │   └── ComplaintDetailPage.jsx
│   ├── containers/
│   │   ├── ClaimDetailContainer.jsx      # claimId param -> claim + status + timeline + documents + garage
│   │   ├── CallDetailContainer.jsx       # callId param -> polling call attempt + escalation form
│   │   └── ComplaintDetailContainer.jsx  # complaintId param -> complaint
│   ├── components/
│   │   ├── ui/ (+)                       # shadcn add: button input select card tabs label textarea badge
│   │   ├── custom/                       # first real use — FormField.jsx, FormSelect.jsx, index.js barrel
│   │   ├── common/
│   │   │   ├── ProtectedRoute.jsx        # unchanged pass-through stub
│   │   │   ├── IdLookupForm.jsx          # shared lookup-by-id pattern, see 7.1
│   │   │   └── DispositionBadge.jsx      # first real use of CLAUDE.md's cross-domain badge
│   │   ├── claims/
│   │   │   ├── ClaimOverviewCard.jsx
│   │   │   ├── ClaimStatusPanel.jsx      # verification-level selector — see 0.4
│   │   │   ├── ClaimStatusTimeline.jsx
│   │   │   ├── ClaimDocumentList.jsx
│   │   │   └── RepairGarageCard.jsx
│   │   ├── calls/
│   │   │   ├── CallAttemptSummary.jsx
│   │   │   └── form/
│   │   │       └── StartCallForm.jsx     # see 0.7
│   │   ├── actions/
│   │   │   └── form/
│   │   │       ├── ActionCreateForm.jsx
│   │   │       └── EscalationCreateForm.jsx
│   │   ├── complaints/
│   │   │   ├── ComplaintDetail.jsx
│   │   │   └── form/
│   │   │       └── ComplaintCreateForm.jsx
│   │   └── Navbar.jsx                    # first real nav — mobile-collapsible per CLAUDE.md §3.7
│   ├── hooks/
│   │   ├── claimHooks/
│   │   │   └── claimQueries.js           # read-only — no mutations, matching CLAUDE.md's target shape
│   │   ├── callHooks/
│   │   │   ├── callQueries.js            # useCallAttempt — polling, see 0.6
│   │   │   └── callMutations.js          # useStartCall
│   │   ├── actionHooks/
│   │   │   └── actionMutations.js        # useCreateAction, useCreateEscalation — see 0.5
│   │   └── complaintHooks/
│   │       ├── complaintQueries.js       # useComplaint
│   │       └── complaintMutations.js     # useCreateComplaint
│   ├── services/
│   │   ├── healthService.js              # unchanged
│   │   ├── claimService.js
│   │   ├── callService.js
│   │   ├── actionService.js
│   │   └── complaintService.js
│   ├── validations/
│   │   ├── callSchemas.js                # startCallSchema
│   │   ├── actionSchemas.js              # actionCreateSchema, escalationCreateSchema
│   │   └── complaintSchemas.js           # complaintCreateSchema — see 0.8
│   ├── utils/
│   │   ├── constants.js                  # DISPOSITION_CODES, ACTION_CODES, CLAIM_STAGES, VERIFICATION_LEVELS, ...
│   │   ├── queryKeys.js                  # claimKeys, callKeys, complaintKeys
│   │   ├── idempotency.js                # newIdempotencyKey() — see 0.5
│   │   └── currencyUtils.js              # formatAedAmount() — see 0.9
│   ├── contexts/authContext.jsx          # unchanged stub — still no backend auth/, see 0.2
│   ├── middleware/fetchClient.js         # unchanged — headers option already covers 0.5's need
│   └── lib/utils.js                      # unchanged
├── components.json                       # unchanged
└── package.json (+)                      # see §2
```

`hooks/` gains no `escalationHooks/`/`callbackHooks/` folder of their own — per §0.2's real
backend, escalation-creation lives in `actions/router.py` alongside action-creation (same
domain package on the backend), and there is no callback endpoint at all (§8), so
`actionHooks/actionMutations.js` covers both action and escalation creation rather than
inventing a folder split the backend doesn't have.

---

## 2. Dependencies added

Per `phase-0-frontend-spec.md` §1.1's own stated trigger ("`react-hook-form`, `yup`,
`@hookform/resolvers`, and any `@radix-ui/*`/`class-variance-authority`/`clsx`/
`tailwind-merge`/`lucide-react` packages land the moment the first form... needs them") —
this is that phase:

```json
{
  "dependencies": {
    "react-hook-form": "^7",
    "yup": "^1",
    "@hookform/resolvers": "^3",
    "clsx": "^2",
    "tailwind-merge": "^2",
    "lucide-react": "latest",
    "class-variance-authority": "^0.7",
    "@radix-ui/react-select": "^2",
    "@radix-ui/react-tabs": "^1",
    "@radix-ui/react-label": "^2"
  }
}
```

`components/ui/` gains exactly the shadcn primitives the forms/detail views below use —
`button`, `input`, `select`, `card`, `tabs`, `label`, `textarea`, `badge` — added one
`npx shadcn add <component>` at a time, never speculatively (`phase-0-frontend-spec.md` §6).

---

## 3. Claims domain (read-only)

### 3.1 API surface consumed

```text
GET /claims/{claim_id}                         -> ClaimRead
GET /claims/{claim_id}/status?verification_level=L0|L1|L2  -> ClaimStatusRead
GET /claims/{claim_id}/timeline                -> list[ClaimStatusEventRead]
GET /claims/{claim_id}/documents               -> list[ClaimDocumentRead]
GET /claims/{claim_id}/garage                  -> RepairGarageRead | null
```

No create/update — `claims/` is 100% read-only from the dashboard in Phase 1 (claim data is
seeded synthetically by `scripts/seed_demo_data.py`, not authored via the API), matching
`CLAUDE.md` §3.3's own note that `claimHooks/` "has no mutations from the dashboard."

### 3.2 `services/claimService.js`

```javascript
import { fetchClient } from "@/middleware/fetchClient";

export const getClaim = (claimId) => fetchClient(`/claims/${claimId}`);
export const getClaimStatus = (claimId, verificationLevel) =>
  fetchClient(`/claims/${claimId}/status?verification_level=${verificationLevel}`);
export const getClaimTimeline = (claimId) => fetchClient(`/claims/${claimId}/timeline`);
export const getClaimDocuments = (claimId) => fetchClient(`/claims/${claimId}/documents`);
export const getClaimGarage = (claimId) => fetchClient(`/claims/${claimId}/garage`);
```

### 3.3 `hooks/claimHooks/claimQueries.js`

```javascript
import { useQuery } from "@tanstack/react-query";
import { claimKeys } from "@/utils/queryKeys";
import * as claimService from "@/services/claimService";

export const useClaim = (claimId) =>
  useQuery({ queryKey: claimKeys.detail(claimId), queryFn: () => claimService.getClaim(claimId) });

export const useClaimStatus = (claimId, verificationLevel) =>
  useQuery({
    queryKey: claimKeys.status(claimId, verificationLevel),
    queryFn: () => claimService.getClaimStatus(claimId, verificationLevel),
  });

export const useClaimTimeline = (claimId) =>
  useQuery({ queryKey: claimKeys.timeline(claimId), queryFn: () => claimService.getClaimTimeline(claimId) });

export const useClaimDocuments = (claimId) =>
  useQuery({ queryKey: claimKeys.documents(claimId), queryFn: () => claimService.getClaimDocuments(claimId) });

export const useClaimGarage = (claimId) =>
  useQuery({ queryKey: claimKeys.garage(claimId), queryFn: () => claimService.getClaimGarage(claimId) });
```

### 3.4 `containers/ClaimDetailContainer.jsx`

Reads `claimId` from the route, composes the five queries above into a tabbed layout
(`components/ui/tabs`): **Overview** (`ClaimOverviewCard` — policy/vehicle/stage/owner),
**Status** (`ClaimStatusPanel`, §0.4's verification-level selector), **Timeline**
(`ClaimStatusTimeline`), **Documents** (`ClaimDocumentList`), **Garage**
(`RepairGarageCard`, hidden entirely if the query resolves `null`). Each tab renders its own
loading/error state independently (five separate queries, not one combined fetch) since a
missing garage (`null`, a valid response — `MotorClaim.garage_id` is nullable) must not block
the other four tabs from rendering.

`ClaimOverviewCard` also renders two quick-action buttons — "File a complaint on this claim"
(routes to `/complaints?claimId=...`, prefilling `ComplaintCreateForm`, §6.2) and "Create an
action for this claim" (opens `ActionCreateForm`, §5.2, inline) — since neither the complaint
nor action creation flow has a claim-picker of its own (§0.3), the one place an ops user is
already looking at a specific claim is the natural launch point for both.

### 3.5 `components/claims/ClaimStatusPanel.jsx` (sketch)

```jsx
import { useState } from "react";
import { useClaimStatus } from "@/hooks/claimHooks/claimQueries";
import { formatAedAmount } from "@/utils/currencyUtils";
import { VERIFICATION_LEVELS } from "@/utils/constants";

export function ClaimStatusPanel({ claimId }) {
  const [verificationLevel, setVerificationLevel] = useState("L0");
  const { data: status, isLoading } = useClaimStatus(claimId, verificationLevel);

  return (
    <div className="space-y-4">
      <label className="flex flex-col gap-1 text-sm sm:flex-row sm:items-center sm:gap-2">
        Preview as verification level
        <select
          value={verificationLevel}
          onChange={(e) => setVerificationLevel(e.target.value)}
          className="w-full rounded border px-2 py-1 sm:w-auto"
        >
          {VERIFICATION_LEVELS.map((level) => (
            <option key={level} value={level}>{level}</option>
          ))}
        </select>
      </label>
      {isLoading ? (
        <p>Loading…</p>
      ) : (
        <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <dt>Stage</dt><dd>{status.claim_stage}</dd>
          <dt>Next expected event</dt><dd>{status.next_expected_event ?? "—"}</dd>
          <dt>Customer action required</dt><dd>{status.customer_action_required ? "Yes" : "No"}</dd>
          <dt>Settlement amount</dt>
          <dd>{status.settlement_amount != null ? formatAedAmount(status.settlement_amount) : "Not disclosed at this level"}</dd>
        </dl>
      )}
    </div>
  );
}
```

`"Not disclosed at this level"` (rather than a blank cell) is deliberate — it makes the
redaction rule from `phase-1-backend-spec.md` §0.8 visible in the UI instead of looking like
missing data, which is the entire point of this panel per §0.4.

---

## 4. Calls domain (start + read)

### 4.1 API surface consumed

```text
POST /calls                     -> StartCallOutput   (StartCallInput body; Depends(require_outbound_enabled))
GET  /calls/{call_id}           -> CallAttemptRead
GET  /calls/{call_id}/outcome   -> CallAttemptRead    (identical shape — no separate outcome table, see 0.2)
```

`callHooks/callQueries.js` uses only `GET /calls/{call_id}` — `/outcome` is not called
separately since it returns the same `CallAttemptRead` shape; wiring both would be two
network calls for one row. `services/callService.js` still exports `getCallOutcome` (thin
wrapper) so a future need for the semantically distinct endpoint doesn't require touching the
service layer, but nothing in this phase's UI calls it — this is a one-line forward-compat
allowance, not built-ahead functionality.

### 4.2 `components/calls/form/StartCallForm.jsx` (sketch)

```jsx
import { useForm, Controller } from "react-hook-form";
import { yupResolver } from "@hookform/resolvers/yup";
import { useNavigate } from "react-router";
import { startCallSchema } from "@/validations/callSchemas";
import { useStartCall } from "@/hooks/callHooks/callMutations";
import { FormField, FormSelect } from "@/components/custom";
import { CALL_ANSWER_RESULTS } from "@/utils/constants"; // see 0.7

export function StartCallForm() {
  const navigate = useNavigate();
  const { control, handleSubmit, formState: { errors, isSubmitting } } = useForm({
    resolver: yupResolver(startCallSchema),
    defaultValues: { customerId: "", claimId: "", simulatedAnswerResult: "HUMAN_ANSWERED" },
  });
  const { mutateAsync: startCall } = useStartCall();

  const onSubmit = async (values) => {
    const { call_id } = await startCall(values);
    navigate(`/calls/${call_id}`);
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <Controller name="customerId" control={control} render={({ field }) => (
        <FormField {...field} label="Customer ID" error={errors.customerId?.message} />
      )} />
      <Controller name="claimId" control={control} render={({ field }) => (
        <FormField {...field} label="Claim ID" error={errors.claimId?.message} />
      )} />
      <Controller name="simulatedAnswerResult" control={control} render={({ field }) => (
        <FormSelect {...field} label="Simulated answer result" options={CALL_ANSWER_RESULTS}
                    error={errors.simulatedAnswerResult?.message} />
      )} />
      <button type="submit" disabled={isSubmitting} className="md:col-span-2">Start call</button>
    </form>
  );
}
```

Navigating straight to `/calls/${call_id}` on success is what makes §0.3's "reached by a
known id" model work in practice — the ops user never has to copy/paste the id the backend
just generated.

### 4.3 `hooks/callHooks/callMutations.js`

```javascript
import { useMutation } from "@tanstack/react-query";
import { startCall } from "@/services/callService";

export function useStartCall() {
  return useMutation({
    mutationFn: ({ customerId, claimId, simulatedAnswerResult }) =>
      startCall({ customer_id: customerId, claim_id: claimId, simulated_answer_result: simulatedAnswerResult }),
  });
}
```

### 4.4 `containers/CallDetailContainer.jsx`

Polls `useCallAttempt(callId)` (§0.6), renders `CallAttemptSummary` (disposition via
`DispositionBadge`, verification level, resolution, duration once available, a spinner/"call
in progress" state while `disposition_code` is still `null`), a link to
`/claims/${attempt.claim_id}` once the attempt loads, and `EscalationCreateForm` (§5.3) —
this is the one screen where both `claim_id` and `call_id` are simultaneously available
without the ops user typing either, which is why escalation creation lives here rather than
on the claim detail page (§0.3's "reached by a known id" constraint applies to forms too).

---

## 5. Actions & Escalations (create-only)

### 5.1 API surface consumed

```text
POST /claims/{claim_id}/actions       (Idempotency-Key required)  -> ActionRead
POST /claims/{claim_id}/escalations   (Idempotency-Key required)  -> EscalationRead
```

No read/list endpoint for either — a created `ClaimAction`/`Escalation` is not re-displayed
anywhere in this phase beyond the success toast and the `ActionRead`/`EscalationRead` object
the mutation resolves with. `components/actions/form/ActionCreateForm.jsx` renders that
result inline (action id + status) after a successful submit rather than navigating away,
since there's no detail page to navigate to.

### 5.2 `components/actions/form/ActionCreateForm.jsx` — Yup schema

```javascript
// validations/actionSchemas.js
import { object, string } from "yup";
import { ACTION_CODES } from "@/utils/constants";

export const actionCreateSchema = object({
  actionCode: string().oneOf(ACTION_CODES).required(),
  summary: string().required().max(1000),
  sourceCallId: string().nullable().default(null),
});

export const escalationCreateSchema = object({
  callId: string().required(),
  reason: string().required().max(1000),
});
```

`ACTION_CODES` mirrors `backend/src/actions/constants.py::ActionCode`'s 21 values verbatim
(§7.2) — unlike §0.8's complaint fields, `ActionCreate.action_code` **is** a real Pydantic
enum server-side, so this `.oneOf(...)` is a genuine mirror, not a courtesy over a gap.

### 5.3 `components/actions/form/EscalationCreateForm.jsx`

Rendered inside `CallDetailContainer` (§4.4) with `callId` passed as a prop, not a form
field — the ops user is already looking at that call, so re-typing its id would be pure
friction. Only `reason` is a real input; `EscalationCreate.context_snapshot` (a `dict`,
defaulting to `{}`) is **not** collected via this form — it's the automatic warm-transfer
context a live call's `human_request_detected` signal would populate (backend spec §3.2),
not something a dashboard user hand-authors as JSON. Submitting sends `context_snapshot: {}`
implicitly (the backend default applies when the field is omitted).

---

## 6. Complaints (create + read)

### 6.1 API surface consumed

```text
POST /complaints              -> ComplaintRead   (no Idempotency-Key header — see 0.5)
GET  /complaints/{complaint_id} -> ComplaintRead
```

No status-update endpoint exists (`Complaint.status` stays `"OPEN"` from this API's
perspective) — `ComplaintDetail.jsx` therefore renders `status` as a read-only badge, never
as an editable control, and no `ComplaintStatusUpdateForm` is built this phase (`CLAUDE.md`
§3.3 names one; it has nothing to submit to yet — see §8).

### 6.2 `components/complaints/form/ComplaintCreateForm.jsx`

Reads an optional `?claimId=` search param (set by `ClaimOverviewCard`'s quick action, §3.4)
to prefill `claimId`; `sourceCallId` is always a manual field since there's no call picker
(§0.3). On success, navigates to `/complaints/${complaint.id}` — the same "hand the ops user
the id" pattern as `StartCallForm` (§4.2).

### 6.3 `validations/complaintSchemas.js`

```javascript
import { object, string } from "yup";

const SEVERITIES = ["LOW", "MEDIUM", "HIGH"];               // see 0.8 — not backend-enforced yet
const CONTACT_METHODS = ["PHONE", "EMAIL", "SMS"];          // see 0.8 — not backend-enforced yet

export const complaintCreateSchema = object({
  claimId: string().required(),
  sourceCallId: string().required(),
  complaintCategory: string().required().max(64),
  customerStatementSummary: string().required().max(2000),
  customerExpectedResolution: string().nullable().max(500).default(null),
  severity: string().oneOf(SEVERITIES).required(),
  preferredContactMethod: string().oneOf(CONTACT_METHODS).required(),
});
```

### 6.4 `containers/ComplaintDetailContainer.jsx`

Renders `ComplaintDetail.jsx`: category, statement summary, expected resolution, severity,
status badge, and the two SLA deadlines (`acknowledgment_due_at`/`resolution_due_at`)
formatted with `utils/slaUtils.js`-style countdown text ("due in 18h" / "overdue by 2h").
**No `ComplaintSlaTimeline`** is built — `ComplaintSlaEvent` (the `AT_RISK`/`BREACHED`
history) has no read endpoint (§8), so there is no event history to render, only the two
`_due_at` timestamps `ComplaintRead` already carries. A future `GET
/complaints/{id}/sla-events` endpoint slots into this container without touching the rest of
the page.

---

## 7. Shared components & utilities

### 7.1 `components/common/IdLookupForm.jsx`

The one shared shape behind all three of §0.3's lookup fields:

```jsx
import { useState } from "react";
import { useNavigate } from "react-router";

export function IdLookupForm({ label, placeholder, basePath }) {
  const [id, setId] = useState("");
  const navigate = useNavigate();

  const onSubmit = (e) => {
    e.preventDefault();
    if (id.trim()) navigate(`${basePath}/${id.trim()}`);
  };

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-2 sm:flex-row">
      <input
        value={id}
        onChange={(e) => setId(e.target.value)}
        placeholder={placeholder}
        aria-label={label}
        className="flex-1 rounded border px-3 py-2"
      />
      <button type="submit">Look up</button>
    </form>
  );
}
```

Used as `<IdLookupForm label="Claim ID" placeholder="e.g. CLAIM-DEMO-001" basePath="/claims" />`
on `ClaimsPage`, and the equivalent for `/calls` and `/complaints`.

### 7.2 `utils/constants.js` (excerpt)

```javascript
// Mirrors backend/src/calls/constants.py::DispositionCode verbatim — do not reorder or
// abbreviate; DispositionBadge and any future disposition filter depend on exact string match.
export const DISPOSITION_CODES = [
  "SUCCESS_STATUS_DELIVERED", "SUCCESS_STATUS_AND_QUERY_RESOLVED", "SUCCESS_ACTION_CREATED",
  "SUCCESS_COMPLAINT_REGISTERED", "SUCCESS_HUMAN_TRANSFER", "CALLBACK_REQUESTED",
  "HUMAN_CALLBACK_REQUIRED", "RIGHT_PARTY_NOT_AVAILABLE", "WRONG_PARTY", "AUTH_FAILED",
  "AUTH_REFUSED", "CUSTOMER_TERMINATED_CALL", "NO_ANSWER", "LINE_BUSY", "CALL_REJECTED",
  "VOICEMAIL", "NUMBER_UNREACHABLE", "INVALID_CONTACT_NUMBER", "NETWORK_FAILURE",
  "AI_ESCALATED_LOW_CONFIDENCE", "AUTOMATED_CONTACT_UNSUCCESSFUL",
  "SPECIAL_CUSTOMER_CIRCUMSTANCE", "CONSENT_REFUSED", "COMMUNICATION_SUPPRESSION_REQUESTED",
  "ACCESSIBILITY_REQUIREMENT_DETECTED", "MINOR_ANSWERED", "DSAR_REQUESTED",
  "ADVERSARIAL_INPUT_DETECTED", "SECURITY_POLICY_ESCALATION", "INVALID_OR_UNAUTHORIZED_CLI",
  "CONCURRENT_CALL_CONFLICT", "SILENT_CALL_TECHNICAL_FAILURE", "BACKEND_SYSTEM_FAILURE",
  "DTMF_FALLBACK_ACTIVATED", "CUSTOMER_VULNERABILITY_INDICATED", "FRAUD_SUSPECTED",
  "CALL_DROPPED_PRE_AUTH", "CALL_DROPPED_POST_AUTH", "LLM_TIMEOUT", "STT_SERVICE_FAILURE",
  "TTS_SERVICE_FAILURE", "OTP_ATTEMPTS_EXCEEDED", "OTP_LOCKED",
  "HIGH_RISK_NUMBER_CHANGE_DETECTED", "COMPLAINT_SLA_AT_RISK", "COMPLAINT_SLA_BREACHED",
];

// Mirrors backend/src/actions/constants.py::ActionCode verbatim.
export const ACTION_CODES = [
  "CALLBACK_SCHEDULED", "CLAIM_DELAY_ESCALATION", "DOCUMENT_STATUS_DISPUTE",
  "DOCUMENT_SUBMISSION_LINK_REQUEST", "CLAIM_REVIEW_REQUEST", "COMPLAINT_CREATED",
  "HUMAN_CALLBACK_CREATED", "CUSTOMER_CONTACT_DETAILS_REVIEW", "GARAGE_CONTACT_REQUEST",
  "CLAIMS_TEAM_QUERY", "SPECIAL_CIRCUMSTANCE_REVIEW", "COMMUNICATION_SUPPRESSION",
  "DSAR_REQUEST_CREATED", "ACCESSIBLE_CHANNEL_REQUEST", "SECURITY_REVIEW_REQUEST",
  "VULNERABLE_CUSTOMER_SUPPORT_REQUEST", "FRAUD_SIU_REVIEW_REQUEST",
  "EVIDENCE_PRESERVATION_REQUEST", "TECHNICAL_RECOVERY_FOLLOWUP",
  "BACKEND_DATA_VERIFICATION_REQUEST", "COMPLAINT_SLA_ESCALATION",
];

export const VERIFICATION_LEVELS = ["L0", "L1", "L2"];

// Client-side courtesy allow-list only — backend field is an unconstrained str, see 0.7.
export const CALL_ANSWER_RESULTS = ["HUMAN_ANSWERED", "NO_ANSWER", "VOICEMAIL", "FAILED"];
```

`CLAIM_STAGES` (the 18 `ClaimStage` values) is added the same way the moment a component
first needs to render or filter by stage — `ClaimOverviewCard` just displays
`status.claim_stage` as received, so it doesn't need the array yet; adding it speculatively
would be exactly the empty-registry problem `phase-0-frontend-spec.md` §6 already flagged
once.

### 7.3 `utils/queryKeys.js`

```javascript
export const claimKeys = {
  all: ["claims"],
  detail: (id) => [...claimKeys.all, id],
  status: (id, level) => [...claimKeys.detail(id), "status", level],
  timeline: (id) => [...claimKeys.detail(id), "timeline"],
  documents: (id) => [...claimKeys.detail(id), "documents"],
  garage: (id) => [...claimKeys.detail(id), "garage"],
};

export const callKeys = {
  all: ["calls"],
  detail: (id) => [...callKeys.all, id],
};

export const complaintKeys = {
  all: ["complaints"],
  detail: (id) => [...complaintKeys.all, id],
};
```

No key factory for actions/escalations — per §5.1, neither has a read endpoint, so there is
no cached query for a mutation to invalidate. This is a direct reflection of the real
backend, not an oversight: the moment a list/read endpoint exists for either, its key factory
and the corresponding mutation's `onSuccess: () => queryClient.invalidateQueries(...)` land
together.

### 7.4 `components/Navbar.jsx`

The first real navigation — Phase 0 deferred this because there was only one route
(`phase-0-frontend-spec.md` §6). Per `CLAUDE.md` §3.7, mobile-collapsed by default (a
`useState` toggle, no external nav library needed for three links):

```jsx
import { useState } from "react";
import { Link } from "react-router";

const LINKS = [
  { to: "/claims", label: "Claims" },
  { to: "/calls", label: "Calls" },
  { to: "/complaints", label: "Complaints" },
];

export function Navbar() {
  const [open, setOpen] = useState(false);
  return (
    <nav className="border-b p-4">
      <div className="flex items-center justify-between">
        <span className="font-semibold">CallAgent Ops</span>
        <button className="md:hidden" onClick={() => setOpen(!open)} aria-label="Toggle navigation">☰</button>
        <ul className="hidden gap-4 md:flex">
          {LINKS.map((l) => <li key={l.to}><Link to={l.to}>{l.label}</Link></li>)}
        </ul>
      </div>
      {open && (
        <ul className="mt-2 flex flex-col gap-2 md:hidden">
          {LINKS.map((l) => <li key={l.to}><Link to={l.to} onClick={() => setOpen(false)}>{l.label}</Link></li>)}
        </ul>
      )}
    </nav>
  );
}
```

### 7.5 `App.jsx` (+)

```jsx
import { Routes, Route } from "react-router";
import { Navbar } from "@/components/Navbar";
import HealthPage from "@/pages/HealthPage";
import ClaimsPage from "@/pages/ClaimsPage";
import ClaimDetailPage from "@/pages/ClaimDetailPage";
import CallsPage from "@/pages/CallsPage";
import CallDetailPage from "@/pages/CallDetailPage";
import ComplaintsPage from "@/pages/ComplaintsPage";
import ComplaintDetailPage from "@/pages/ComplaintDetailPage";

export default function App() {
  return (
    <>
      <Navbar />
      <Routes>
        <Route path="/" element={<HealthPage />} />
        <Route path="/claims" element={<ClaimsPage />} />
        <Route path="/claims/:claimId" element={<ClaimDetailPage />} />
        <Route path="/calls" element={<CallsPage />} />
        <Route path="/calls/:callId" element={<CallDetailPage />} />
        <Route path="/complaints" element={<ComplaintsPage />} />
        <Route path="/complaints/:complaintId" element={<ComplaintDetailPage />} />
      </Routes>
    </>
  );
}
```

No route is wrapped in `ProtectedRoute` — still a pass-through stub with no backend `auth/`
to protect against (§0.2 point 3, unchanged from Phase 0 decision 1).

---

## 8. Explicitly deferred to later phases

Same discipline `phase-0-frontend-spec.md` §6 and `phase-1-backend-spec.md` §17 already
established:

- **`CampaignsPage`/`CallJobTable`/`CampaignForm`, `CliConfigList`/`ContactCalendarList`
  (Admin), `CustomerList`/`CustomerProfile`/`SuppressionStatusBadge`** — no backend router
  exists for `campaigns/`, `telephony/`, or `customers/` yet (§0.2). Nothing to build against.
- **`KillSwitchPanel`** — `src/config.py`'s five flags have no HTTP read/write surface.
  Needs a backend admin endpoint before this screen has anything to bind to.
- **Any list/table view** — `CrudTable`/`CrudDrawer` (`CLAUDE.md`'s generic lookup-CRUD
  engine) and `PaginationControls` have no consumer until a `GET /claims`, `GET /calls`, or
  `GET /complaints` list endpoint exists (§0.3). `src/pagination.py` on the backend is unused
  by any route today.
- **`EscalationQueue`/`CallbackQueue`, and any "acknowledge"/"complete" action on either** —
  escalations have no read/list endpoint (only create), and `Callback` has no router at all
  (`actions/service.py::schedule_callback()` exists but nothing calls it over HTTP). Building
  a queue screen with nothing to populate it, or a `useOptimistic` acknowledge action with no
  endpoint to call, would be dead code.
- **`ComplaintStatusUpdateForm`, `ComplaintSlaTimeline`** — no status-update endpoint, no
  `ComplaintSlaEvent` read endpoint (§6.4).
- **`TranscriptViewer`, `CallEventLog`, `LatencyMetricsPanel`, `CallAttemptTimeline`
  (multi-attempt)** — `CallEvent`/`CallTranscript`/`CallSummary`/`CustomerIntent`/
  `SentimentEvent` don't exist as backend models in Phase 1 (only `CallAttempt`/
  `CallSession`); these need Phase 2's real conversation content and Phase 3's redaction
  pipeline before there's anything to render.
- **`SecurityReviewPage` and everything RBAC-gated (`RoleGate.jsx` with real logic)** —
  blocked on the still-unscheduled `auth/` backend domain (§0.2 point 3,
  `phase-0-frontend-spec.md` decision 1, still an open question for whoever owns
  `IMPLEMENTATION_PLAN.md`).
- **`DashboardPage`, `AnalyticsPage`, `OutcomeFunnelChart`, `NoAnswerAnalytics`,
  `StatusAnalytics`, `CustomerExperienceAnalytics`** — explicitly Phase 3's job (§0.1).
- **`fetchClient`'s 401-refresh-retry** — still blocked on the same missing `auth/` backend,
  unchanged from Phase 0 decision 2.
- **A real `Footer.jsx`** — no content has ever been proposed for one; still not needed for
  a six-page operational app.

---

## 9. Manual verification (no domain test runner added this phase)

`phase-0-frontend-spec.md` §5 deliberately shipped no test step ("a single manual smoke
check covers it more cheaply than adding a test runner for one file"). Phase 1 adds real
forms and real cross-page navigation, so the smoke check grows to a short manual script run
against a live backend (`docker-compose up`, `scripts/seed_demo_data.py` already run) — still
not a reason to add a component test runner for six pages:

1. `IdLookupForm` on `/claims` with a seeded demo claim id navigates to and correctly renders
   `/claims/:claimId`'s five tabs.
2. `ClaimStatusPanel`'s verification-level selector, on a claim in `SETTLEMENT_APPROVED` or
   `PAYMENT_INITIATED` stage, shows `settlement_amount` at `L2` and "Not disclosed at this
   level" at `L0`/`L1` — the one behavior this whole domain exists to prove (§0.4).
3. `StartCallForm` with a seeded customer/claim id and `simulated_answer_result =
   HUMAN_ANSWERED` navigates to `/calls/:callId`, which polls and eventually shows a non-null
   `disposition_code` without a manual refresh (§0.6).
4. `EscalationCreateForm` on that same call-detail page succeeds and returns a real
   `EscalationRead.id` — confirms the `Idempotency-Key` header is actually being sent (a
   missing header 422s, per `actions/router.py`).
5. `ActionCreateForm` from a claim's quick action succeeds twice in a row with the form left
   mounted between submits (not remounted) and — if manually re-submitted without changing
   inputs — returns the *same* `ActionRead.id` both times, proving the idempotency key reuse
   from §0.5 actually works end-to-end, not just in the code sketch.
6. `ComplaintCreateForm`, reached via `ClaimOverviewCard`'s "File a complaint" link, arrives
   with `claimId` prefilled from the query param; on submit, navigates to
   `/complaints/:complaintId`, which shows both SLA due-at timestamps.
7. Resize each of the six pages to ~375px, ~768px, ~1280px (`CLAUDE.md` §3.7) — `Navbar`
   collapses below `md`, every form stacks to one column below `md`.
8. `npm run build` and `npm run lint` both pass clean.

---

## 10. Exit criteria traceability

| Backend capability (Phase 1) | Frontend screen proving it's reachable |
|---|---|
| `GET /claims/{id}/status` verification-level redaction (backend spec §0.8) | `ClaimStatusPanel`, §3.5/§0.4 |
| `POST /calls` ad-hoc single-attempt entry point (backend spec §13) | `StartCallForm` + polling `CallDetailContainer`, §4 |
| Disposition codes reaching a terminal state (backend spec §9) | `CallAttemptSummary` + `DispositionBadge`, §4.4 |
| `Idempotency-Key`-gated action/escalation creation (backend spec §8.1) | `ActionCreateForm`/`EscalationCreateForm`, §5, verified per §9.5 |
| Complaint creation + server-computed SLA timestamps (backend spec §0.9) | `ComplaintCreateForm` + `ComplaintDetail`'s due-at display, §6 |
| Claim read domain (status/timeline/documents/garage) (backend spec §4) | `ClaimDetailContainer`'s four remaining tabs, §3.4 |

Everything else in `phases/phase-1-deterministic-core.md`'s 15-branch exit criteria (e.g.
`OTP LIMIT → lockout`, `CALL DROP → auth expires`, `CONCURRENT CALL → AI attempt aborted`) is
proven by the backend's own fake/text harness (`tests/integration/test_phase1_e2e.py`) and
has no dashboard-observable surface in Phase 1 beyond the final `disposition_code` this
spec's `CallDetailContainer` already displays — there is no dedicated frontend flow for
driving OTP/call-drop/concurrency scenarios manually, since `StartCallForm`'s
`simulated_answer_result` only covers the dial-outcome branch, not the in-call signal
sequence the harness drives (backend spec §0.5's `CustomerIntentSignal` variants have no HTTP
entry point at all — they're Temporal signals, not REST).

---
**Companion documents:** [`phase-1-backend-spec.md`](./phase-1-backend-spec.md) (backend this
spec builds against) · [`phase-0-frontend-spec.md`](./phase-0-frontend-spec.md) (this phase's
starting code state)
