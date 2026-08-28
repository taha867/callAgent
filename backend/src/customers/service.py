"""get_contact_preference(), get_auth_factor() — plain reads over an AsyncSession, no
Temporal awareness (calls/activities.py's authentication stage calls these)."""

import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.customers.models import CustomerAuthFactor, CustomerContactPreference


async def get_contact_preference(
    session: AsyncSession, customer_id: str
) -> CustomerContactPreference | None:
    result = await session.execute(
        select(CustomerContactPreference).where(
            CustomerContactPreference.customer_id == customer_id
        )
    )
    return result.scalars().first()


async def get_auth_factor(
    session: AsyncSession, customer_id: str, factor_type: str
) -> CustomerAuthFactor | None:
    result = await session.execute(
        select(CustomerAuthFactor).where(
            CustomerAuthFactor.customer_id == customer_id,
            CustomerAuthFactor.factor_type == factor_type,
        )
    )
    return result.scalars().first()


def hash_factor_value(value: str) -> str:
    """Same fingerprint approach as src/idempotency.py — sha256 of a normalized value.
    Never compare/store a Level-1 knowledge factor in plaintext (spec §10.2)."""
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()
