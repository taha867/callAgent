"""get_otp_delivery_adapter — the one place that maps
VerificationConfig.OTP_DELIVERY_PROVIDER to a concrete OtpDeliveryAdapter, mirroring the
per-provider adapter-selection pattern CLAUDE.md §2.7 describes for voice/config.py.
"""

from src.verification.adapters.otp_delivery.base import OtpDeliveryAdapter
from src.verification.adapters.otp_delivery.log_only import LogOtpDeliveryAdapter


def get_otp_delivery_adapter(provider: str) -> OtpDeliveryAdapter:
    if provider == "log_only":
        return LogOtpDeliveryAdapter()
    raise ValueError(f"unknown OTP_DELIVERY_PROVIDER: {provider!r}")
