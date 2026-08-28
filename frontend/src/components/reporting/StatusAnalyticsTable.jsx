import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useStatusAnalytics } from "@/hooks/reportingHooks/reportingQueries";
import { formatPercent } from "@/utils/metricsUtils";

// GET /reporting/status-analytics returns a bare array, not a wrapped object.
export function StatusAnalyticsTable({ since, until }) {
  const { data, isLoading, isError } = useStatusAnalytics(since, until);

  if (isLoading) return <p className="text-muted-foreground">Loading status analytics…</p>;
  if (isError || !data) return <p className="text-destructive">Could not load status analytics.</p>;
  if (data.length === 0) return <p className="text-muted-foreground">No statuses delivered in this range.</p>;

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Status</TableHead>
          <TableHead>Total calls</TableHead>
          <TableHead>Question rate</TableHead>
          <TableHead>Escalation rate</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {data.map((row) => (
          <TableRow key={row.status}>
            <TableCell>{row.status}</TableCell>
            <TableCell>{row.total_calls}</TableCell>
            <TableCell>{formatPercent(row.question_rate)}</TableCell>
            <TableCell>{formatPercent(row.escalation_rate)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
