"""Synthetic demo dataset — customers, policies, and one MotorClaim per ClaimStage (all 18
statuses from spec §13), plus a handful of garages/documents/status events.

Fixed seed + fixed synthetic IDs, idempotent upsert: safe to re-run against a non-empty
database (the docker-compose `migrate` service runs this on every `up`). CLM-DEMO-001 is
pinned to CLAIM_REGISTERED, owned by CUST-DEMO-001 — tests/integration/test_phase0_e2e.py
hardcodes both IDs.
"""

import asyncio
import random
from datetime import date

from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.claims.constants import ClaimStage
from src.claims.models import (
    ClaimDocument,
    ClaimStatusEvent,
    MotorClaim,
    MotorPolicy,
    RepairGarage,
)
from src.customers.models import Customer, CustomerAuthFactor, CustomerContactPreference
from src.customers.service import hash_factor_value
from src.database import get_session_factory
from src.telephony.models import BusinessContactCalendar, TelephonyCliConfiguration

# Phase 4 — synthetic demo-only calendar rows so the contact-window mechanism (task 4's
# stub, telephony/service.py::is_within_contact_window) is actually exercisable by
# tests/scripted_conversations/adversarial/test_contact_window_blackout.py. NOT real UAE
# Ramadan/holiday dates — see phases/phase-5-security-compliance.md for that data feed.
_DEMO_CALENDAR_ROWS = [
    {
        "id": "DEMO-CAL-2026-09-05",
        "calendar_date": date(2026, 9, 5),
        "calendar_type": "RAMADAN",
        "contact_allowed": False,
    },
    {
        "id": "DEMO-CAL-2026-09-06",
        "calendar_date": date(2026, 9, 6),
        "calendar_type": "BLACKOUT",
        "contact_allowed": False,
    },
]

_SEED = 20260827

_FIRST_NAMES = [
    "Ahmed",
    "Fatima",
    "Mohammed",
    "Aisha",
    "Khalid",
    "Mariam",
    "Omar",
    "Layla",
    "Yousef",
    "Noor",
    "Hassan",
    "Salma",
    "Ali",
    "Huda",
    "Rashid",
]
_LAST_NAMES = ["Al Suwaidi", "Al Mansouri", "Al Marri", "Al Nuaimi", "Al Shamsi"]


async def _upsert_customer(session, *, id_: str, full_name: str, phone: str, language: str) -> None:
    stmt = pg_insert(Customer).values(
        id=id_,
        full_name=full_name,
        phone_e164=phone,
        preferred_language=language,
        national_id_last4=str(1000 + int(id_.split("-")[-1])),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[Customer.id],
        set_={
            "full_name": stmt.excluded.full_name,
            "phone_e164": stmt.excluded.phone_e164,
            "preferred_language": stmt.excluded.preferred_language,
        },
    )
    await session.execute(stmt)

    # Batch 15 — every demo customer gets a contact preference + one Level-1 auth factor
    # (a fixed birth-year value, "1990") so any harness/manual test can authenticate them.
    pref_stmt = pg_insert(CustomerContactPreference).values(
        id=f"PREF-{id_}", customer_id=id_, preferred_language=language
    )
    pref_stmt = pref_stmt.on_conflict_do_update(
        index_elements=[CustomerContactPreference.customer_id],
        set_={"preferred_language": pref_stmt.excluded.preferred_language},
    )
    await session.execute(pref_stmt)

    factor_stmt = pg_insert(CustomerAuthFactor).values(
        id=f"FACTOR-{id_}",
        customer_id=id_,
        factor_type="BIRTH_MONTH_YEAR",
        factor_value_hash=hash_factor_value("1990"),
    )
    factor_stmt = factor_stmt.on_conflict_do_update(
        index_elements=[CustomerAuthFactor.id],
        set_={"factor_value_hash": factor_stmt.excluded.factor_value_hash},
    )
    await session.execute(factor_stmt)


async def _upsert_garage(session, *, id_: str, name: str) -> None:
    stmt = pg_insert(RepairGarage).values(id=id_, name=name, phone_e164="+97140000000")
    stmt = stmt.on_conflict_do_update(
        index_elements=[RepairGarage.id], set_={"name": stmt.excluded.name}
    )
    await session.execute(stmt)


async def _upsert_policy(session, *, id_: str, customer_id: str, plate: str) -> None:
    stmt = pg_insert(MotorPolicy).values(
        id=id_,
        customer_id=customer_id,
        policy_number=f"POL-{id_.split('-')[-1]}",
        vehicle_plate=plate,
        vehicle_make_model="Toyota Camry",
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[MotorPolicy.id], set_={"vehicle_plate": stmt.excluded.vehicle_plate}
    )
    await session.execute(stmt)


