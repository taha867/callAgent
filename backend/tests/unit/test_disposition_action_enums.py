import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, StatementError

from src.actions.constants import ActionCode
from src.calls.constants import DispositionCode
from src.claims.models import ClaimStage

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_FIXTURES_DIR = _BACKEND_DIR / "tests" / "fixtures"


def _read_codes(name: str) -> set[str]:
    return {
        line.strip() for line in (_FIXTURES_DIR / name).read_text().splitlines() if line.strip()
    }


def test_disposition_code_matches_spec_fixture_exactly():
    assert {m.value for m in DispositionCode} == _read_codes("spec_disposition_codes.txt")


def test_action_code_matches_spec_fixture_exactly():
    assert {m.value for m in ActionCode} == _read_codes("spec_action_codes.txt")


def test_disposition_code_count_and_name_equals_value():
    assert len(DispositionCode) == 46
    assert all(m.name == m.value for m in DispositionCode)


def test_action_code_count_and_name_equals_value():
    assert len(ActionCode) == 21
    assert all(m.name == m.value for m in ActionCode)


def test_claim_stage_count():
    assert len(ClaimStage) == 18


def test_invalid_disposition_code_raises_value_error():
    with pytest.raises(ValueError):
        DispositionCode("NOT_A_REAL_CODE")


def test_invalid_action_code_raises_value_error():
    with pytest.raises(ValueError):
        ActionCode("NOT_A_REAL_CODE")


async def test_claim_stage_check_constraint_rejects_invalid_value_via_raw_sql(db_session):
    """Proves the DB-level half of spec decision 5's runtime enforcement — a raw SQL
    insert bypassing the ORM is still rejected by the CHECK constraint."""
    from src.claims.models import MotorPolicy
    from src.customers.models import Customer

    db_session.add(Customer(id="CUST-ENUM-TEST", full_name="x", phone_e164="+1"))
    await db_session.flush()
    db_session.add(
        MotorPolicy(
            id="POL-ENUM-TEST",
            customer_id="CUST-ENUM-TEST",
            policy_number="P1",
            vehicle_plate="X",
            vehicle_make_model="Y",
        )
    )
    await db_session.flush()

    with pytest.raises((IntegrityError, DBAPIError)):
        await db_session.execute(
            text(
                "INSERT INTO motor_claim (id, policy_id, customer_id, claim_stage, "
                "customer_action_required, delay_flag, language) "
                "VALUES ('CLM-ENUM-TEST', 'POL-ENUM-TEST', 'CUST-ENUM-TEST', 'NOT_A_STAGE', "
                "false, false, 'en')"
            )
        )


async def test_claim_stage_orm_insert_rejects_invalid_value(db_session):
    """Proves the ORM-level half (validate_strings=True). Assigning the bad value doesn't
    raise immediately — sa.Enum validates at bind-parameter time, i.e. on flush — where it
    raises StatementError wrapping a builtin LookupError, never reaching the database."""
    from src.claims.models import MotorClaim

    claim = MotorClaim(
        id="CLM-ENUM-TEST-2",
        policy_id="POL-X",
        customer_id="CUST-X",
        claim_stage="NOT_A_STAGE",  # type: ignore[arg-type]
        language="en",
    )
    db_session.add(claim)
    with pytest.raises(StatementError):
        await db_session.flush()


def test_static_checker_clean_against_src():
    from scripts.ci.check_disposition_action_codes import scan_paths

    assert scan_paths([_BACKEND_DIR / "src"]) == []


def test_static_checker_catches_fixture_violations():
    from scripts.ci.check_disposition_action_codes import scan_paths

    violations = scan_paths([_FIXTURES_DIR / "bad_disposition_codes.py"])
    codes = {v.code for v in violations}
    assert codes == {"UNKNOWN_DISPOSITION_CODE", "UNKNOWN_ACTION_CODE"}
    assert len(violations) == 3


def test_cli_exits_nonzero_on_fixture():
    result = subprocess.run(
        [
            sys.executable,
            str(_BACKEND_DIR / "scripts" / "ci" / "check_disposition_action_codes.py"),
            "--path",
            str(_FIXTURES_DIR / "bad_disposition_codes.py"),
        ],
        cwd=_BACKEND_DIR,
        capture_output=True,
    )
    assert result.returncode == 1


def test_cli_exits_zero_against_src():
    result = subprocess.run(
        [
            sys.executable,
            str(_BACKEND_DIR / "scripts" / "ci" / "check_disposition_action_codes.py"),
            "--path",
            "src",
        ],
        cwd=_BACKEND_DIR,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout.decode() + result.stderr.decode()
