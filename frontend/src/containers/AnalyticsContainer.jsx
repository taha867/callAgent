import { useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DateRangeFilter } from "@/components/reporting/DateRangeFilter";
import { NoAnswerAnalyticsPanel } from "@/components/reporting/NoAnswerAnalyticsPanel";
import { StatusAnalyticsTable } from "@/components/reporting/StatusAnalyticsTable";
import { CustomerExperiencePanel } from "@/components/reporting/CustomerExperiencePanel";
import { EscalationAnalyticsPanel } from "@/components/reporting/EscalationAnalyticsPanel";
import { defaultDateRange } from "@/utils/metricsUtils";

// Each TabsContent's panel calls its own hook internally — same independent-per-tab-query
// discipline ClaimDetailContainer already established (Phase 1) — so one slow/failing tab
// never blocks the others. Radix Tabs.Content lazy-mounts by default (no forceMount passed
// anywhere in this repo's ui/tabs.jsx wrapper), so each panel's query only fires once that
// tab is first opened.
export default function AnalyticsContainer() {
  const [{ since, until }, setRange] = useState(defaultDateRange());

  return (
    <div className="space-y-4">
      <DateRangeFilter
        since={since}
        until={until}
        onChange={(newSince, newUntil) => setRange({ since: newSince, until: newUntil })}
      />
      <Tabs defaultValue="no-answer">
        <TabsList>
          <TabsTrigger value="no-answer">No-Answer</TabsTrigger>
          <TabsTrigger value="status">Status</TabsTrigger>
          <TabsTrigger value="experience">Customer Experience</TabsTrigger>
          <TabsTrigger value="escalations">Escalations</TabsTrigger>
        </TabsList>
        <TabsContent value="no-answer">
          <NoAnswerAnalyticsPanel since={since} until={until} />
        </TabsContent>
        <TabsContent value="status">
          <StatusAnalyticsTable since={since} until={until} />
        </TabsContent>
        <TabsContent value="experience">
          <CustomerExperiencePanel since={since} until={until} />
        </TabsContent>
        <TabsContent value="escalations">
          <EscalationAnalyticsPanel since={since} until={until} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
