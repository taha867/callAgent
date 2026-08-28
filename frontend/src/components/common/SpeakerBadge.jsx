import { Badge } from "@/components/ui/badge";

export function SpeakerBadge({ speaker }) {
  return <Badge variant={speaker === "AI" ? "default" : "outline"}>{speaker}</Badge>;
}
