import { useParams } from "react-router";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ClaimOverviewCard } from "@/components/claims/ClaimOverviewCard";
import { ClaimStatusPanel } from "@/components/claims/ClaimStatusPanel";
import { ClaimStatusTimeline } from "@/components/claims/ClaimStatusTimeline";
import { ClaimDocumentList } from "@/components/claims/ClaimDocumentList";
import { RepairGarageCard } from "@/components/claims/RepairGarageCard";

// Five independent queries, one per tab — a missing garage (a valid null response) must not
// block the other four tabs from rendering. See phase-1-frontend-spec.md §3.4.
export default function ClaimDetailContainer() {
  const { claimId } = useParams();

  return (
    <Tabs defaultValue="overview">
      <TabsList>
        <TabsTrigger value="overview">Overview</TabsTrigger>
        <TabsTrigger value="status">Status</TabsTrigger>
        <TabsTrigger value="timeline">Timeline</TabsTrigger>
        <TabsTrigger value="documents">Documents</TabsTrigger>
        <TabsTrigger value="garage">Garage</TabsTrigger>
      </TabsList>
      <TabsContent value="overview">
        <ClaimOverviewCard claimId={claimId} />
      </TabsContent>
      <TabsContent value="status">
        <ClaimStatusPanel claimId={claimId} />
      </TabsContent>
      <TabsContent value="timeline">
        <ClaimStatusTimeline claimId={claimId} />
      </TabsContent>
      <TabsContent value="documents">
        <ClaimDocumentList claimId={claimId} />
      </TabsContent>
      <TabsContent value="garage">
        <RepairGarageCard claimId={claimId} />
      </TabsContent>
    </Tabs>
  );
}
