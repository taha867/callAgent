import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "react-hot-toast";
import App from "@/App";
import "@/index.css";

// retry: false — TanStack Query's default retry scheduling can strand a failed query in
// fetchStatus "paused" indefinitely instead of ever reaching status "error" (observed and
// reproduced against this app's own endpoints: isError stayed false and every container's
// error branch never rendered, even minutes after a 404). networkMode: "always" is set too,
// since the same pausing is networkMode's documented mechanism for offline detection, and
// this app has no offline-first requirements. Every container in this app is written
// assuming a failed query reaches isError promptly — that assumption must hold.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: { networkMode: "always", retry: false },
    mutations: { networkMode: "always", retry: false },
  },
});

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
        <Toaster />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
