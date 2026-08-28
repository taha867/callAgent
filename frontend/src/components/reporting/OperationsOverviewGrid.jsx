import { useOperationsOverview } from "@/hooks/reportingHooks/reportingQueries";
import { StatTile } from "@/components/common/StatTile";
import { Skeleton } from "@/components/ui/skeleton";
import { formatPercent, formatMs, formatDuration } from "@/utils/metricsUtils";

// Every field OperationsOverviewRead returns (backend/src/reporting/schemas.py), rendered
// unconditionally — the honestly-zero metrics (fraud_siu_referrals etc., spec §0.10 of the
// backend spec) get a real tile showing their real 0/0.0% value, never hidden or replaced
// with a "coming soon" placeholder, which would misrepresent a real number as unavailable.
const TILES = [
  { key: "calls_scheduled", label: "Calls scheduled" },
  { key: "calls_attempted", label: "Calls attempted" },
  { key: "human_answer_rate", label: "Human answer rate", format: formatPercent },
  { key: "right_party_contact_rate", label: "Right-party contact rate", format: formatPercent },
  { key: "verification_success_rate", label: "Verification success rate", format: formatPercent },
  { key: "statuses_delivered", label: "Statuses delivered" },
  { key: "ai_contained_calls", label: "AI-contained calls" },
  { key: "actions_created", label: "Actions created" },
  { key: "complaints_created", label: "Complaints created" },
  { key: "human_escalations", label: "Human escalations" },
  { key: "callbacks_scheduled", label: "Callbacks scheduled" },
  { key: "no_answer_rate", label: "No-answer rate", format: formatPercent },
  { key: "avg_call_duration_seconds", label: "Avg call duration", format: formatDuration },
  { key: "latency_p50_ms", label: "Latency P50", format: formatMs },
  { key: "latency_p95_ms", label: "Latency P95", format: formatMs },
  { key: "latency_p99_ms", label: "Latency P99", format: formatMs },
  {
    key: "silent_call_technical_failure_rate",
    label: "Silent-call failure rate",
    format: formatPercent,
  },
  {
    key: "backend_dependency_failure_rate",
    label: "Backend dependency failure rate",
    format: formatPercent,
  },
  { key: "model_stt_tts_failure_rate", label: "Model/STT/TTS failure rate", format: formatPercent },
  { key: "dtmf_fallback_rate", label: "DTMF fallback rate", format: formatPercent },
  { key: "concurrent_call_conflicts_prevented", label: "Concurrent-call conflicts prevented" },
  { key: "dropped_call_rate", label: "Dropped-call rate", format: formatPercent },
  { key: "otp_lockouts", label: "OTP lockouts" },
  { key: "fraud_siu_referrals", label: "Fraud/SIU referrals" },
  { key: "vulnerable_customer_referrals", label: "Vulnerable-customer referrals" },
];

export function OperationsOverviewGrid({ since, until }) {
  const { data, isLoading, isError } = useOperationsOverview(since, until);

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        {TILES.map((tile) => (
          <Skeleton key={tile.key} className="h-24 w-full" />
        ))}
      </div>
    );
  }

  if (isError || !data) {
    return <p className="text-destructive">Could not load operations overview.</p>;
  }

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
      {TILES.map(({ key, label, format }) => (
        <StatTile key={key} label={label} value={format ? format(data[key]) : (data[key] ?? "—")} />
      ))}
    </div>
  );
}
