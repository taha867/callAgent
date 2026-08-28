import { useParams } from "react-router";
import { useCallAttempt } from "@/hooks/callHooks/callQueries";
import { CallAttemptSummary } from "@/components/calls/CallAttemptSummary";
import { EscalationCreateForm } from "@/components/actions/form/EscalationCreateForm";

// The one screen where both claim_id and call_id are simultaneously available without the
// ops user typing either — this is why escalation creation lives here rather than on the
// claim detail page. See phase-1-frontend-spec.md §4.4.
export default function CallDetailContainer() {
  const { callId } = useParams();
  const { data: attempt, isLoading, isError } = useCallAttempt(callId);

  if (isLoading) return <p>Loading…</p>;
  if (isError) return <p className="text-destructive">Could not load this call.</p>;
  if (!attempt) return null;

  return (
    <div className="space-y-6">
      <CallAttemptSummary attempt={attempt} />
      <EscalationCreateForm claimId={attempt.claim_id} callId={attempt.id} />
    </div>
  );
}
