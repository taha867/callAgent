"""Deterministic regex/checksum recognizers (spec §28: "implement a local deterministic
scrubber using regex/checksum rules plus NER/classification... do not make a paid cloud
redaction service mandatory") + the Presidio NER layer for the categories the deterministic
layer structurally cannot find (names, addresses, dates).

Every recognizer here returns `Match` spans over RAW text — no masking happens in this
module. `privacy/service.py::redact()` resolves overlaps across every recognizer's matches
and does the actual `[CATEGORY_REDACTED]` string replacement in one pass, so this module can
be tested purely on "did it find the right span," independent of masking mechanics.

Detection order matters for one category only: OTP_PIN_CVV_PASSWORD is found and its
resolution priority is highest (spec §36 — never log OTP/PIN/CVV/password is the single
highest-severity rule in this codebase) so it always wins an overlap against any other
category's match on the same digits.
"""

import re
from dataclasses import dataclass

from src.privacy.constants import PiiCategory


@dataclass(frozen=True)
class Match:
    start: int
    end: int
    category: PiiCategory
    detector: str  # "REGEX" | "CHECKSUM" | "PRESIDIO_NER"


# --- OTP / PIN / CVV / password — keyword-triggered digit-run mask, EN + AR, runs first ---

_OTP_TRIGGER = (
    r"(?:otp|one[- ]time (?:code|password|pin)|verification code|passcode|cvv|pin|password"
    r"|الرمز|كلمة السر|كلمة المرور|رقم سري|رمز التحقق)"
)
_OTP_PATTERN = re.compile(
    rf"{_OTP_TRIGGER}\b(?:\s+\S+){{0,3}}?\s*[:\-]?\s*(\d{{3,8}})",
    re.IGNORECASE,
)


def _find_otp_pin_cvv_password(text: str) -> list[Match]:
    return [
        Match(m.start(1), m.end(1), PiiCategory.OTP_PIN_CVV_PASSWORD, "REGEX")
        for m in _OTP_PATTERN.finditer(text)
    ]


# --- IBAN — UAE format + mod-97 (ISO 7064 MOD97-10) checksum -----------------------------

_IBAN_PATTERN = re.compile(r"\bAE\d{2}[ ]?\d{3}[ ]?\d{16}\b")


def _iban_checksum_valid(candidate: str) -> bool:
    compact = candidate.replace(" ", "").upper()
    if len(compact) != 23:
        return False
    rearranged = compact[4:] + compact[:4]
    numeric = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(numeric) % 97 == 1


def _find_iban(text: str) -> list[Match]:
    return [
        Match(m.start(), m.end(), PiiCategory.IBAN, "CHECKSUM")
        for m in _IBAN_PATTERN.finditer(text)
        if _iban_checksum_valid(m.group())
    ]


# --- Card number — 13-19 digits (spaces/dashes allowed) + Luhn checksum ------------------

