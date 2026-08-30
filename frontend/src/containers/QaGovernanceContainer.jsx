import { useState } from "react";
import { GovernanceSummaryHeader } from "@/components/qa/GovernanceSummaryHeader";
import { JourneyStatusGrid } from "@/components/qa/JourneyStatusGrid";
import { DefectLogTable } from "@/components/qa/DefectLogTable";
import { DefectDetailPanel } from "@/components/qa/DefectDetailPanel";
import { DefectLogEntryForm } from "@/components/qa/form/DefectLogEntryForm";
import { DefectOccurrenceForm } from "@/components/qa/form/DefectOccurrenceForm";

export default function QaGovernanceContainer() {
  const [page, setPage] = useState(1);
  const [selectedEntryId, setSelectedEntryId] = useState(null);

  return (
    <div className="space-y-6">
      <GovernanceSummaryHeader />
      <JourneyStatusGrid />
      <DefectLogEntryForm onSuccess={() => setPage(1)} />
      <DefectOccurrenceForm onSuccess={() => setPage(1)} />
      <DefectLogTable page={page} onPageChange={setPage} onSelect={setSelectedEntryId} />
      {selectedEntryId && (
        <DefectDetailPanel entryId={selectedEntryId} onClose={() => setSelectedEntryId(null)} />
      )}
    </div>
  );
}
