import { fetchClient } from "@/middleware/fetchClient";

export async function getHealth() {
  return fetchClient("/health", { silent: true });
}
