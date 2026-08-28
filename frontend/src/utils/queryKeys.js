export const claimKeys = {
  all: ["claims"],
  detail: (id) => [...claimKeys.all, id],
  status: (id, level) => [...claimKeys.detail(id), "status", level],
  timeline: (id) => [...claimKeys.detail(id), "timeline"],
  documents: (id) => [...claimKeys.detail(id), "documents"],
  garage: (id) => [...claimKeys.detail(id), "garage"],
};

export const callKeys = {
  all: ["calls"],
  detail: (id) => [...callKeys.all, id],
  transcript: (id) => [...callKeys.detail(id), "transcript"],
  summary: (id) => [...callKeys.detail(id), "summary"],
  intents: (id) => [...callKeys.detail(id), "intents"],
  sentiment: (id) => [...callKeys.detail(id), "sentiment"],
};

export const complaintKeys = {
  all: ["complaints"],
  detail: (id) => [...complaintKeys.all, id],
};

// since/until are part of every key deliberately — changing the date range must be a cache
// miss, not a stale re-render of the previous range's numbers.
export const reportingKeys = {
  all: ["reporting"],
  operationsOverview: (since, until) => [...reportingKeys.all, "operations-overview", since, until],
  outcomeFunnel: (since, until) => [...reportingKeys.all, "outcome-funnel", since, until],
  noAnswerAnalytics: (since, until) => [...reportingKeys.all, "no-answer-analytics", since, until],
  statusAnalytics: (since, until) => [...reportingKeys.all, "status-analytics", since, until],
  customerExperience: (since, until) => [...reportingKeys.all, "customer-experience", since, until],
  escalationAnalytics: (since, until) => [...reportingKeys.all, "escalation-analytics", since, until],
};
