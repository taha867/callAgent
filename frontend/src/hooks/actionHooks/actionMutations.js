import { useMutation } from "@tanstack/react-query";
import { useRef } from "react";
import { createAction, createEscalation } from "@/services/actionService";
import { newIdempotencyKey } from "@/utils/idempotency";

// The idempotency key is generated once per mount of the owning form, not once per click —
// a retry or a double-submit reuses the same key so the backend's idempotency record returns
// the original row instead of creating a duplicate. See phase-1-frontend-spec.md decision 0.5.
export function useCreateAction(claimId) {
  const idempotencyKey = useRef(newIdempotencyKey());
  return useMutation({
    mutationFn: (values) => createAction(claimId, values, idempotencyKey.current),
  });
}

export function useCreateEscalation(claimId) {
  const idempotencyKey = useRef(newIdempotencyKey());
  return useMutation({
    mutationFn: (values) => createEscalation(claimId, values, idempotencyKey.current),
  });
}
