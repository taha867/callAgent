import { fetchClient } from "@/middleware/fetchClient";
import { unwrapResponse } from "@/utils/unwrapResponse";

// since/until are ISO datetime strings (containing `:`/`+`) — encodeURIComponent is
// required here, unlike e.g. claimService.js's plain enum query params which never need
// escaping.
function rangeQuery(since, until) {
  return `since=${encodeURIComponent(since)}&until=${encodeURIComponent(until)}`;
}

export const getOperationsOverview = (since, until) =>
  unwrapResponse(fetchClient(`/reporting/operations-overview?${rangeQuery(since, until)}`));

export const getOutcomeFunnel = (since, until) =>
  unwrapResponse(fetchClient(`/reporting/outcome-funnel?${rangeQuery(since, until)}`));

export const getNoAnswerAnalytics = (since, until) =>
  unwrapResponse(fetchClient(`/reporting/no-answer-analytics?${rangeQuery(since, until)}`));

export const getStatusAnalytics = (since, until) =>
  unwrapResponse(fetchClient(`/reporting/status-analytics?${rangeQuery(since, until)}`));

export const getCustomerExperience = (since, until) =>
  unwrapResponse(fetchClient(`/reporting/customer-experience?${rangeQuery(since, until)}`));

export const getEscalationAnalytics = (since, until) =>
  unwrapResponse(fetchClient(`/reporting/escalation-analytics?${rangeQuery(since, until)}`));
