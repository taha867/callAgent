import { useParams } from "react-router";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useCallAttempt } from "@/hooks/callHooks/callQueries";
import { CallAttemptSummary } from "@/components/calls/CallAttemptSummary";
import { CallTranscriptViewer } from "@/components/calls/CallTranscriptViewer";
import { CallSummaryPanel } from "@/components/calls/CallSummaryPanel";
import { CustomerIntentList } from "@/components/calls/CustomerIntentList";
import { SentimentTimeline } from "@/components/calls/SentimentTimeline";
import { EscalationCreateForm } from "@/components/actions/form/EscalationCreateForm";

// The one screen where both claim_id and call_id are simultaneously available without the
// ops user typing either — this is why escalation creation lives here rather than on the
// claim detail page. See phase-1-frontend-spec.md §4.4. EscalationCreateForm stays a
// sibling AFTER the Tabs, never nested inside a TabsContent — it's an action available
// regardless of which tab is open, not tab-scoped content.
export default function CallDetailContainer() {
  const { callId } = useParams();
  const { data: attempt, isLoading, isError } = useCallAttempt(callId);

  if (isLoading) return <p>Loading…</p>;
  if (isError) return <p className="text-destructive">Could not load this call.</p>;
  if (!attempt) return null;

  return (
    <div className="space-y-6">
      <Tabs defaultValue="summary">
        <TabsList>
          <TabsTrigger value="summary">Summary</TabsTrigger>
          <TabsTrigger value="transcript">Transcript</TabsTrigger>
          <TabsTrigger value="intents">Intents</TabsTrigger>
          <TabsTrigger value="sentiment">Sentiment</TabsTrigger>
        </TabsList>
        <TabsContent value="summary" className="space-y-4">
          <CallAttemptSummary attempt={attempt} />
          <CallSummaryPanel callId={callId} />
        </TabsContent>
        <TabsContent value="transcript">
          <CallTranscriptViewer callId={callId} />
        </TabsContent>
        <TabsContent value="intents">
          <CustomerIntentList callId={callId} />
        </TabsContent>
        <TabsContent value="sentiment">
          <SentimentTimeline callId={callId} />
        </TabsContent>
      </Tabs>
      <EscalationCreateForm claimId={attempt.claim_id} callId={attempt.id} />
    </div>
  );
}
