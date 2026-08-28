"""OutboundCampaign, CallJob — spec §26. CallJob is the unit RetrySchedulerWorkflow
(src/campaigns/workflows.py, added later this phase) is keyed on.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base


class OutboundCampaign(Base):
    __tablename__ = "outbound_campaign"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    reason: Mapped[str]  # e.g. "REPAIR_AUTHORIZED" — spec §4's example `reason`
    priority: Mapped[str] = mapped_column(default="NORMAL")  # NORMAL | URGENT
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class CallJob(Base):
    """One per (campaign, customer, claim) — the unit RetrySchedulerWorkflow is keyed on."""

    __tablename__ = "call_job"

    id: Mapped[str] = mapped_column(primary_key=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("outbound_campaign.id"), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customer.id"), index=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("motor_claim.id"), index=True)
    status: Mapped[str] = mapped_column(default="QUEUED")  # QUEUED | IN_PROGRESS | DONE
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
