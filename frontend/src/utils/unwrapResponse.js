// fetchClient resolves { data, status, ok, headers } (see middleware/fetchClient.js) —
// every service function unwraps through this so hooks/components can work with the plain
// response body, and so a non-2xx response actually throws (fetchClient itself only throws
// on network/timeout, never on a non-2xx HTTP status — it just toasts and returns ok:false).
// A thrown error is what lets TanStack Query's isError ever become true.
export async function unwrapResponse(promise) {
  const { data, ok } = await promise;
  if (!ok) {
    throw new Error(data?.detail ?? "Request failed");
  }
  return data;
}
