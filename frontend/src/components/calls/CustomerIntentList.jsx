import { Badge } from "@/components/ui/badge";
import { useCallIntents } from "@/hooks/callHooks/callQueries";

export function CustomerIntentList({ callId }) {
  const { data, isLoading, isError } = useCallIntents(callId);

  if (isLoading) return <p className="text-muted-foreground">Loading intents…</p>;
  if (isError) return <p className="text-destructive">Could not load customer intents.</p>;
  // An empty list is a valid state — e.g. a WRONG_PARTY call never reached the follow-up
  // stage that produces CustomerIntent rows.
  if (!data || data.length === 0) {
    return <p className="text-muted-foreground">No customer intents recorded for this call.</p>;
  }

  return (
    <ul className="space-y-3">
      {data.map((intent) => (
        <li key={intent.id} className="flex items-start gap-3">
          <Badge variant="secondary">{intent.intent}</Badge>
          <div className="flex-1 text-sm">
            {intent.topic && <p className="font-medium">{intent.topic}</p>}
            {intent.summary && <p className="text-muted-foreground">{intent.summary}</p>}
          </div>
        </li>
      ))}
    </ul>
  );
}
