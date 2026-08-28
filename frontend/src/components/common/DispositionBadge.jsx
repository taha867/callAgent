import { Badge } from "@/components/ui/badge";

// Bucket all 45 DispositionCode values into ui/badge's variants by semantic meaning.
// See phase-1-frontend-spec.md §7.2 for the full enum this must stay in sync with.
const DESTRUCTIVE_CODES = new Set([
  "AUTH_FAILED", "AUTH_REFUSED", "FRAUD_SUSPECTED", "SECURITY_POLICY_ESCALATION",
  "ADVERSARIAL_INPUT_DETECTED", "OTP_ATTEMPTS_EXCEEDED", "OTP_LOCKED",
  "CONCURRENT_CALL_CONFLICT", "COMPLAINT_SLA_BREACHED", "HIGH_RISK_NUMBER_CHANGE_DETECTED",
  "CUSTOMER_VULNERABILITY_INDICATED", "INVALID_OR_UNAUTHORIZED_CLI", "NETWORK_FAILURE",
  "SILENT_CALL_TECHNICAL_FAILURE", "BACKEND_SYSTEM_FAILURE",
]);

function variantFor(dispositionCode) {
  if (!dispositionCode) return "secondary";
  if (dispositionCode.startsWith("SUCCESS_")) return "default";
  if (DESTRUCTIVE_CODES.has(dispositionCode) || dispositionCode.endsWith("_FAILURE")) {
    return "destructive";
  }
  return "secondary";
}

export function DispositionBadge({ dispositionCode }) {
  if (!dispositionCode) {
    return <Badge variant="secondary">In progress</Badge>;
  }
  return <Badge variant={variantFor(dispositionCode)}>{dispositionCode}</Badge>;
}
