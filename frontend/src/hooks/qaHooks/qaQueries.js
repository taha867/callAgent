import { useQuery } from "@tanstack/react-query";
import * as qaService from "@/services/qaService";
import { qaKeys } from "@/utils/queryKeys";

export function useDefectList({ page = 1, pageSize = 20, status, demoJourneyId } = {}) {
  const params = { page, pageSize, status: status ?? null, demoJourneyId: demoJourneyId ?? null };
  return useQuery({
    queryKey: qaKeys.defectList(params),
    queryFn: () => qaService.listDefects(params),
  });
}

export function useDefect(entryId) {
  return useQuery({
    queryKey: qaKeys.defectDetail(entryId),
    queryFn: () => qaService.getDefect(entryId),
    enabled: Boolean(entryId),
  });
}

export function useJourneyRuns(demoJourneyId) {
  return useQuery({
    queryKey: qaKeys.journeyRuns(demoJourneyId),
    queryFn: () => qaService.listJourneyRuns(demoJourneyId),
  });
}

export function useGovernanceSummary() {
  return useQuery({
    queryKey: qaKeys.governanceSummary(),
    queryFn: qaService.getGovernanceSummary,
  });
}
