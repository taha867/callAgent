"""privacy/service.py::redact() — table-driven over spec §28's minimum-detect list plus
adversarial (multi-PII, mixed) cases. The single most important test this phase adds: a
spoken-out-loud Emirates ID/IBAN/card number/OTP must NEVER survive into redact()'s output
(spec §36 rule 17).
"""

from src.privacy.service import redact

_VALID_IBAN = "AE070331234567890123456"
_VALID_CARD = "4111111111111111"


def _assert_fully_masked(raw: str, redacted: str, *raw_fragments: str) -> None:
    for fragment in raw_fragments:
        assert fragment not in redacted, f"{fragment!r} leaked into redacted output: {redacted!r}"


def test_emirates_id_redacted():
    raw = "My Emirates ID is 784-1985-1234567-1, please note it."
    result = redact(raw, language="en")
    assert "[EMIRATES_ID_REDACTED]" in result.redacted_text
    _assert_fully_masked(raw, result.redacted_text, "784-1985-1234567-1")
    assert "EMIRATES_ID" in {c.value for c in result.detections}


def test_iban_redacted():
    raw = f"Please refund to IBAN {_VALID_IBAN} today."
    result = redact(raw, language="en")
    assert "[IBAN_REDACTED]" in result.redacted_text
    _assert_fully_masked(raw, result.redacted_text, _VALID_IBAN)


def test_card_number_redacted():
    raw = f"Charge my card {_VALID_CARD} for the deductible."
    result = redact(raw, language="en")
    assert "[CARD_NUMBER_REDACTED]" in result.redacted_text
    _assert_fully_masked(raw, result.redacted_text, _VALID_CARD)


def test_otp_redacted():
    raw = "Your OTP is 482913, please read it back."
    result = redact(raw, language="en")
    assert "[OTP_PIN_CVV_PASSWORD_REDACTED]" in result.redacted_text
    _assert_fully_masked(raw, result.redacted_text, "482913")


def test_pin_redacted():
    raw = "My PIN is 4521 for that account."
    result = redact(raw, language="en")
    assert "[OTP_PIN_CVV_PASSWORD_REDACTED]" in result.redacted_text
    _assert_fully_masked(raw, result.redacted_text, "4521")


def test_password_redacted():
    raw = "My password is 998877 if you need it."
    result = redact(raw, language="en")
    assert "[OTP_PIN_CVV_PASSWORD_REDACTED]" in result.redacted_text
    _assert_fully_masked(raw, result.redacted_text, "998877")


def test_phone_number_redacted():
    raw = "You can reach me at 0501234567 anytime."
    result = redact(raw, language="en")
    assert "[PHONE_NUMBER_REDACTED]" in result.redacted_text
    _assert_fully_masked(raw, result.redacted_text, "0501234567")


def test_email_redacted():
    raw = "Send it to customer@example.com please."
    result = redact(raw, language="en")
    assert "[EMAIL_ADDRESS_REDACTED]" in result.redacted_text
    _assert_fully_masked(raw, result.redacted_text, "customer@example.com")


def test_policy_claim_id_redacted():
    raw = "This is regarding claim CLM-2026-001288."
    result = redact(raw, language="en")
    assert "[POLICY_CLAIM_ID_REDACTED]" in result.redacted_text
    _assert_fully_masked(raw, result.redacted_text, "CLM-2026-001288")


def test_otp_wins_priority_over_overlapping_generic_digit_run():
    """The OTP/PIN/CVV/password keyword-window match must take priority — spec §36's
    single highest-severity rule."""
    raw = "The verification code is 991122, thanks."
    result = redact(raw, language="en")
    assert "[OTP_PIN_CVV_PASSWORD_REDACTED]" in result.redacted_text
    _assert_fully_masked(raw, result.redacted_text, "991122")


def test_multiple_categories_in_one_turn_all_masked():
    """Adversarial/mixed case — several PII categories spoken in the same turn, none must
    survive."""
    raw = f"My Emirates ID is 784-1985-1234567-1, my card is {_VALID_CARD}, and my OTP is 552211."
    result = redact(raw, language="en")
    _assert_fully_masked(raw, result.redacted_text, "784-1985-1234567-1", _VALID_CARD, "552211")
    detected = {c.value for c in result.detections}
    assert {"EMIRATES_ID", "CARD_NUMBER", "OTP_PIN_CVV_PASSWORD"} <= detected


def test_arabic_turn_skips_presidio_but_still_redacts_deterministic_categories():
    """spec §2.4's documented gap: Arabic gets the full deterministic layer (digit/format
    based, language-independent) but no Presidio NER pass."""
    raw = "بطاقة هويتي الإماراتية هي 784-1985-1234567-1"
    result = redact(raw, language="ar")
    assert "[EMIRATES_ID_REDACTED]" in result.redacted_text
    _assert_fully_masked(raw, result.redacted_text, "784-1985-1234567-1")


def test_benign_text_no_detections():
    raw = "The repair is authorised and the garage will contact you tomorrow."
    result = redact(raw, language="en")
    assert result.redacted_text == raw
    assert result.detections == []


def test_relative_date_reference_not_treated_as_date_of_birth():
    """Regression: Presidio's DATE_TIME entity matches ANY date-shaped mention, including
    relative ones with no birth-date meaning — 'tomorrow' was getting flagged as
    DATE_OF_BIRTH, mangling an ordinary operational sentence. Only a year-bearing date
    mention should be treated as a DOB candidate."""
    raw = "The repair is authorised and the garage will contact you tomorrow."
    result = redact(raw, language="en")
    assert result.redacted_text == raw
    assert result.detections == []


def test_year_bearing_date_still_treated_as_date_of_birth():
    raw = "My date of birth is 15 March 1990."
    result = redact(raw, language="en")
    assert "[DATE_OF_BIRTH_REDACTED]" in result.redacted_text
    _assert_fully_masked(raw, result.redacted_text, "1990")


def test_presidio_person_name_redacted_english_only():
    raw = "My name is John Smith and I'm calling about my claim."
    result = redact(raw, language="en")
    assert "[PERSON_NAME_REDACTED]" in result.redacted_text
    _assert_fully_masked(raw, result.redacted_text, "John Smith")


def test_presidio_not_applied_to_arabic_person_names():
    """Same raw pattern as the English test above, but in Arabic — the Presidio pass must
    not run, so no PERSON_NAME detection occurs even though a name is present."""
    raw = "اسمي جون سميث وأتصل بخصوص مطالبتي"
    result = redact(raw, language="ar")
    assert "PERSON_NAME" not in {c.value for c in result.detections}
