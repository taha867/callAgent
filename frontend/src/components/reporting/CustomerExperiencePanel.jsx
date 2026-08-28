import { StatTile } from "@/components/common/StatTile";
import { SentimentBadge } from "@/components/common/SentimentBadge";
import { useCustomerExperience } from "@/hooks/reportingHooks/reportingQueries";
import { formatPercent } from "@/utils/metricsUtils";

// initial_sentiment_breakdown/final_sentiment_breakdown are { [sentiment]: count } dicts —
// an absent key means zero, never assume all of POSITIVE/NEUTRAL/NEGATIVE are present.
function SentimentBreakdown({ title, breakdown }) {
  const entries = Object.entries(breakdown);
  return (
    <div>
      <h3 className="mb-2 text-sm font-medium text-muted-foreground">{title}</h3>
      {entries.length === 0 ? (
        <p className="text-muted-foreground">No data for this range.</p>
      ) : (
        <div className="flex flex-wrap gap-3">
          {entries.map(([sentiment, count]) => (
            <div key={sentiment} className="flex items-center gap-2">
              <SentimentBadge sentiment={sentiment} />
              <span className="text-sm">{count}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function CustomerExperiencePanel({ since, until }) {
  const { data, isLoading, isError } = useCustomerExperience(since, until);

  if (isLoading) return <p className="text-muted-foreground">Loading customer experience…</p>;
  if (isError || !data) return <p className="text-destructive">Could not load customer experience.</p>;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatTile label="Dissatisfaction rate" value={formatPercent(data.dissatisfaction_rate)} />
        <StatTile label="Complaint rate" value={formatPercent(data.complaint_rate)} />
        <StatTile label="Repeated-contact customers" value={data.repeated_contact_customers} />
        <StatTile label="Calls requiring humans" value={data.calls_requiring_humans} />
      </div>
      <SentimentBreakdown title="Initial sentiment" breakdown={data.initial_sentiment_breakdown} />
      <SentimentBreakdown title="Final sentiment" breakdown={data.final_sentiment_breakdown} />
    </div>
  );
}
