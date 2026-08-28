import { IdLookupForm } from "@/components/common/IdLookupForm";
import { StartCallForm } from "@/components/calls/form/StartCallForm";

export default function CallsPage() {
  return (
    <main className="mx-auto max-w-xl space-y-8 p-4">
      <section className="space-y-4">
        <h1 className="text-lg font-semibold">Start a call</h1>
        <StartCallForm />
      </section>
      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Look up a call</h2>
        <IdLookupForm label="Call ID" placeholder="e.g. CALL-DEMO-001" basePath="/calls" />
      </section>
    </main>
  );
}
