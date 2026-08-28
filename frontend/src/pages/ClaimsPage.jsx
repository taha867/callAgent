import { IdLookupForm } from "@/components/common/IdLookupForm";

export default function ClaimsPage() {
  return (
    <main className="mx-auto max-w-xl space-y-4 p-4">
      <h1 className="text-lg font-semibold">Claims</h1>
      <IdLookupForm label="Claim ID" placeholder="e.g. CLAIM-DEMO-001" basePath="/claims" />
    </main>
  );
}
