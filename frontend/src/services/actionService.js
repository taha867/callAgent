import { fetchClient } from "@/middleware/fetchClient";
import { unwrapResponse } from "@/utils/unwrapResponse";

// POST /claims/{claim_id}/actions requires an Idempotency-Key header (not a body field) —
// see phase-1-frontend-spec.md decision 0.5. The key is minted once per form mount by the
// calling mutation hook, not regenerated here.
export const createAction = (claimId, { actionCode, summary, sourceCallId }, idempotencyKey) =>
  unwrapResponse(
    fetchClient(`/claims/${claimId}/actions`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: {
        claim_id: claimId,
        action_code: actionCode,
        summary,
        source_call_id: sourceCallId ?? null,
      },
    }),
  );

// EscalationCreate has no claim_id field — the claim_id in the URL is only for route
// validation (Depends(valid_claim)); the created Escalation row associates via call_id only.
// context_snapshot is intentionally omitted here — it's populated by the live-call workflow,
// not hand-authored from the dashboard (spec §5.3).
export const createEscalation = (claimId, { callId, reason }, idempotencyKey) =>
  unwrapResponse(
    fetchClient(`/claims/${claimId}/escalations`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: { call_id: callId, reason },
    }),
  );
