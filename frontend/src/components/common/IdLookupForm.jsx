import { useState } from "react";
import { useNavigate } from "react-router";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

// Shared "look up by id" pattern behind ClaimsPage/CallsPage/ComplaintsPage — Phase 1 has no
// list endpoint for any of these domains, so the only way into a detail view is a known id,
// either pasted (seed data) or handed over after a create action. See
// phase-1-frontend-spec.md §0.3/§7.1.
export function IdLookupForm({ label, placeholder, basePath }) {
  const [id, setId] = useState("");
  const navigate = useNavigate();

  const onSubmit = (e) => {
    e.preventDefault();
    if (id.trim()) navigate(`${basePath}/${id.trim()}`);
  };

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-2 sm:flex-row">
      <Input
        value={id}
        onChange={(e) => setId(e.target.value)}
        placeholder={placeholder}
        aria-label={label}
        className="flex-1"
      />
      <Button type="submit">Look up</Button>
    </form>
  );
}
