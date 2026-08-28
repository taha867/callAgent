import DashboardContainer from "@/containers/DashboardContainer";

export default function DashboardPage() {
  return (
    <main className="mx-auto max-w-6xl space-y-4 p-4">
      <h1 className="text-lg font-semibold">Operations Dashboard</h1>
      <DashboardContainer />
    </main>
  );
}
