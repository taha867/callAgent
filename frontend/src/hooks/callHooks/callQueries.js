import { useQuery } from "@tanstack/react-query";
import * as callService from "@/services/callService";
import { callKeys } from "@/utils/queryKeys";

// POST /calls returns immediately; disposition_code stays null until the workflow's
// terminal activity writes it. Poll until it resolves, then stop. See spec §0.6.
export function useCallAttempt(callId) {
  return useQuery({
    queryKey: callKeys.detail(callId),
    queryFn: () => callService.getCallAttempt(callId),
    refetchInterval: (query) => (query.state.data?.disposition_code ? false : 2000),
  });
}

export function useCallTranscript(callId) {
  return useQuery({
    queryKey: callKeys.transcript(callId),
    queryFn: () => callService.getCallTranscript(callId),
  });
}

// The best-effort post-call summary (calls/workflows.py::_finalize) may not have landed
// yet if this tab is opened moments after the call ended — poll briefly, capped, per
// .claude/plans/phase-3-frontend-implementation-plan.md Correction 4. A call whose
// disposition means no conversation ever happened (WRONG_PARTY, NO_ANSWER, ...) will never
// get a summary; without the dataUpdateCount cap this would poll every 3s forever, since
// the Summary tab is CallDetailContainer's default (i.e. always-mounted) tab.
export function useCallSummary(callId) {
  return useQuery({
    queryKey: callKeys.summary(callId),
    queryFn: () => callService.getCallSummary(callId),
    refetchInterval: (query) =>
      query.state.data || query.state.dataUpdateCount >= 5 ? false : 3000,
  });
}

export function useCallIntents(callId) {
  return useQuery({
    queryKey: callKeys.intents(callId),
    queryFn: () => callService.getCallIntents(callId),
  });
}

export function useCallSentiment(callId) {
  return useQuery({
    queryKey: callKeys.sentiment(callId),
    queryFn: () => callService.getCallSentiment(callId),
  });
}
