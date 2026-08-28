import { useState } from "react";
import { Link } from "react-router";
import { useClaim } from "@/hooks/claimHooks/claimQueries";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ActionCreateForm } from "@/components/actions/form/ActionCreateForm";

export function ClaimOverviewCard({ claimId }) {
  const { data: claim, isLoading, isError } = useClaim(claimId);
  const [showActionForm, setShowActionForm] = useState(false);

  if (isLoading) return <p>Loading…</p>;
  if (isError) return <p className="text-destructive">Could not load this claim.</p>;
  // isLoading is isPending && isFetching (TanStack Query v5) — it can be false in a
  // transient window before data is actually attached. Guard on data itself, not just the
  // derived flags, before dereferencing it.
  if (!claim) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Claim {claim.id}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <dt className="text-muted-foreground">Policy</dt>
          <dd>{claim.policy_id}</dd>
          <dt className="text-muted-foreground">Customer</dt>
          <dd>{claim.customer_id}</dd>
          <dt className="text-muted-foreground">Stage</dt>
          <dd>{claim.claim_stage}</dd>
          <dt className="text-muted-foreground">Current owner</dt>
          <dd>{claim.current_owner ?? "—"}</dd>
          <dt className="text-muted-foreground">Delay flag</dt>
          <dd>{claim.delay_flag ? "Yes" : "No"}</dd>
        </dl>

        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline">
            <Link to={`/complaints?claimId=${claim.id}`}>File a complaint on this claim</Link>
          </Button>
          <Button variant="outline" onClick={() => setShowActionForm((v) => !v)}>
            {showActionForm ? "Hide action form" : "Create an action for this claim"}
          </Button>
        </div>

        {/* Kept mounted regardless of toggle state so ActionCreateForm's idempotency-key
            ref (see useCreateAction) survives opening/closing the section. */}
        <div className={showActionForm ? "" : "hidden"}>
          <ActionCreateForm claimId={claim.id} />
        </div>
      </CardContent>
    </Card>
  );
}
