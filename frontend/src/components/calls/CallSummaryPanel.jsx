import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useCallSummary } from "@/hooks/callHooks/callQueries";

// Never log summary_text — same rule as CallTranscriptViewer (spec §0.7). GET
// /calls/{id}/summary returns null (200, not 404) when generate_call_summary hasn't
// produced a row yet — that's a valid, expected state, not an error.
export function CallSummaryPanel({ callId }) {
  const { data, isLoading, isError } = useCallSummary(callId);

  if (isLoading) return <Skeleton className="h-20 w-full" />;
  if (isError) return <p className="text-destructive">Could not load the call summary.</p>;
  if (!data) return <p className="text-muted-foreground">Summary not yet available.</p>;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground">Call summary</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm">{data.summary_text}</p>
      </CardContent>
    </Card>
  );
}
