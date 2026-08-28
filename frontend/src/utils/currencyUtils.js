// ClaimStatusRead.settlement_amount is a backend Decimal that Pydantic v2 serializes as a
// plain JSON number by default — the wire format already isn't the end-to-end Decimal
// guarantee CLAUDE.md §4 asks for (see phase-1-frontend-spec.md decision 0.9, flagged back
// to the backend spec owner, not fixed here). This formatter contains the damage: it is a
// display-only value everywhere in this app. Never sum it, average it, or otherwise treat
// the parsed number as safe for arithmetic.
const AED_FORMATTER = new Intl.NumberFormat("en-AE", {
  style: "currency",
  currency: "AED",
  minimumFractionDigits: 2,
});

export function formatAedAmount(amount) {
  if (amount == null) return null;
  return AED_FORMATTER.format(amount);
}
