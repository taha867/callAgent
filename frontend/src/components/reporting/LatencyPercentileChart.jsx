import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";

const chartConfig = {
  ms: { label: "Latency (ms)", color: "var(--chart-2)" },
};

// Takes the OperationsOverviewRead result as a PROP, does not call useOperationsOverview
// itself — one query, shared with OperationsOverviewGrid via TanStack Query's own
// cache-sharing, avoiding a redundant fetch for a value the parent container already has
// in hand. See .claude/specs/phase-3-frontend-spec.md §3.8.
export function LatencyPercentileChart({ data }) {
  if (!data) return null;

  const chartData = [
    { percentile: "P50", ms: data.latency_p50_ms },
    { percentile: "P95", ms: data.latency_p95_ms },
    { percentile: "P99", ms: data.latency_p99_ms },
  ];

  const hasData = chartData.some((row) => row.ms != null);
  if (!hasData) {
    return <p className="text-muted-foreground">No latency samples recorded for this range yet.</p>;
  }

  return (
    <ChartContainer config={chartConfig} className="min-h-[240px] w-full">
      <BarChart data={chartData}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="percentile" tickLine={false} axisLine={false} />
        <YAxis allowDecimals={false} />
        <ChartTooltip content={<ChartTooltipContent />} />
        <Bar dataKey="ms" fill="var(--color-ms)" radius={4} />
      </BarChart>
    </ChartContainer>
  );
}
