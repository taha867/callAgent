import { Link } from "react-router";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DispositionBadge } from "@/components/common/DispositionBadge";

export function CallAttemptSummary({ attempt }) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle>Call {attempt.id}</CardTitle>
        <DispositionBadge dispositionCode={attempt.disposition_code} />
      </CardHeader>
      <CardContent className="space-y-2">
        {!attempt.disposition_code && (
          <p className="text-muted-foreground">Call in progress — this page updates automatically.</p>
        )}
        <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <dt className="text-muted-foreground">Customer reached</dt>
          <dd>{attempt.customer_reached ? "Yes" : "No"}</dd>
          <dt className="text-muted-foreground">Right party</dt>
          <dd>{attempt.right_party == null ? "—" : attempt.right_party ? "Yes" : "No"}</dd>
          <dt className="text-muted-foreground">Verified</dt>
          <dd>{attempt.verified ? `Yes (${attempt.verification_level})` : "No"}</dd>
          <dt className="text-muted-foreground">Status delivered</dt>
          <dd>{attempt.status_delivered ?? "—"}</dd>
          <dt className="text-muted-foreground">Resolution</dt>
          <dd>{attempt.resolution ?? "—"}</dd>
          <dt className="text-muted-foreground">Duration</dt>
          <dd>{attempt.duration_seconds != null ? `${attempt.duration_seconds}s` : "—"}</dd>
        </dl>
        <Link to={`/claims/${attempt.claim_id}`} className="text-primary underline-offset-4 hover:underline">
          View claim {attempt.claim_id}
        </Link>
      </CardContent>
    </Card>
  );
}
