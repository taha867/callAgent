import { useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { yupResolver } from "@hookform/resolvers/yup";
import { escalationCreateSchema } from "@/validations/actionSchemas";
import { useCreateEscalation } from "@/hooks/actionHooks/actionMutations";
import { FormField } from "@/components/custom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

// claimId/callId are both already known on the call-detail page (the one screen where both
// ids are available without the ops user typing either) — only `reason` is a real input.
// context_snapshot is intentionally not collected here; it's the live call's automatic
// warm-transfer context, not something hand-authored from the dashboard. See spec §5.3.
export function EscalationCreateForm({ claimId, callId }) {
  const [created, setCreated] = useState(null);
  const {
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm({
    resolver: yupResolver(escalationCreateSchema),
    defaultValues: { callId, reason: "" },
  });
  const { mutateAsync: createEscalation } = useCreateEscalation(claimId);

  const onSubmit = async (values) => {
    try {
      const escalation = await createEscalation(values);
      setCreated(escalation);
    } catch {
      // fetchClient already toasted the failure.
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Escalate this call</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <Controller
            name="reason"
            control={control}
            render={({ field }) => (
              <FormField {...field} multiline label="Reason" error={errors.reason?.message} />
            )}
          />
          <Button type="submit" disabled={isSubmitting}>
            Create escalation
          </Button>
        </form>
        {created && (
          <p className="text-sm text-muted-foreground">
            Created escalation {created.id} — status {created.status}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
