// Formats a ComplaintRead due-at timestamp (acknowledgment_due_at / resolution_due_at) as a
// short countdown string. No ComplaintSlaEvent (AT_RISK/BREACHED) history is readable from
// the dashboard yet (no endpoint exists) — this is the only SLA signal available in Phase 1.
export function formatDueIn(dueAtIso) {
  if (!dueAtIso) return "—";

  const diffMs = new Date(dueAtIso).getTime() - Date.now();
  const overdue = diffMs < 0;
  const diffHours = Math.round(Math.abs(diffMs) / (60 * 60 * 1000));

  const unit = diffHours < 1 ? "less than 1h" : `${diffHours}h`;
  return overdue ? `overdue by ${unit}` : `due in ${unit}`;
}
