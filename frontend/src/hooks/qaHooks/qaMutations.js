import { useMutation, useQueryClient } from "@tanstack/react-query";
import * as qaService from "@/services/qaService";
import { qaKeys } from "@/utils/queryKeys";

// First real invalidate-on-success example in this codebase (complaintMutations.js's
// useCreateComplaint has none — it just navigates away instead). qa/'s own list + summary
// genuinely must go stale after any create/patch/occurrence, so this is a real gap being
// filled, not a stylistic choice.
function useInvalidateQaLists() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: qaKeys.all });
  };
}

export function useCreateDefect() {
  const invalidate = useInvalidateQaLists();
  return useMutation({
    mutationFn: qaService.createDefect,
    onSuccess: invalidate,
  });
}

export function useRecordOccurrence() {
  const invalidate = useInvalidateQaLists();
  return useMutation({
    mutationFn: qaService.recordOccurrence,
    onSuccess: invalidate,
  });
}

export function useUpdateDefectStatus() {
  const invalidate = useInvalidateQaLists();
  return useMutation({
    mutationFn: qaService.updateDefectStatus,
    onSuccess: invalidate,
  });
}
