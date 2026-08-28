import { object, string } from "yup";
import { CALL_ANSWER_RESULTS } from "@/utils/constants";

export const startCallSchema = object({
  customerId: string().required("Customer ID is required"),
  claimId: string().required("Claim ID is required"),
  simulatedAnswerResult: string().oneOf(CALL_ANSWER_RESULTS).required(),
});
