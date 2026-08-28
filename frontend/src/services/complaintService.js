import { fetchClient } from "@/middleware/fetchClient";
import { unwrapResponse } from "@/utils/unwrapResponse";

// No Idempotency-Key header — POST /complaints derives its idempotency key server-side from
// source_call_id/claim_id (backend spec §8.1). See phase-1-frontend-spec.md decision 0.5.
export const createComplaint = ({
  claimId,
  sourceCallId,
  complaintCategory,
  customerStatementSummary,
  customerExpectedResolution,
  severity,
  preferredContactMethod,
}) =>
  unwrapResponse(
    fetchClient("/complaints", {
      method: "POST",
      body: {
        claim_id: claimId,
        source_call_id: sourceCallId,
        complaint_category: complaintCategory,
        customer_statement_summary: customerStatementSummary,
        customer_expected_resolution: customerExpectedResolution ?? null,
        severity,
        preferred_contact_method: preferredContactMethod,
      },
    }),
  );

export const getComplaint = (complaintId) =>
  unwrapResponse(fetchClient(`/complaints/${complaintId}`));
