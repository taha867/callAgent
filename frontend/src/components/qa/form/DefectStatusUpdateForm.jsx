import { useForm, Controller } from "react-hook-form";
import { yupResolver } from "@hookform/resolvers/yup";
import { defectStatusUpdateSchema } from "@/validations/qaSchemas";
import { useUpdateDefectStatus } from "@/hooks/qaHooks/qaMutations";
import { FormField, FormSelect } from "@/components/custom";
import { Button } from "@/components/ui/button";
import { DEFECT_STATUSES, COMPILED_ARTIFACT_TYPES } from "@/utils/constants";

export function DefectStatusUpdateForm({ entry, onSuccess }) {
  const {
    control,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm({
    resolver: yupResolver(defectStatusUpdateSchema),
    defaultValues: {
      status: entry.status,
      compiledArtifactType: entry.compiled_artifact_type ?? null,
      compiledArtifactRef: entry.compiled_artifact_ref ?? null,
      notes: null,
    },
  });
  const { mutateAsync: updateStatus } = useUpdateDefectStatus();
  const wantsCompiled = watch("status") === "COMPILED";

  const onSubmit = async (values) => {
    try {
      await updateStatus({ entryId: entry.id, ...values });
      onSuccess?.();
    } catch {
      // fetchClient already toasted the failure.
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <Controller
        name="status"
        control={control}
        render={({ field }) => (
          <FormSelect {...field} label="Status" options={DEFECT_STATUSES} error={errors.status?.message} />
        )}
      />
      {wantsCompiled && (
        <>
          <Controller
            name="compiledArtifactType"
            control={control}
            render={({ field }) => (
              <FormSelect
                {...field}
                value={field.value ?? ""}
                label="Artifact type"
                options={COMPILED_ARTIFACT_TYPES}
                error={errors.compiledArtifactType?.message}
              />
            )}
          />
          <Controller
            name="compiledArtifactRef"
            control={control}
            render={({ field }) => (
              <FormField
                {...field}
                value={field.value ?? ""}
                label="Artifact reference"
                placeholder="tests/scripted_conversations/adversarial/test_x.py::test_y"
                className="md:col-span-2"
                error={errors.compiledArtifactRef?.message}
              />
            )}
          />
        </>
      )}
      <Button type="submit" disabled={isSubmitting} className="md:col-span-2">
        Save
      </Button>
    </form>
  );
}
