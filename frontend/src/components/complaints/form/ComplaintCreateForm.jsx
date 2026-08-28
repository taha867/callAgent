import { useForm, Controller } from "react-hook-form";
import { yupResolver } from "@hookform/resolvers/yup";
import { useNavigate, useSearchParams } from "react-router";
import { complaintCreateSchema } from "@/validations/complaintSchemas";
import { useCreateComplaint } from "@/hooks/complaintHooks/complaintMutations";
import { FormField, FormSelect } from "@/components/custom";
import { Button } from "@/components/ui/button";
import { COMPLAINT_SEVERITIES, COMPLAINT_CONTACT_METHODS } from "@/utils/constants";

// claimId is prefilled from ?claimId=, set by ClaimOverviewCard's "File a complaint" quick
// action — sourceCallId is always a manual field since there's no call picker. See
// phase-1-frontend-spec.md §6.2.
export function ComplaintCreateForm() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const {
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm({
    resolver: yupResolver(complaintCreateSchema),
    defaultValues: {
      claimId: searchParams.get("claimId") ?? "",
      sourceCallId: "",
      complaintCategory: "",
      customerStatementSummary: "",
      customerExpectedResolution: null,
      severity: COMPLAINT_SEVERITIES[0],
      preferredContactMethod: COMPLAINT_CONTACT_METHODS[0],
    },
  });
  const { mutateAsync: createComplaint } = useCreateComplaint();

  const onSubmit = async (values) => {
    try {
      const complaint = await createComplaint(values);
      navigate(`/complaints/${complaint.id}`);
    } catch {
      // fetchClient already toasted the failure.
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <Controller
        name="claimId"
        control={control}
        render={({ field }) => (
          <FormField {...field} label="Claim ID" error={errors.claimId?.message} />
        )}
      />
      <Controller
        name="sourceCallId"
        control={control}
        render={({ field }) => (
          <FormField {...field} label="Source call ID" error={errors.sourceCallId?.message} />
        )}
      />
      <Controller
        name="complaintCategory"
        control={control}
        render={({ field }) => (
          <FormField {...field} label="Category" error={errors.complaintCategory?.message} />
        )}
      />
      <Controller
        name="severity"
        control={control}
        render={({ field }) => (
          <FormSelect
            {...field}
            label="Severity"
            options={COMPLAINT_SEVERITIES}
            error={errors.severity?.message}
          />
        )}
      />
      <Controller
        name="preferredContactMethod"
        control={control}
        render={({ field }) => (
          <FormSelect
            {...field}
            label="Preferred contact method"
            options={COMPLAINT_CONTACT_METHODS}
            error={errors.preferredContactMethod?.message}
          />
        )}
      />
      <Controller
        name="customerStatementSummary"
        control={control}
        render={({ field }) => (
          <FormField
            {...field}
            multiline
            label="Customer statement summary"
            className="md:col-span-2"
            error={errors.customerStatementSummary?.message}
          />
        )}
      />
      <Controller
        name="customerExpectedResolution"
        control={control}
        render={({ field }) => (
          <FormField
            {...field}
            value={field.value ?? ""}
            multiline
            label="Customer expected resolution (optional)"
            className="md:col-span-2"
            error={errors.customerExpectedResolution?.message}
          />
        )}
      />
      <Button type="submit" disabled={isSubmitting} className="md:col-span-2">
        File complaint
      </Button>
    </form>
  );
}
