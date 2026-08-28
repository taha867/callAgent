import { useClaimTimeline } from "@/hooks/claimHooks/claimQueries";

export function ClaimStatusTimeline({ claimId }) {
  const { data: events, isLoading, isError } = useClaimTimeline(claimId);

  if (isLoading) return <p>Loading…</p>;
  if (isError) return <p className="text-destructive">Could not load the timeline.</p>;
  if (!events) return null;
  if (events.length === 0) return <p className="text-muted-foreground">No status events yet.</p>;

  return (
    <ol className="space-y-3">
      {events.map((event) => (
        <li key={event.id} className="border-l-2 border-border pl-3">
          <p className="text-sm text-muted-foreground">
            {new Date(event.event_timestamp).toLocaleString()}
          </p>
          <p>
            {event.from_stage ? `${event.from_stage} → ${event.to_stage}` : event.to_stage}
          </p>
          {event.note && <p className="text-sm text-muted-foreground">{event.note}</p>}
        </li>
      ))}
    </ol>
  );
}
