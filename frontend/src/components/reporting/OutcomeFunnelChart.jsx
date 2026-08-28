import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { useOutcomeFunnel } from "@/hooks/reportingHooks/reportingQueries";
import { formatPercent } from "@/utils/metricsUtils";

const chartConfig = {
  count: { label: "Calls", color: "var(--chart-1)" },
};

export function OutcomeFunnelChart({ since, until }) {
  const { data, isLoading, isError } = useOutcomeFunnel(since, until);

  if (isLoading) return <p className="text-muted-foreground">Loading outcome funnel…</p>;
  if (isError || !data) return <p className="text-destructive">Could not load outcome funnel.</p>;

  return (
    <ChartContainer config={chartConfig} className="min-h-[240px] w-full">
      <BarChart data={data.stages}>
        <CartesianGrid vertical={false} />
        <XAxis
          dataKey="stage"
          tickLine={false}
          axisLine={false}
          interval={0}
          angle={-20}
          textAnchor="end"
          height={60}
        />
        <YAxis allowDecimals={false} />
        <ChartTooltip
          content={
            <ChartTooltipContent
              formatter={(value, _name, item) => [
                `${value} (${
                  item.payload.conversion_from_previous != null
                    ? formatPercent(item.payload.conversion_from_previous)
                    : "—"
                })`,
                "Calls",
              ]}
            />
          }
        />
        <Bar dataKey="count" fill="var(--color-count)" radius={4} />
      </BarChart>
    </ChartContainer>
  );
}
