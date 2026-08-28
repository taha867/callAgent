// Phase 3 — every _rate field and every _ms field the reporting/ domain returns goes
// through one of these, never a hand-rolled .toFixed() at the component level.

export const formatPercent = (rate) => (rate == null ? "—" : `${(rate * 100).toFixed(1)}%`);

export const formatMs = (ms) => (ms == null ? "—" : `${Math.round(ms)}ms`);

export const formatDuration = (seconds) =>
  seconds == null ? "—" : `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;

// Last-7-days default for DashboardContainer/AnalyticsContainer's initial date-range state.
// Both values are already ISO strings — the same shape DateRangeFilter's corrected
// onSubmit produces (see .claude/plans/phase-3-frontend-implementation-plan.md Correction
// 2), so a container can pass either straight into services/reportingService.js's functions.
export function defaultDateRange() {
  const until = new Date();
  const since = new Date(until.getTime() - 7 * 24 * 60 * 60 * 1000);
  return { since: since.toISOString(), until: until.toISOString() };
}
