import { StatTile } from "@/components/common/StatTile";
import { useGovernanceSummary } from "@/hooks/qaHooks/qaQueries";

// Same loading/error guard order as StatusAnalyticsTable.jsx.
export function GovernanceSummaryHeader() {
  const { data, isLoading, isError } = useGovernanceSummary();

  if (isLoading) return <p className="text-muted-foreground">Loading governance summary…</p>;
  if (isError || !data) {
    return <p className="text-destructive">Could not load the governance summary.</p>;
  }

  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
      <StatTile label="Total defects" value={data.total_defects} />
      <StatTile label="Open" value={data.open_defects} />
      <StatTile
        label="Compilation required"
        value={data.compilation_required_count}
        hint={data.compilation_required_count > 0 ? "Two-strike rule pending" : "All clear"}
      />
      <StatTile label="Journeys passing" value={`${data.journeys_passing} / ${data.journeys_total}`} />
    </div>
  );
}
