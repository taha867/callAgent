import { useMutation } from "@tanstack/react-query";
import { startCall } from "@/services/callService";

export function useStartCall() {
  return useMutation({
    mutationFn: (values) => startCall(values),
  });
}
