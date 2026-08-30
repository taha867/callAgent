import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { PaginationControls } from "@/components/common/PaginationControls";
import { DefectStatusBadge } from "@/components/qa/DefectStatusBadge";
import { useDefectList } from "@/hooks/qaHooks/qaQueries";

// Same guard order as StatusAnalyticsTable.jsx. Wrapped in overflow-x-auto per
// CLAUDE.md §3.7's table rule — Title/Journey/Occurrences/Status is exactly the column
// count that overflows a phone screen.
export function DefectLogTable({ page, onPageChange, onSelect }) {
  const { data, isLoading, isError } = useDefectList({ page });

  if (isLoading) return <p className="text-muted-foreground">Loading defect log…</p>;
  if (isError || !data) return <p className="text-destructive">Could not load the defect log.</p>;
  if (data.items.length === 0) return <p className="text-muted-foreground">No defects logged yet.</p>;

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead>Journey</TableHead>
              <TableHead>Occurrences</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.items.map((entry) => (
              <TableRow
                key={entry.id}
                onClick={() => onSelect(entry.id)}
                className="cursor-pointer"
              >
                <TableCell>{entry.title}</TableCell>
                <TableCell>{entry.demo_journey_id ?? "—"}</TableCell>
                <TableCell>{entry.occurrence_count}</TableCell>
                <TableCell>
                  <DefectStatusBadge entry={entry} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <PaginationControls page={data.page} totalPages={data.total_pages} onPageChange={onPageChange} />
    </div>
  );
}
