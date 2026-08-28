import { useParams } from "react-router";
import { useComplaint } from "@/hooks/complaintHooks/complaintQueries";
import { ComplaintDetail } from "@/components/complaints/ComplaintDetail";

export default function ComplaintDetailContainer() {
  const { complaintId } = useParams();
  const { data: complaint, isLoading, isError } = useComplaint(complaintId);

  if (isLoading) return <p>Loading…</p>;
  if (isError) return <p className="text-destructive">Could not load this complaint.</p>;
  if (!complaint) return null;

  return <ComplaintDetail complaint={complaint} />;
}
