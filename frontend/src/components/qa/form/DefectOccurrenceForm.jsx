import { useForm, Controller } from "react-hook-form";
import { yupResolver } from "@hookform/resolvers/yup";
import { defectOccurrenceCreateSchema } from "@/validations/qaSchemas";
import { useRecordOccurrence } from "@/hooks/qaHooks/qaMutations";
import { FormField } from "@/components/custom";
import { Button } from "@/components/ui/button";

// Recording a REPEAT sighting of an existing shape key — small and deliberately distinct
// from DefectLogEntryForm (phase-4-frontend-spec.md §0.4): the whole point of the two-strike
// rule is that a human is asked "have I seen this shape before?" as a real decision each
// time, not defaulted into "create new."
export function DefectOccurrenceForm({ onSuccess }) {
  const {
    control,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm({
    resolver: yupResolver(defectOccurrenceCreateSchema),
    defaultValues: { shapeKey: "", demoJourneyId: null, adversarialScenarioId: null, notes: null },
  });
  const { mutateAsync: recordOccurrence } = useRecordOccurrence();

  const onSubmit = async (values) => {
    try {
      await recordOccurrence(values);
      reset();
      onSuccess?.();
    } catch {
      // fetchClient already toasted the failure.
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4 md:flex-row md:items-end">
      <Controller
        name="shapeKey"
        control={control}
        render={({ field }) => (
          <FormField {...field} label="Existing shape key" error={errors.shapeKey?.message} />
        )}
      />
      <Controller
        name="notes"
        control={control}
        render={({ field }) => (
          <FormField
            {...field}
            value={field.value ?? ""}
            label="Note (optional)"
            className="md:flex-1"
            error={errors.notes?.message}
          />
        )}
      />
      <Button type="submit" disabled={isSubmitting}>
        Record occurrence
      </Button>
    </form>
  );
}
