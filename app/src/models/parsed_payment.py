"""ParsedPayment model — Phase 1 payment reconciliation.

Structured-extraction output from a billing-category email. One source
email can produce N parsed_payments rows (e.g., Yardi remittance with
a tabular invoice list). Lifecycle:

  unmatched      → no candidate invoice scored above the floor
  proposed       → ambiguous; surfaces in `Needs review` for accept/reject
  auto_matched   → matcher created the Payment automatically
  manual_matched → user picked the invoice from the unmatched/proposed view
  ignored        → user dismissed; never auto-create a Payment for this row

When match_status reaches `auto_matched` or `manual_matched`, the
linked Payment + Invoice fields are populated. The original email
stays untouched — re-running parsers safely deletes + re-inserts
parsed_payments rows for a message.

See `docs/payment-reconciliation-spec.md`.
"""

import enum
import uuid
from datetime import datetime, date, timezone
from decimal import Decimal

from sqlalchemy import (
    DateTime, Date, Float, ForeignKey, Numeric, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class ParsedPaymentStatus(str, enum.Enum):
    unmatched = "unmatched"
    proposed = "proposed"
    auto_matched = "auto_matched"
    manual_matched = "manual_matched"
    ignored = "ignored"


class ParsedPayment(Base):
    __tablename__ = "parsed_payments"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()),
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_message_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agent_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    processor: Mapped[str] = mapped_column(String(40), nullable=False)

    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    payer_name: Mapped[str | None] = mapped_column(String(255))
    property_hint: Mapped[str | None] = mapped_column(String(255))
    invoice_hint: Mapped[str | None] = mapped_column(String(100))
    payment_method: Mapped[str | None] = mapped_column(String(20))
    payment_date: Mapped[date | None] = mapped_column(Date)
    reference_number: Mapped[str | None] = mapped_column(String(100))
    raw_block: Mapped[str | None] = mapped_column(Text)

    match_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ParsedPaymentStatus.unmatched.value,
    )
    matched_invoice_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("invoices.id", ondelete="SET NULL"),
    )
    payment_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("payments.id", ondelete="SET NULL"),
    )
    match_confidence: Mapped[float | None] = mapped_column(Float)
    match_reasoning: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    organization = relationship("Organization", lazy="noload")
    agent_message = relationship("AgentMessage", lazy="noload")
    matched_invoice = relationship("Invoice", lazy="noload")
    payment = relationship("Payment", lazy="noload")
