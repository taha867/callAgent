import { object, string } from "yup";
import { ACTION_CODES } from "@/utils/constants";

// ActionCreate.action_code is a real Pydantic enum server-side (backend/src/actions/schemas.py)
// — this .oneOf(...) is a genuine mirror, not a courtesy over a validation gap.
export const actionCreateSchema = object({
  actionCode: string().oneOf(ACTION_CODES).required("Action code is required"),
  summary: string().required("Summary is required").max(1000),
  sourceCallId: string().nullable().default(null),
});

export const escalationCreateSchema = object({
  callId: string().required(),
  reason: string().required("Reason is required").max(1000),
});
