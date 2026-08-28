import { SentimentBadge } from "@/components/common/SentimentBadge";
import { useCallSentiment } from "@/hooks/callHooks/callQueries";

// turn_index !== null rows are per-turn readings (the live classifier, spec §4.1 of the
// backend spec); turn_index === null rows are call-level markers — the call-start
// REPEATED_CONTACT flag and the call-end final-sentiment row generate_call_summary writes.
// These are rendered separately, never mixed into the turn-indexed list, since they don't
// have a real turn number to display.
export function SentimentTimeline({ callId }) {
  const { data, isLoading, isError } = useCallSentiment(callId);

  if (isLoading) return <p className="text-muted-foreground">Loading sentiment…</p>;
  if (isError) return <p className="text-destructive">Could not load sentiment.</p>;
  if (!data || data.length === 0) {
    return <p className="text-muted-foreground">No sentiment recorded for this call.</p>;
  }

  const perTurn = data.filter((row) => row.turn_index !== null);
  const callLevel = data.filter((row) => row.turn_index === null);

  return (
    <div className="space-y-6">
      {perTurn.length > 0 && (
        <ol className="space-y-2">
          {perTurn.map((row) => (
            <li key={row.id} className="flex items-center gap-3">
              <span className="w-12 text-xs text-muted-foreground">Turn {row.turn_index}</span>
              <SentimentBadge sentiment={row.sentiment} />
              {row.signal && <span className="text-xs text-muted-foreground">{row.signal}</span>}
            </li>
          ))}
        </ol>
      )}

      {callLevel.length > 0 && (
        <ul className="space-y-1 border-t pt-3 text-sm">
          {callLevel.map((row) =>
            row.signal === "REPEATED_CONTACT" ? (
              <li key={row.id} className="text-muted-foreground">
                Repeated contact flagged
              </li>
            ) : (
              <li key={row.id} className="flex items-center gap-2 text-muted-foreground">
                Final sentiment: <SentimentBadge sentiment={row.sentiment} />
              </li>
            ),
          )}
        </ul>
      )}
    </div>
  );
}
