import { useState } from "react";
import { useClaimStatus } from "@/hooks/claimHooks/claimQueries";
import { formatAedAmount } from "@/utils/currencyUtils";
import { VERIFICATION_LEVELS } from "@/utils/constants";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// The verification-level selector is a QA/inspection control, not a login — it lets an ops
// user *preview* claims/service.py::get_disclosable_status()'s redaction rule (settlement
// amount withheld below L2) without a real call session. See phase-1-frontend-spec.md §0.4.
export function ClaimStatusPanel({ claimId }) {
  const [verificationLevel, setVerificationLevel] = useState("L0");
  const { data: status, isLoading, isError } = useClaimStatus(claimId, verificationLevel);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-1.5 sm:max-w-xs">
        <Label htmlFor="verification-level">Preview as verification level</Label>
        <Select value={verificationLevel} onValueChange={setVerificationLevel}>
          <SelectTrigger id="verification-level" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {VERIFICATION_LEVELS.map((level) => (
              <SelectItem key={level} value={level}>
                {level}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {isLoading && <p>Loading…</p>}
      {isError && <p className="text-destructive">Could not load claim status.</p>}
      {status && (
        <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <dt className="text-muted-foreground">Stage</dt>
          <dd>{status.claim_stage}</dd>
          <dt className="text-muted-foreground">Next expected event</dt>
          <dd>{status.next_expected_event ?? "—"}</dd>
          <dt className="text-muted-foreground">Expected by</dt>
          <dd>{status.expected_by ? new Date(status.expected_by).toLocaleString() : "—"}</dd>
          <dt className="text-muted-foreground">Customer action required</dt>
          <dd>{status.customer_action_required ? "Yes" : "No"}</dd>
          <dt className="text-muted-foreground">Settlement amount</dt>
          <dd>
            {status.settlement_amount != null
              ? formatAedAmount(status.settlement_amount)
              : "Not disclosed at this level"}
          </dd>
        </dl>
      )}
    </div>
  );
}