async def _upsert_claim(
    session,
    *,
    id_: str,
    policy_id: str,
    customer_id: str,
    stage: ClaimStage,
    language: str,
    garage_id: str | None,
) -> None:
    delay_flag = stage in (ClaimStage.CLAIM_DELAYED,)
    customer_action_required = stage in (
        ClaimStage.CLAIM_DELAYED,
        ClaimStage.CLAIM_DECLINED,
        ClaimStage.ADDITIONAL_INFORMATION_REQUIRED,
        ClaimStage.DOCUMENTS_PENDING,
    )
    stmt = pg_insert(MotorClaim).values(
        id=id_,
        policy_id=policy_id,
        customer_id=customer_id,
        garage_id=garage_id,
        claim_stage=stage,
        current_owner="CLAIMS_TEAM",
        next_expected_event=None,
        customer_action_required=customer_action_required,
        delay_flag=delay_flag,
        approved_customer_message_key=f"MOTOR_{stage.value}",
        language=language,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[MotorClaim.id],
        set_={
            "claim_stage": stmt.excluded.claim_stage,
            "delay_flag": stmt.excluded.delay_flag,
            "customer_action_required": stmt.excluded.customer_action_required,
        },
    )
    await session.execute(stmt)


async def main() -> None:
    rng = random.Random(_SEED)
    session_factory = get_session_factory()

    async with session_factory() as session, session.begin():
        # Batch 15 — one active, trunk-authorized CLI. No BusinessContactCalendar rows:
        # task 4's stub state (absence of a row means the normal contact window applies;
        # real Ramadan/holiday data is a Phase 5 concern).
        cli_stmt = pg_insert(TelephonyCliConfiguration).values(
            cli="+971600000000", owner="ABC_INSURANCE", trunk_authorized=True, is_active=True
        )
        cli_stmt = cli_stmt.on_conflict_do_update(
            index_elements=[TelephonyCliConfiguration.cli],
            set_={"trunk_authorized": cli_stmt.excluded.trunk_authorized},
        )
        await session.execute(cli_stmt)

        # Phase 4 — Batch 15b: the two synthetic BusinessContactCalendar rows above.
        for row in _DEMO_CALENDAR_ROWS:
            cal_stmt = pg_insert(BusinessContactCalendar).values(**row)
            cal_stmt = cal_stmt.on_conflict_do_update(
                index_elements=[BusinessContactCalendar.id],
                set_={
                    "calendar_type": cal_stmt.excluded.calendar_type,
                    "contact_allowed": cal_stmt.excluded.contact_allowed,
                },
            )
            await session.execute(cal_stmt)

        garage_ids = []
        for i in range(1, 6):
            garage_id = f"GAR-DEMO-{i:03d}"
            await _upsert_garage(session, id_=garage_id, name=f"Al Futtaim Auto Care {i}")
            garage_ids.append(garage_id)

        customer_ids = []
        for i in range(1, 16):
            cust_id = f"CUST-DEMO-{i:03d}"
            language = "ar" if i % 3 == 0 else "en"
            full_name = f"{rng.choice(_FIRST_NAMES)} {rng.choice(_LAST_NAMES)}"
            phone = f"+9715{50000000 + i:08d}"
            await _upsert_customer(
                session, id_=cust_id, full_name=full_name, phone=phone, language=language
            )
            customer_ids.append(cust_id)

        stages = list(ClaimStage)  # coverage requirement: one MotorClaim per ClaimStage
        for i, stage in enumerate(stages, start=1):
            claim_id = f"CLM-DEMO-{i:03d}"
            policy_id = f"POL-DEMO-{i:03d}"
            customer_id = customer_ids[(i - 1) % len(customer_ids)]
            language = "ar" if i % 3 == 0 else "en"
            garage_id = garage_ids[i % len(garage_ids)] if i % 2 == 0 else None

            await _upsert_policy(
                session, id_=policy_id, customer_id=customer_id, plate=f"DXB-{10000 + i}"
            )

            # CLM-DEMO-001 pinned to CLAIM_REGISTERED / CUST-DEMO-001 for the e2e smoke test.
            if i == 1:
                stage = ClaimStage.CLAIM_REGISTERED
                customer_id = "CUST-DEMO-001"

            await _upsert_claim(
                session,
                id_=claim_id,
                policy_id=policy_id,
                customer_id=customer_id,
                stage=stage,
                language=language,
                garage_id=garage_id,
            )

        # A handful of documents/status events on a subset of claims.
        for i in (2, 3, 18):
            claim_id = f"CLM-DEMO-{i:03d}"
            stmt = pg_insert(ClaimDocument).values(
                id=f"DOC-DEMO-{i:03d}",
                claim_id=claim_id,
                document_type="POLICE_REPORT",
                status="PENDING",
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[ClaimDocument.id], set_={"status": stmt.excluded.status}
            )
            await session.execute(stmt)

            stmt = pg_insert(ClaimStatusEvent).values(
                id=f"EVT-DEMO-{i:03d}",
                claim_id=claim_id,
                to_stage=stages[i - 1],
                note="seeded",
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[ClaimStatusEvent.id], set_={"note": stmt.excluded.note}
            )
            await session.execute(stmt)

    print(f"seeded {len(customer_ids)} customers, {len(stages)} claims (one per ClaimStage)")


if __name__ == "__main__":
    asyncio.run(main())
