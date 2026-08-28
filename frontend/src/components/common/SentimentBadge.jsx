import { Badge } from "@/components/ui/badge";

// Mirrors DispositionBadge.jsx's variantFor() pattern — a small lookup table into
// ui/badge's variants by semantic meaning.
const VARIANT_BY_SENTIMENT = { POSITIVE: "default", NEUTRAL: "secondary", NEGATIVE: "destructive" };

export function SentimentBadge({ sentiment }) {
  if (!sentiment) {
    return <Badge variant="secondary">Unknown</Badge>;
  }
  return <Badge variant={VARIANT_BY_SENTIMENT[sentiment] ?? "secondary"}>{sentiment}</Badge>;
}
