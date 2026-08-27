import toast from "react-hot-toast";

const BASE_URL = import.meta.env.VITE_API_BASE_URL;
const DEFAULT_TIMEOUT_MS = 10_000;

// No-op until an auth/ backend exists (see phase-0-frontend-spec.md decision 1/2) —
// whichever phase adds token refresh replaces this, not fetchClient's callers.
let onUnauthorized = () => {};
export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

export async function fetchClient(path, { method = "GET", body, headers = {}, timeoutMs = DEFAULT_TIMEOUT_MS, silent = false } = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers: { "Content-Type": "application/json", ...headers },
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });

    if (response.status === 401) {
      onUnauthorized();
    }

    const data = response.status === 204 ? null : await response.json().catch(() => null);

    if (!response.ok && !silent) {
      toast.error(data?.detail ?? `Request failed (${response.status})`);
    }

    return { data, status: response.status, ok: response.ok, headers: response.headers };
  } catch (error) {
    if (!silent) {
      toast.error(error.name === "AbortError" ? "Request timed out" : "Network error");
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}
