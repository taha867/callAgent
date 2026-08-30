import { Badge } from "@/components/ui/badge";
import { useJourneyRuns } from "@/hooks/qaHooks/qaQueries";
import { DEMO_JOURNEY_IDS } from "@/utils/constants";

function formatJourneyLabel(id) {
  return id
    .replace(/^DEMO_\d+_/, "")
    .split("_")
    .map((w) => w[0] + w.slice(1).toLowerCase())
    .join(" ");
}

// Latest cooperative (adversarial_scenario_id === null) run per journey, client-side —
// GET /qa/journey-runs returns every run, newest first is not guaranteed by the API
// contract, so this finds the max run_at per demo_journey_id explicitly.
function latestCooperativeRunByJourney(runs) {
  const byJourney = {};
  for (const run of runs ?? []) {
    if (run.adversarial_scenario_id !== null) continue;
    const existing = byJourney[run.demo_journey_id];
    if (!existing || new Date(run.run_at) > new Date(existing.run_at)) {
      byJourney[run.demo_journey_id] = run;
    }
  }
  return byJourney;
}

// Mobile-first per CLAUDE.md §3.7 — 1 column below sm, 3 columns at sm+. 9 small
// self-contained cards never need the overflow-x-auto treatment a wide table would.
export function JourneyStatusGrid() {
  const { data, isLoading, isError } = useJourneyRuns();

  if (isLoading) return <p className="text-muted-foreground">Loading journey status…</p>;
  if (isError) return <p className="text-destructive">Could not load journey status.</p>;

  const latest = latestCooperativeRunByJourney(data);

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      {DEMO_JOURNEY_IDS.map((id) => {
        const run = latest[id];
        return (
          <div key={id} className="rounded-lg border border-border p-3">
            <p className="text-sm font-medium">{formatJourneyLabel(id)}</p>
            <Badge variant={run ? (run.passed ? "default" : "destructive") : "secondary"}>
              {run ? (run.passed ? "Passing" : "Failing") : "Not yet run"}
            </Badge>
          </div>
        );
      })}
    </div>
  );
}
