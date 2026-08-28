import { StatTile } from "@/components/common/StatTile";
import { useEscalationAnalytics } from "@/hooks/reportingHooks/reportingQueries";

// by_status/by_reason are { [key]: count } dicts — same "absent key = zero" discipline as
// CustomerExperiencePanel's sentiment breakdowns.
function CountBreakdown({ title, breakdown }) {
  const entries = Object.entries(breakdown);
  return (
    <div>
      <h3 className="mb-2 text-sm font-medium text-muted-foreground">{title}</h3>
      {entries.length === 0 ? (
        <p className="text-muted-foreground">No data for this range.</p>
      ) : (
        <ul className="space-y-1">
          {entries.map(([key, count]) => (
            <li key={key} className="flex justify-between text-sm">
              <span>{key}</span>
              <span className="font-medium">{count}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function EscalationAnalyticsPanel({ since, until }) {
  const { data, isLoading, isError } = useEscalationAnalytics(since, until);

  if (isLoading) return <p className="text-muted-foreground">Loading escalation analytics…</p>;
  if (isError || !data) return <p className="text-destructive">Could not load escalation analytics.</p>;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-2">
        <StatTile label="Total escalations" value={data.total_escalations} />
        <StatTile label="Warm transfers" value={data.warm_transfer_count} />
      </div>
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
        <CountBreakdown title="By status" breakdown={data.by_status} />
        <CountBreakdown title="By reason" breakdown={data.by_reason} />
      </div>
    </div>
  );
}
