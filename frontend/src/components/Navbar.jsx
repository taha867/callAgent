import { useState } from "react";
import { Link } from "react-router";
import { Menu, X } from "lucide-react";
import { Button } from "@/components/ui/button";

const LINKS = [
  { to: "/claims", label: "Claims" },
  { to: "/calls", label: "Calls" },
  { to: "/complaints", label: "Complaints" },
];

// First real navigation — Phase 0 deferred this because there was only one route. Mobile-
// collapsed by default per CLAUDE.md §3.7. See phase-1-frontend-spec.md §7.4.
export function Navbar() {
  const [open, setOpen] = useState(false);

  return (
    <nav className="border-b border-border p-4">
      <div className="flex items-center justify-between">
        <Link to="/" className="font-semibold">
          CallAgent Ops
        </Link>
        <Button
          variant="ghost"
          size="icon"
          className="md:hidden"
          onClick={() => setOpen((v) => !v)}
          aria-label="Toggle navigation"
        >
          {open ? <X /> : <Menu />}
        </Button>
        <ul className="hidden gap-4 md:flex">
          {LINKS.map((link) => (
            <li key={link.to}>
              <Link to={link.to}>{link.label}</Link>
            </li>
          ))}
        </ul>
      </div>
      {open && (
        <ul className="mt-2 flex flex-col gap-2 md:hidden">
          {LINKS.map((link) => (
            <li key={link.to}>
              <Link to={link.to} onClick={() => setOpen(false)}>
                {link.label}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </nav>
  );
}
