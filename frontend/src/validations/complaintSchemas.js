import { object, string } from "yup";
import { COMPLAINT_SEVERITIES, COMPLAINT_CONTACT_METHODS } from "@/utils/constants";

// severity / preferredContactMethod are backend-unconstrained plain strings today
// (ComplaintCreate.severity / .preferred_contact_method) — this .oneOf(...) is the frontend
// compensating for that gap, not a mirror of a real Pydantic constraint. See
// phase-1-frontend-spec.md decision 0.8.
export const complaintCreateSchema = object({
  claimId: string().required("Claim ID is required"),
  sourceCallId: string().required("Source call ID is required"),
  complaintCategory: string().required("Category is required").max(64),
  customerStatementSummary: string().required("Statement summary is required").max(2000),
  customerExpectedResolution: string().nullable().max(500).default(null),
  severity: string().oneOf(COMPLAINT_SEVERITIES).required("Severity is required"),
  preferredContactMethod: string().oneOf(COMPLAINT_CONTACT_METHODS).required("Contact method is required"),
});
