import { useQuery } from "@tanstack/react-query";
import { getCallAttempt } from "@/services/callService";
import { callKeys } from "@/utils/queryKeys";

// POST /calls returns immediately; disposition_code stays null until the workflow's
// terminal activity writes it. Poll until it resolves, then stop. See spec §0.6.
export function useCallAttempt(callId) {
  return useQuery({
    queryKey: callKeys.detail(callId),
    queryFn: () => getCallAttempt(callId),
    refetchInterval: (query) => (query.state.data?.disposition_code ? false : 2000),
  });
}
