"""Invoice and InvoiceLineItem models."""

import uuid
import enum
import secrets
from datetime import datetime, timezone, date
from sqlalchemy import String, Boolean, DateTime, Date, Text, Integer, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class InvoiceStatus(str, enum.Enum):
    draft = "draft"
    sent = "sent"
    revised = "revised"
    viewed = "viewed"
    paid = "paid"
    overdue = "overdue"
    written_off = "written_off"
    void = "void"


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Document type and details
    document_type: Mapped[str] = mapped_column(String(20), default="invoice")  # estimate, invoice
    invoice_number: Mapped[str | None] = mapped_column(String(30), nullable=True, unique=True)
    subject: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default=InvoiceStatus.draft.value, index=True)

    # Dates
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    paid_date: Mapped[date | None] = mapped_column(Date)

    # Amounts
    subtotal: Mapped[float] = mapped_column(Float, default=0.0)
    discount: Mapped[float] = mapped_column(Float, default=0.0)
    tax_rate: Mapped[float] = mapped_column(Float, default=0.0)
    tax_amount: Mapped[float] = mapped_column(Float, default=0.0)
    total: Mapped[float] = mapped_column(Float, default=0.0)
    amount_paid: Mapped[float] = mapped_column(Float, default=0.0)
    balance: Mapped[float] = mapped_column(Float, default=0.0)

    # Recurring
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)

    # Notes
    notes: Mapped[str | None] = mapped_column(Text)

    # PSS migration reference
    pss_invoice_id: Mapped[str | None] = mapped_column(String(50), index=True)

    # Stripe
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(String(255))

    # PDF + payment link
    pdf_url: Mapped[str | None] = mapped_column(String(500))
    payment_token: Mapped[str] = mapped_column(
        String(64), unique=True, default=lambda: secrets.token_urlsafe(32)
    )

    # Approval
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[str | None] = mapped_column(String(200))
    approval_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("estimate_approvals.id"))

    # Revision tracking
    revision_count: Mapped[int] = mapped_column(Integer, default=0)
    revised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Audit trail — who did what
    created_by: Mapped[str | None] = mapped_column(String(200))
    sent_by: Mapped[str | None] = mapped_column(String(200))
    voided_by: Mapped[str | None] = mapped_column(String(200))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    written_off_by: Mapped[str | None] = mapped_column(String(200))
    written_off_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    converted_by: Mapped[str | None] = mapped_column(String(200))
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Tracking
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    organization = relationship("Organization", lazy="noload")
    customer = relationship("Customer", back_populates="invoices", lazy="noload")
    line_items = relationship("InvoiceLineItem", back_populates="invoice", lazy="noload",
                              cascade="all, delete-orphan", order_by="InvoiceLineItem.sort_order")
    payments = relationship("Payment", back_populates="invoice", lazy="noload")


class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    invoice_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    service_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("services.id", ondelete="SET NULL")
    )

    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, default=1.0)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    is_taxed: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    invoice = relationship("Invoice", back_populates="line_items", lazy="noload")
    service = relationship("Service", lazy="noload")


class InvoiceRevision(Base):
    """Frozen snapshot of an invoice before each revision."""
    __tablename__ = "invoice_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    invoice_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    invoice_number_at_revision: Mapped[str] = mapped_column(String(30), nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    revised_by: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    invoice = relationship("Invoice", lazy="noload")
