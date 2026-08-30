import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { DefectStatusBadge } from "@/components/qa/DefectStatusBadge";
import { DefectStatusUpdateForm } from "@/components/qa/form/DefectStatusUpdateForm";
import { useDefect } from "@/hooks/qaHooks/qaQueries";

export function DefectDetailPanel({ entryId, onClose }) {
  const { data: entry, isLoading, isError } = useDefect(entryId);

  if (isLoading) return <p className="text-muted-foreground">Loading defect…</p>;
  if (isError || !entry) return <p className="text-destructive">Could not load this defect.</p>;

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div>
          <CardTitle>{entry.title}</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">{entry.defect_shape_key}</p>
        </div>
        <div className="flex items-center gap-2">
          <DefectStatusBadge entry={entry} />
          <Button type="button" variant="ghost" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <dl className="grid grid-cols-2 gap-2 text-sm md:grid-cols-4">
          <div>
            <dt className="text-muted-foreground">Journey</dt>
            <dd>{entry.demo_journey_id ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Scenario</dt>
            <dd>{entry.adversarial_scenario_id ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Occurrences</dt>
            <dd>{entry.occurrence_count}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Severity</dt>
            <dd>{entry.severity}</dd>
          </div>
        </dl>
        {entry.notes && <p className="whitespace-pre-wrap text-sm">{entry.notes}</p>}
        {/* No onSuccess close here on purpose — the mutation invalidates qa/'s queries, so
            this panel re-renders in place with the updated status/badge; closing it would
            hide the very confirmation the user just asked to see. */}
        <DefectStatusUpdateForm entry={entry} />
      </CardContent>
    </Card>
  );
}
