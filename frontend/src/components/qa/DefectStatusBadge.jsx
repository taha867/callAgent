import { Badge } from "@/components/ui/badge";

// DispositionBadge.jsx's exact shape: a status -> variant map. Real shadcn Badge variants
// are default|secondary|destructive|outline|ghost|link (confirmed in ui/badge.jsx) — no
// "success"/"muted" variant exists, unlike an earlier design-time assumption.
const VARIANT_BY_STATUS = {
  OPEN: "secondary",
  FIX_APPLIED: "outline",
  COMPILED: "default",
  WONT_FIX: "outline",
};

export function DefectStatusBadge({ entry }) {
  if (entry.compilation_required) {
    return <Badge variant="destructive">Compile required ({entry.occurrence_count}×)</Badge>;
  }
  return <Badge variant={VARIANT_BY_STATUS[entry.status] ?? "secondary"}>{entry.status}</Badge>;
}
