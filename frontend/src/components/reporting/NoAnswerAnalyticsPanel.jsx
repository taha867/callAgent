import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { StatTile } from "@/components/common/StatTile";
import { useNoAnswerAnalytics } from "@/hooks/reportingHooks/reportingQueries";
import { formatPercent } from "@/utils/metricsUtils";

const hourChartConfig = {
  no_answer_count: { label: "No-answer count", color: "var(--chart-3)" },
};

export function NoAnswerAnalyticsPanel({ since, until }) {
  const { data, isLoading, isError } = useNoAnswerAnalytics(since, until);

  if (isLoading) return <p className="text-muted-foreground">Loading no-answer analytics…</p>;
  if (isError || !data) return <p className="text-destructive">Could not load no-answer analytics.</p>;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatTile label="Rejected" value={data.rejected_count} />
        <StatTile label="Voicemail" value={data.voicemail_count} />
        <StatTile label="Unreachable" value={data.unreachable_count} />
        <StatTile label="Successful callbacks" value={data.successful_callbacks} />
      </div>

      <div>
        <h3 className="mb-2 text-sm font-medium text-muted-foreground">No-answer by hour</h3>
        <ChartContainer config={hourChartConfig} className="min-h-[220px] w-full">
          <BarChart data={data.by_hour}>
            <CartesianGrid vertical={false} />
            <XAxis dataKey="hour" tickLine={false} axisLine={false} />
            <YAxis allowDecimals={false} />
            <ChartTooltip content={<ChartTooltipContent />} />
            <Bar dataKey="no_answer_count" fill="var(--color-no_answer_count)" radius={4} />
          </BarChart>
        </ChartContainer>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-medium text-muted-foreground">No-answer by day</h3>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Day</TableHead>
              <TableHead>No-answer</TableHead>
              <TableHead>Total</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.by_day.map((row) => (
              <TableRow key={row.day}>
                <TableCell>{row.day}</TableCell>
                <TableCell>{row.no_answer_count}</TableCell>
                <TableCell>{row.total_count}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-medium text-muted-foreground">Answer rate by attempt number</h3>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Attempt #</TableHead>
              <TableHead>Answer rate</TableHead>
              <TableHead>Total</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.by_attempt_number.map((row) => (
              <TableRow key={row.attempt_number}>
                <TableCell>{row.attempt_number}</TableCell>
                <TableCell>{formatPercent(row.answer_rate)}</TableCell>
                <TableCell>{row.total_count}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
