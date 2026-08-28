import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatDueIn } from "@/utils/slaUtils";

// No ComplaintSlaEvent (AT_RISK/BREACHED) read endpoint exists yet — the two due-at
// timestamps ComplaintRead already carries are the only SLA signal available in Phase 1.
// See phase-1-frontend-spec.md §6.4.
export function ComplaintDetail({ complaint }) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle>Complaint {complaint.id}</CardTitle>
        <Badge variant={complaint.status === "OPEN" ? "secondary" : "default"}>
          {complaint.status}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-3">
        <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <dt className="text-muted-foreground">Category</dt>
          <dd>{complaint.complaint_category}</dd>
          <dt className="text-muted-foreground">Severity</dt>
          <dd>{complaint.severity}</dd>
          <dt className="text-muted-foreground">Preferred contact method</dt>
          <dd>{complaint.preferred_contact_method}</dd>
          <dt className="text-muted-foreground">Acknowledgment</dt>
          <dd>{formatDueIn(complaint.acknowledgment_due_at)}</dd>
          <dt className="text-muted-foreground">Resolution</dt>
          <dd>{formatDueIn(complaint.resolution_due_at)}</dd>
        </dl>
        <div>
          <p className="text-muted-foreground">Customer statement</p>
          <p>{complaint.customer_statement_summary}</p>
        </div>
        {complaint.customer_expected_resolution && (
          <div>
            <p className="text-muted-foreground">Customer expected resolution</p>
            <p>{complaint.customer_expected_resolution}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
