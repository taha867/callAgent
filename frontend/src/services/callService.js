import { fetchClient } from "@/middleware/fetchClient";
import { unwrapResponse } from "@/utils/unwrapResponse";

export const startCall = ({ customerId, claimId, simulatedAnswerResult }) =>
  unwrapResponse(
    fetchClient("/calls", {
      method: "POST",
      body: {
        customer_id: customerId,
        claim_id: claimId,
        simulated_answer_result: simulatedAnswerResult,
      },
    }),
  );

export const getCallAttempt = (callId) => unwrapResponse(fetchClient(`/calls/${callId}`));

// Same response shape as getCallAttempt (no separate outcome table) — not called by this
// phase's UI, kept as a one-line forward-compat allowance. See spec §4.1.
export const getCallOutcome = (callId) =>
  unwrapResponse(fetchClient(`/calls/${callId}/outcome`));

export const getCallTranscript = (callId) =>
  unwrapResponse(fetchClient(`/calls/${callId}/transcript`));

// Can resolve to `null` (200 OK) — the backend returns null, not 404, when
// generate_call_summary hasn't produced a row yet. unwrapResponse passes null through
// unchanged as long as ok is true; CallSummaryPanel handles that branch itself.
export const getCallSummary = (callId) => unwrapResponse(fetchClient(`/calls/${callId}/summary`));

export const getCallIntents = (callId) => unwrapResponse(fetchClient(`/calls/${callId}/intents`));

export const getCallSentiment = (callId) =>
  unwrapResponse(fetchClient(`/calls/${callId}/sentiment`));
