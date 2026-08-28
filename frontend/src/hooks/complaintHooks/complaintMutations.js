import { useMutation } from "@tanstack/react-query";
import { createComplaint } from "@/services/complaintService";

export function useCreateComplaint() {
  return useMutation({
    mutationFn: (values) => createComplaint(values),
  });
}
