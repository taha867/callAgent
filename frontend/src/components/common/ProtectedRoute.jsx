export function ProtectedRoute({ children }) {
  // Pass-through until real auth exists — do not wire a redirect against a backend that
  // isn't there yet (see phase-0-frontend-spec.md decision 1).
  return children;
}
