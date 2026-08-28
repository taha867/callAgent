"""privacy/scrubber.py's card-number recognizer — Luhn checksum, not just a 13-19-digit
count match. Both test values below are the same length; only the checksum tells them apart.
"""

from src.privacy.scrubber import _find_card_number, _luhn_valid

_VALID_CARD = "4111111111111111"  # well-known Luhn-valid test Visa number
_INVALID_CHECKSUM_CARD = "4111111111111112"  # last digit flipped


def test_valid_checksum_accepted():
    assert _luhn_valid(_VALID_CARD) is True


def test_invalid_checksum_rejected():
    assert _luhn_valid(_INVALID_CHECKSUM_CARD) is False


def test_find_card_number_matches_valid_checksum_only():
    text = f"My card number is {_VALID_CARD} please charge it."
    matches = _find_card_number(text)
    assert len(matches) == 1
    assert matches[0].category.value == "CARD_NUMBER"


def test_find_card_number_skips_digit_run_with_bad_checksum():
    text = f"My card number is {_INVALID_CHECKSUM_CARD} please charge it."
    assert _find_card_number(text) == []


def test_find_card_number_handles_spaced_and_dashed_formats():
    spaced = "4111 1111 1111 1111"
    dashed = "4111-1111-1111-1111"
    assert len(_find_card_number(spaced)) == 1
    assert len(_find_card_number(dashed)) == 1
