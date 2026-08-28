import { useQuery } from "@tanstack/react-query";
import * as reportingService from "@/services/reportingService";
import { reportingKeys } from "@/utils/queryKeys";

// enabled: Boolean(since && until) guards the one render frame before a container's
// date-range state is set — since/until are required on every reporting/ endpoint (a
// missing one 422s), so there is nothing valid to fetch before both exist.

export function useOperationsOverview(since, until) {
  return useQuery({
    queryKey: reportingKeys.operationsOverview(since, until),
    queryFn: () => reportingService.getOperationsOverview(since, until),
    enabled: Boolean(since && until),
  });
}

export function useOutcomeFunnel(since, until) {
  return useQuery({
    queryKey: reportingKeys.outcomeFunnel(since, until),
    queryFn: () => reportingService.getOutcomeFunnel(since, until),
    enabled: Boolean(since && until),
  });
}

export function useNoAnswerAnalytics(since, until) {
  return useQuery({
    queryKey: reportingKeys.noAnswerAnalytics(since, until),
    queryFn: () => reportingService.getNoAnswerAnalytics(since, until),
    enabled: Boolean(since && until),
  });
}

export function useStatusAnalytics(since, until) {
  return useQuery({
    queryKey: reportingKeys.statusAnalytics(since, until),
    queryFn: () => reportingService.getStatusAnalytics(since, until),
    enabled: Boolean(since && until),
  });
}

export function useCustomerExperience(since, until) {
  return useQuery({
    queryKey: reportingKeys.customerExperience(since, until),
    queryFn: () => reportingService.getCustomerExperience(since, until),
    enabled: Boolean(since && until),
  });
}

export function useEscalationAnalytics(since, until) {
  return useQuery({
    queryKey: reportingKeys.escalationAnalytics(since, until),
    queryFn: () => reportingService.getEscalationAnalytics(since, until),
    enabled: Boolean(since && until),
  });
}
