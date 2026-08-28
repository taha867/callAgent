"""privacy/scrubber.py's IBAN recognizer — mod-97 (ISO 7064 MOD97-10) checksum, not just a
23-character AE-prefixed digit-count match. Both test values below are format-valid; only
the checksum test tells them apart.
"""

from src.privacy.scrubber import _find_iban, _iban_checksum_valid

_VALID_AE_IBAN = "AE070331234567890123456"
_INVALID_CHECKSUM_AE_IBAN = "AE070331234567890123457"  # last digit flipped


def test_valid_checksum_accepted():
    assert _iban_checksum_valid(_VALID_AE_IBAN) is True


def test_invalid_checksum_rejected():
    assert _iban_checksum_valid(_INVALID_CHECKSUM_AE_IBAN) is False


def test_find_iban_matches_valid_checksum_only():
    text = f"My IBAN is {_VALID_AE_IBAN} for the refund."
    matches = _find_iban(text)
    assert len(matches) == 1
    assert matches[0].category.value == "IBAN"
    assert text[matches[0].start : matches[0].end] == _VALID_AE_IBAN


def test_find_iban_skips_format_match_with_bad_checksum():
    text = f"My IBAN is {_INVALID_CHECKSUM_AE_IBAN} for the refund."
    assert _find_iban(text) == []
