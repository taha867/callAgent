"""Imports ONLY `enum` — nothing else (see src/calls/constants.py's docstring for why)."""

from enum import StrEnum


class PiiCategory(StrEnum):
    """Spec §28's minimum-detect list, verbatim."""

    EMIRATES_ID = "EMIRATES_ID"
    PASSPORT_NUMBER = "PASSPORT_NUMBER"
    DATE_OF_BIRTH = "DATE_OF_BIRTH"
    IBAN = "IBAN"
    CARD_NUMBER = "CARD_NUMBER"
    OTP_PIN_CVV_PASSWORD = "OTP_PIN_CVV_PASSWORD"
    PHONE_NUMBER = "PHONE_NUMBER"
    EMAIL_ADDRESS = "EMAIL_ADDRESS"
    PHYSICAL_ADDRESS = "PHYSICAL_ADDRESS"
    POLICY_CLAIM_ID = "POLICY_CLAIM_ID"
    PERSON_NAME = "PERSON_NAME"
