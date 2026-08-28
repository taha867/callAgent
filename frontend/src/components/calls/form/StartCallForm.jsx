import { useForm, Controller } from "react-hook-form";
import { yupResolver } from "@hookform/resolvers/yup";
import { useNavigate } from "react-router";
import { startCallSchema } from "@/validations/callSchemas";
import { useStartCall } from "@/hooks/callHooks/callMutations";
import { FormField, FormSelect } from "@/components/custom";
import { Button } from "@/components/ui/button";
import { CALL_ANSWER_RESULTS } from "@/utils/constants";

// simulated_answer_result exposes Phase 1's fake/text harness deliberately — it lets an ops
// user manually drive dial outcomes (NO_ANSWER/VOICEMAIL/FAILED) from the dashboard without
// real telephony. See phase-1-frontend-spec.md decision 0.7 — this allow-list is a client
// courtesy, the backend field is an unconstrained string.
export function StartCallForm() {
  const navigate = useNavigate();
  const {
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm({
    resolver: yupResolver(startCallSchema),
    defaultValues: { customerId: "", claimId: "", simulatedAnswerResult: "HUMAN_ANSWERED" },
  });
  const { mutateAsync: startCall } = useStartCall();

  const onSubmit = async (values) => {
    try {
      const { call_id } = await startCall(values);
      navigate(`/calls/${call_id}`);
    } catch {
      // fetchClient already toasted the failure — nothing further to do here.
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <Controller
        name="customerId"
        control={control}
        render={({ field }) => (
          <FormField {...field} label="Customer ID" error={errors.customerId?.message} />
        )}
      />
      <Controller
        name="claimId"
        control={control}
        render={({ field }) => (
          <FormField {...field} label="Claim ID" error={errors.claimId?.message} />
        )}
      />
      <Controller
        name="simulatedAnswerResult"
        control={control}
        render={({ field }) => (
          <FormSelect
            {...field}
            label="Simulated answer result"
            options={CALL_ANSWER_RESULTS}
            error={errors.simulatedAnswerResult?.message}
          />
        )}
      />
      <Button type="submit" disabled={isSubmitting} className="md:col-span-2">
        Start call
      </Button>
    </form>
  );
}
