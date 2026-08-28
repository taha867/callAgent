"""PiiRedactionEvent — spec §28/§26. Insert-only: the audit trail proving a PII category WAS
caught and masked in a given transcript turn, not a record of the matched text itself
(storing the raw PII in the audit-of-redaction table would defeat the redaction it's
auditing). Guarded by the shared src.insert_only.enforce_insert_only decorator — the same
mechanism runtime_failure_event/complaint_sla_event already use — not hand-rolled listeners.

call_id is a plain indexed string, not a ForeignKey to call_attempt — same reasoning
src/actions/models.py's Escalation.call_id and src/audit/models.py's RuntimeFailureEvent.call_id
already document: it may reference an in-flight call before the corresponding CallAttempt row
is finalized.
"""

import uuid
from datetime import datetime

from sqlalchemy import Enum as SAEnum
from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column

from src.insert_only import enforce_insert_only
from src.models import Base
from src.privacy.constants import PiiCategory


@enforce_insert_only
class PiiRedactionEvent(Base):
    __tablename__ = "pii_redaction_event"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    call_id: Mapped[str] = mapped_column(index=True)
    turn_index: Mapped[int]
    category: Mapped[PiiCategory] = mapped_column(
        SAEnum(
            PiiCategory,
            name="pii_category",
            validate_strings=True,
            native_enum=False,
            create_constraint=True,
            length=32,
        )
    )
    detector: Mapped[str]  # "REGEX" | "CHECKSUM" | "PRESIDIO_NER"
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
