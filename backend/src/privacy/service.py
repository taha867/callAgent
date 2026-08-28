"""redact() — pure, no I/O (Batch 2). record_redaction_events() — the idempotent write
(Batch 3), added once src/idempotency.py's shared wrapper is available to call into.

Per .claude/specs/phase-3-backend-spec.md §2.5, corrected by
.claude/plans/phase-3-backend-implementation-plan.md Correction 1: this module's own write
path must never be wrapped in an outer `session.begin()` by its caller — see
record_redaction_events()'s docstring below.
"""

from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.idempotency import idempotent
from src.privacy import scrubber
from src.privacy.constants import PiiCategory
from src.privacy.models import PiiRedactionEvent
from src.privacy.scrubber import Match

# Lower number = higher priority when two matches overlap. OTP/PIN/CVV/password always wins
# — spec §36's single highest-severity rule (never log OTP/PIN/CVV/password) must never lose
# to a lower-priority category matching the same digits.
_CATEGORY_PRIORITY: dict[PiiCategory, int] = {PiiCategory.OTP_PIN_CVV_PASSWORD: 0}
_DEFAULT_PRIORITY = 1


def _resolve_overlaps(matches: list[Match]) -> list[Match]:
    ranked = sorted(
        matches,
        key=lambda m: (_CATEGORY_PRIORITY.get(m.category, _DEFAULT_PRIORITY), m.start),
    )
    selected: list[Match] = []
    occupied: list[tuple[int, int]] = []
    for m in ranked:
        if any(m.start < e and m.end > s for s, e in occupied):
            continue  # overlaps an already-selected, higher-or-equal-priority match
        selected.append(m)
        occupied.append((m.start, m.end))
    return sorted(selected, key=lambda m: m.start)


def _apply_mask(text: str, resolved_matches: list[Match]) -> str:
    pieces: list[str] = []
    cursor = 0
    for m in resolved_matches:
        pieces.append(text[cursor : m.start])
        pieces.append(f"[{m.category.value}_REDACTED]")
        cursor = m.end
    pieces.append(text[cursor:])
    return "".join(pieces)


class RedactionResult(BaseModel):
    redacted_text: str
    detections: list[PiiCategory]  # categories found, deduplicated — not spans/counts


def redact(text: str, *, language: str) -> RedactionResult:
    """Pure — no I/O, no session. The deterministic layer (scrubber.find_deterministic_matches)
    always runs, language-independent. The Presidio NER layer only runs when language == 'en'
    (spec §2.4's documented Arabic-NER gap — Presidio's default engine is English-only)."""
    matches = scrubber.find_deterministic_matches(text)
    if language == "en":
        matches = matches + scrubber.find_presidio_matches(text)

    resolved = _resolve_overlaps(matches)
    redacted_text = _apply_mask(text, resolved)
    detections = sorted({m.category for m in resolved}, key=lambda c: c.value)
    return RedactionResult(redacted_text=redacted_text, detections=detections)


# Each PiiCategory is only ever produced by exactly one detector family, by construction
# (see privacy/scrubber.py) — PASSPORT_NUMBER has no recognizer yet (spec §28 lists it with
# no country-specific format to match against; reserved for a future detector, matching this
# codebase's existing pattern of enum values with no current producer, e.g.
# DispositionCode.SILENT_CALL_TECHNICAL_FAILURE).
_CATEGORY_DETECTOR: dict[PiiCategory, str] = {
    PiiCategory.EMIRATES_ID: "REGEX",
    PiiCategory.PHONE_NUMBER: "REGEX",
    PiiCategory.EMAIL_ADDRESS: "REGEX",
    PiiCategory.POLICY_CLAIM_ID: "REGEX",
    PiiCategory.OTP_PIN_CVV_PASSWORD: "REGEX",
    PiiCategory.IBAN: "CHECKSUM",
    PiiCategory.CARD_NUMBER: "CHECKSUM",
    PiiCategory.PERSON_NAME: "PRESIDIO_NER",
    PiiCategory.PHYSICAL_ADDRESS: "PRESIDIO_NER",
    PiiCategory.DATE_OF_BIRTH: "PRESIDIO_NER",
    PiiCategory.PASSPORT_NUMBER: "PRESIDIO_NER",
}


async def record_redaction_events(
    session: AsyncSession, *, call_id: str, turn_index: int, detections: list[PiiCategory]
) -> None:
    """Idempotent per CLAUDE.md §4's non-negotiable ("every actions/, complaints/,
    verification/, privacy/ write goes through src/idempotency.py"). One idempotent() call
    per detected category, keyed deterministically off (call_id, turn_index, category) — a
    retried persist_transcript_turn call must never double-log the same turn's detections.

    Per .claude/plans/phase-3-backend-implementation-plan.md Correction 1: idempotent()
    commits `session` itself — the caller (calls/activities.py::persist_transcript_turn)
    must NOT wrap this call in an outer `async with session.begin():`, the same contract
    src/actions/service.py's callers already respect.
    """
    for category in detections:
        detector = _CATEGORY_DETECTOR.get(category, "REGEX")

        async def _operation(
            category: PiiCategory = category, detector: str = detector
        ) -> dict[str, Any]:
            event = PiiRedactionEvent(
                call_id=call_id, turn_index=turn_index, category=category, detector=detector
            )
            session.add(event)
            await session.flush()
            return {
                "id": event.id,
                "call_id": event.call_id,
                "turn_index": event.turn_index,
                "category": event.category.value,
                "detector": event.detector,
            }

        await idempotent(
            session,
            key=f"pii-redaction:{call_id}:{turn_index}:{category.value}",
            correlation_id=call_id,
            operation_name="record_pii_redaction_event",
            payload={"call_id": call_id, "turn_index": turn_index, "category": category.value},
            operation=_operation,
        )
