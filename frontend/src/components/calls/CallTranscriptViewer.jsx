import { useCallTranscript } from "@/hooks/callHooks/callQueries";
import { SpeakerBadge } from "@/components/common/SpeakerBadge";
import { Skeleton } from "@/components/ui/skeleton";

// redacted_text is ALWAYS the output of privacy/service.py::redact() (backend/src/calls/
// activities.py::persist_transcript_turn) — never raw STT/TTS text. Never pass this text
// (or CallSummaryPanel's summary_text) to console.log, an analytics SDK, or an error
// reporter — it's still customer conversation content, redacted or not. See
// .claude/specs/phase-3-frontend-spec.md §0.7.
export function CallTranscriptViewer({ callId }) {
  const { data, isLoading, isError } = useCallTranscript(callId);

  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
      </div>
    );
  }
  if (isError) return <p className="text-destructive">Could not load the transcript.</p>;
  if (!data || data.length === 0) {
    return <p className="text-muted-foreground">No transcript recorded for this call.</p>;
  }

  return (
    <ol className="space-y-3">
      {data.map((turn) => (
        <li key={turn.turn_index} className="flex items-start gap-3">
          <SpeakerBadge speaker={turn.speaker} />
          <p className="flex-1 text-sm">{turn.redacted_text}</p>
        </li>
      ))}
    </ol>
  );
}
