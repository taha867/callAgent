import { useClaimDocuments } from "@/hooks/claimHooks/claimQueries";
import { Badge } from "@/components/ui/badge";

export function ClaimDocumentList({ claimId }) {
  const { data: documents, isLoading, isError } = useClaimDocuments(claimId);

  if (isLoading) return <p>Loading…</p>;
  if (isError) return <p className="text-destructive">Could not load documents.</p>;
  if (!documents) return null;
  if (documents.length === 0) return <p className="text-muted-foreground">No documents on file.</p>;

  return (
    <ul className="space-y-2">
      {documents.map((doc) => (
        <li key={doc.id} className="flex items-center justify-between gap-2 border-b border-border pb-2">
          <span>{doc.document_type}</span>
          <Badge variant={doc.status === "RECEIVED" ? "default" : "secondary"}>{doc.status}</Badge>
        </li>
      ))}
    </ul>
  );
}
