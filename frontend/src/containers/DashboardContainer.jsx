import { useState } from "react";
import { DateRangeFilter } from "@/components/reporting/DateRangeFilter";
import { OperationsOverviewGrid } from "@/components/reporting/OperationsOverviewGrid";
import { OutcomeFunnelChart } from "@/components/reporting/OutcomeFunnelChart";
import { LatencyPercentileChart } from "@/components/reporting/LatencyPercentileChart";
import { useOperationsOverview } from "@/hooks/reportingHooks/reportingQueries";
import { defaultDateRange } from "@/utils/metricsUtils";

export default function DashboardContainer() {
  const [{ since, until }, setRange] = useState(defaultDateRange());
  // Shared with OperationsOverviewGrid via TanStack Query's cache — LatencyPercentileChart
  // reads this result as a prop rather than firing its own query (spec §3.8).
  const { data: overview } = useOperationsOverview(since, until);

  return (
    <div className="space-y-6">
      <DateRangeFilter
        since={since}
        until={until}
        onChange={(newSince, newUntil) => setRange({ since: newSince, until: newUntil })}
      />
      <OperationsOverviewGrid since={since} until={until} />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <OutcomeFunnelChart since={since} until={until} />
        <LatencyPercentileChart data={overview} />
      </div>
    </div>
  );
}
