import { useForm, Controller } from "react-hook-form";
import { yupResolver } from "@hookform/resolvers/yup";
import { defectLogEntryCreateSchema } from "@/validations/qaSchemas";
import { useCreateDefect } from "@/hooks/qaHooks/qaMutations";
import { FormField, FormSelect } from "@/components/custom";
import { Button } from "@/components/ui/button";
import { DEMO_JOURNEY_IDS } from "@/utils/constants";

// Logging a NEW defect (first occurrence) — a deliberately separate, larger action from
// DefectOccurrenceForm's "I've seen this shape again" (phase-4-frontend-spec.md §0.4).
export function DefectLogEntryForm({ onSuccess }) {
  const {
    control,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm({
    resolver: yupResolver(defectLogEntryCreateSchema),
    defaultValues: {
      title: "",
      defectShapeKey: "",
      demoJourneyId: null,
      adversarialScenarioId: null,
      language: "EN",
      severity: "MEDIUM",
      notes: null,
    },
  });
  const { mutateAsync: createDefect } = useCreateDefect();

  const onSubmit = async (values) => {
    try {
      await createDefect(values);
      reset();
      onSuccess?.();
    } catch {
      // fetchClient already toasted the failure.
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <Controller
        name="title"
        control={control}
        render={({ field }) => <FormField {...field} label="Title" error={errors.title?.message} />}
      />
      <Controller
        name="defectShapeKey"
        control={control}
        render={({ field }) => (
          <FormField {...field} label="Defect shape key" error={errors.defectShapeKey?.message} />
        )}
      />
      <Controller
        name="demoJourneyId"
        control={control}
        render={({ field }) => (
          <FormSelect
            {...field}
            value={field.value ?? ""}
            label="Demo journey (optional)"
            options={DEMO_JOURNEY_IDS}
            error={errors.demoJourneyId?.message}
          />
        )}
      />
      <Controller
        name="severity"
        control={control}
        render={({ field }) => (
          <FormSelect
            {...field}
            label="Severity"
            options={["LOW", "MEDIUM", "HIGH"]}
            error={errors.severity?.message}
          />
        )}
      />
      <Controller
        name="language"
        control={control}
        render={({ field }) => (
          <FormSelect
            {...field}
            label="Language"
            options={["EN", "AR", "CODE_SWITCH"]}
            error={errors.language?.message}
          />
        )}
      />
      <Controller
        name="notes"
        control={control}
        render={({ field }) => (
          <FormField
            {...field}
            value={field.value ?? ""}
            multiline
            label="Notes (optional)"
            className="md:col-span-2"
            error={errors.notes?.message}
          />
        )}
      />
      <Button type="submit" disabled={isSubmitting} className="md:col-span-2">
        Log defect
      </Button>
    </form>
  );
}
