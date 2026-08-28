import { useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { yupResolver } from "@hookform/resolvers/yup";
import { actionCreateSchema } from "@/validations/actionSchemas";
import { useCreateAction } from "@/hooks/actionHooks/actionMutations";
import { FormField, FormSelect } from "@/components/custom";
import { Button } from "@/components/ui/button";
import { ACTION_CODES } from "@/utils/constants";

// No read/list endpoint exists for ClaimAction — the created row is shown inline after
// submit rather than navigated to. See phase-1-frontend-spec.md §5.1.
export function ActionCreateForm({ claimId }) {
  const [created, setCreated] = useState(null);
  const {
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm({
    resolver: yupResolver(actionCreateSchema),
    defaultValues: { actionCode: ACTION_CODES[0], summary: "", sourceCallId: null },
  });
  const { mutateAsync: createAction } = useCreateAction(claimId);

  const onSubmit = async (values) => {
    try {
      const action = await createAction(values);
      setCreated(action);
    } catch {
      // fetchClient already toasted the failure.
    }
  };

  return (
    <div className="space-y-3 rounded-lg border border-border p-4">
      <form onSubmit={handleSubmit(onSubmit)} className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Controller
          name="actionCode"
          control={control}
          render={({ field }) => (
            <FormSelect
              {...field}
              label="Action code"
              options={ACTION_CODES}
              error={errors.actionCode?.message}
            />
          )}
        />
        <Controller
          name="sourceCallId"
          control={control}
          render={({ field }) => (
            <FormField
              {...field}
              value={field.value ?? ""}
              label="Source call ID (optional)"
              error={errors.sourceCallId?.message}
            />
          )}
        />
        <Controller
          name="summary"
          control={control}
          render={({ field }) => (
            <FormField
              {...field}
              multiline
              label="Summary"
              className="md:col-span-2"
              error={errors.summary?.message}
            />
          )}
        />
        <Button type="submit" disabled={isSubmitting} className="md:col-span-2">
          Create action
        </Button>
      </form>
      {created && (
        <p className="text-sm text-muted-foreground">
          Created action {created.id} — status {created.status}
        </p>
      )}
    </div>
  );
}
