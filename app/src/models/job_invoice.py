"""JobInvoice — many-to-many link between jobs (agent_actions) and invoices/estimates."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class JobInvoice(Base):
    __tablename__ = "job_invoices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    action_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_actions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invoice_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    linked_by: Mapped[str | None] = mapped_column(String(200))
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    action = relationship("AgentAction", lazy="noload")
    invoice = relationship("Invoice", lazy="noload")