_CARD_PATTERN = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def _luhn_valid(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _find_card_number(text: str) -> list[Match]:
    matches = []
    for m in _CARD_PATTERN.finditer(text):
        digits = re.sub(r"[ -]", "", m.group())
        if 13 <= len(digits) <= 19 and _luhn_valid(digits):
            matches.append(Match(m.start(), m.end(), PiiCategory.CARD_NUMBER, "CHECKSUM"))
    return matches


# --- Emirates ID — format only, no public checksum algorithm ----------------------------

_EMIRATES_ID_PATTERN = re.compile(r"\b\d{3}-\d{4}-\d{7}-\d{1}\b")


def _find_emirates_id(text: str) -> list[Match]:
    return [
        Match(m.start(), m.end(), PiiCategory.EMIRATES_ID, "REGEX")
        for m in _EMIRATES_ID_PATTERN.finditer(text)
    ]


# --- UAE mobile phone number -------------------------------------------------------------

_PHONE_PATTERN = re.compile(r"\b(?:\+971[ -]?5\d{8}|05\d{8})\b")


def _find_phone_number(text: str) -> list[Match]:
    return [
        Match(m.start(), m.end(), PiiCategory.PHONE_NUMBER, "REGEX")
        for m in _PHONE_PATTERN.finditer(text)
    ]


# --- Email address -------------------------------------------------------------------------

_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def _find_email(text: str) -> list[Match]:
    return [
        Match(m.start(), m.end(), PiiCategory.EMAIL_ADDRESS, "REGEX")
        for m in _EMAIL_PATTERN.finditer(text)
    ]


# --- Policy / claim identifier (claims/'s own id format, e.g. CLM-2026-001288) -----------

_POLICY_CLAIM_ID_PATTERN = re.compile(r"\b(?:POL|CLM)-[A-Z0-9-]+\b")


def _find_policy_claim_id(text: str) -> list[Match]:
    return [
        Match(m.start(), m.end(), PiiCategory.POLICY_CLAIM_ID, "REGEX")
        for m in _POLICY_CLAIM_ID_PATTERN.finditer(text)
    ]


def find_deterministic_matches(text: str) -> list[Match]:
    """Language-independent — every recognizer here matches digit/format patterns, not
    natural language, so this runs identically for English and Arabic turns."""
    matches: list[Match] = []
    matches.extend(_find_otp_pin_cvv_password(text))
    matches.extend(_find_iban(text))
    matches.extend(_find_card_number(text))
    matches.extend(_find_emirates_id(text))
    matches.extend(_find_phone_number(text))
    matches.extend(_find_email(text))
    matches.extend(_find_policy_claim_id(text))
    return matches


# --- Presidio NER layer — English only (spec §2.4's documented Arabic-NER gap) -----------

_PRESIDIO_ENTITY_TO_CATEGORY = {
    "PERSON": PiiCategory.PERSON_NAME,
    "LOCATION": PiiCategory.PHYSICAL_ADDRESS,
    "DATE_TIME": PiiCategory.DATE_OF_BIRTH,
}

# Presidio's DATE_TIME entity matches ANY date-shaped mention, including relative ones with
# no birth-date meaning at all ("tomorrow", "next week", "today") — confirmed empirically:
# "the garage will contact you tomorrow" was getting flagged as DATE_OF_BIRTH, mangling an
# entirely ordinary operational sentence. A DOB mention realistically carries a year; a
# relative date reference doesn't. Only promote a DATE_TIME match to DATE_OF_BIRTH when the
# matched span itself contains a plausible year — this is a precision fix, not a full DOB
# classifier, and a genuine yearless DOB phrasing (rare) is accepted as a residual gap.
_YEAR_PATTERN = re.compile(r"(?:19|20)\d{2}")

_analyzer_engine = None


def _get_analyzer_engine():
    """Lazy singleton — importing presidio_analyzer/spaCy at module-import time would make
    every test importing this module (even ones exercising only the deterministic layer)
    pay spaCy's model-load cost. Constructed once per process."""
    global _analyzer_engine
    if _analyzer_engine is None:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider

        # AnalyzerEngine() with no nlp_engine defaults to spaCy's en_core_web_lg (400MB) —
        # the Dockerfile/CI only install en_core_web_sm (see Dockerfile, backend-ci.yml),
        # so the default would silently trigger a live ~400MB download on first use. Pin
        # the model actually installed.
        nlp_engine = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
            }
        ).create_engine()
        _analyzer_engine = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
    return _analyzer_engine


def find_presidio_matches(text: str) -> list[Match]:
    """English only. Only PERSON/LOCATION/DATE_TIME are requested — Presidio's built-in
    PHONE_NUMBER/EMAIL_ADDRESS/CREDIT_CARD/IBAN_CODE recognizers are deliberately excluded:
    the deterministic layer above already covers those with UAE-specific formats and real
    checksums, which Presidio's generic recognizers don't have.

    DATE_TIME -> DATE_OF_BIRTH is over-inclusive by construction (Presidio's DATE_TIME
    entity catches any date, not just a birth date — e.g. a mentioned appointment date).
    For a redaction pipeline, over-redacting a date is the safe direction; documented here
    as a known precision/recall tradeoff, not an oversight.
    """
    engine = _get_analyzer_engine()
    results = engine.analyze(text=text, language="en", entities=list(_PRESIDIO_ENTITY_TO_CATEGORY))
    matches = []
    for r in results:
        if r.entity_type == "DATE_TIME" and not _YEAR_PATTERN.search(text[r.start : r.end]):
            continue
        matches.append(
            Match(r.start, r.end, _PRESIDIO_ENTITY_TO_CATEGORY[r.entity_type], "PRESIDIO_NER")
        )
    return matches
