import { useClaimGarage } from "@/hooks/claimHooks/claimQueries";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function RepairGarageCard({ claimId }) {
  const { data: garage, isLoading, isError } = useClaimGarage(claimId);

  if (isLoading) return <p>Loading…</p>;
  if (isError) return <p className="text-destructive">Could not load garage details.</p>;
  // A null garage is a valid response — MotorClaim.garage_id is nullable, not every claim
  // has one assigned yet.
  if (!garage) return <p className="text-muted-foreground">No garage assigned to this claim yet.</p>;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{garage.name}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1 text-sm">
        {garage.phone_e164 && <p>{garage.phone_e164}</p>}
        {garage.address && <p className="text-muted-foreground">{garage.address}</p>}
      </CardContent>
    </Card>
  );
}
