import { useQuery } from "@tanstack/react-query";
import { getComplaint } from "@/services/complaintService";
import { complaintKeys } from "@/utils/queryKeys";

export function useComplaint(complaintId) {
  return useQuery({
    queryKey: complaintKeys.detail(complaintId),
    queryFn: () => getComplaint(complaintId),
  });
}
