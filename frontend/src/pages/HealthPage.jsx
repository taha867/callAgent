import { useQuery } from "@tanstack/react-query";
import { getHealth } from "@/services/healthService";

export default function HealthPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    refetchInterval: 10_000,
  });

  const status = isLoading ? "checking…" : data?.ok ? "backend: ok" : "backend: unreachable";

  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <p className="text-sm text-neutral-600">{status}</p>
    </main>
  );
}
