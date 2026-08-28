"""Sentiment/dissatisfaction classifier — spec §18. Same shape as voice/guard.py: a cheap,
table-driven lexicon match, no I/O, never itself a state transition (the DELAY_DISSATISFACTION
safety-net signal into the workflow is decided by voice/pipeline.py's caller, not here — see
.claude/specs/phase-3-backend-spec.md §4.1).

Deliberately does NOT attempt:
- REPEATED_CONTACT — a deterministic prior-attempt-count DB check
  (calls/service.py::count_recent_attempts), not a text classification signal at all.
- FORMAL_COMPLAINT_REQUEST / HUMAN_REQUEST — already covered by voice/tools.py's
  register_complaint/create_escalation/warm_transfer tool calls; duplicating them here would
  risk a second, inconsistent complaint/escalation creation path.

EN + AR phrase lists — AR entries are common transliterated/standard-Arabic phrasings, not
an exhaustive dialect coverage (same MVP-scope caveat privacy/scrubber.py's Presidio layer
carries for Arabic).
"""

from typing import Literal

from pydantic import BaseModel

# Checked in this order — first match wins, most-specific signal first.
_DELAY_DISSATISFACTION_PATTERNS: tuple[str, ...] = (
    "been waiting",
    "this is ridiculous",
    "taking too long",
    "still not resolved",
    "why is this taking so long",
    "how much longer",
    "two weeks",
    "لقد انتظرت طويلا",
    "لماذا يستغرق هذا وقتا طويلا",
)

_SERVICE_FAILURE_PATTERNS: tuple[str, ...] = (
    "nobody called me back",
    "no one is helping",
    "keeps failing",
    "system keeps failing",
    "this service is terrible",
    "you people never",
    "الخدمة سيئة",
)

_CUSTOMER_DISPUTE_PATTERNS: tuple[str, ...] = (
    "that's not true",
    "that is not true",
    "that's incorrect",
    "i already submitted",
    "i don't agree",
    "that's wrong",
    "هذا غير صحيح",
)

_NEGATIVE_SENTIMENT_PATTERNS: tuple[str, ...] = (
    "ridiculous",
    "unacceptable",
    "furious",
    "angry",
    "frustrated",
    "terrible",
    "awful",
    "upset",
    "disappointed",
    "غير مقبول",
    "أنا غاضب",
    "محبط",
)

_POSITIVE_PATTERNS: tuple[str, ...] = (
    "thank you",
    "thanks",
    "great",
    "perfect",
    "appreciate it",
    "that's helpful",
    "wonderful",
    "شكرا",
    "ممتاز",
)

_SIGNAL_LEXICON: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("DELAY_DISSATISFACTION", _DELAY_DISSATISFACTION_PATTERNS),
    ("SERVICE_FAILURE", _SERVICE_FAILURE_PATTERNS),
    ("CUSTOMER_DISPUTE", _CUSTOMER_DISPUTE_PATTERNS),
    ("NEGATIVE_SENTIMENT", _NEGATIVE_SENTIMENT_PATTERNS),
)


class SentimentClassification(BaseModel):
    sentiment: Literal["POSITIVE", "NEUTRAL", "NEGATIVE"]
    signal: str | None = None  # one of spec §18's names, or None
    confidence: float = 0.0


def classify_sentiment(text: str) -> SentimentClassification:
    """Never raises — an empty/odd utterance is simply NEUTRAL, not an error."""
    lowered = text.lower()

    for signal_name, patterns in _SIGNAL_LEXICON:
        for pattern in patterns:
            if pattern in lowered:
                return SentimentClassification(
                    sentiment="NEGATIVE", signal=signal_name, confidence=0.85
                )

    for pattern in _POSITIVE_PATTERNS:
        if pattern in lowered:
            return SentimentClassification(sentiment="POSITIVE", confidence=0.7)

    return SentimentClassification(sentiment="NEUTRAL", confidence=0.5)
