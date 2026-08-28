import { IdLookupForm } from "@/components/common/IdLookupForm";
import { ComplaintCreateForm } from "@/components/complaints/form/ComplaintCreateForm";

export default function ComplaintsPage() {
  return (
    <main className="mx-auto max-w-xl space-y-8 p-4">
      <section className="space-y-4">
        <h1 className="text-lg font-semibold">File a complaint</h1>
        <ComplaintCreateForm />
      </section>
      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Look up a complaint</h2>
        <IdLookupForm
          label="Complaint ID"
          placeholder="e.g. COMPLAINT-DEMO-001"
          basePath="/complaints"
        />
      </section>
    </main>
  );
}
