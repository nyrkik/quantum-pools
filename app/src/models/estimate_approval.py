"""Estimate approval records — legal proof of client approval."""

import uuid
import secrets
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


class EstimateApproval(Base):
    __tablename__ = "estimate_approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    invoice_id: Mapped[str] = mapped_column(String(36), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)

    # Who approved
    approved_by_type: Mapped[str] = mapped_column(String(20))  # client, admin_on_behalf
    approved_by_name: Mapped[str] = mapped_column(String(200))
    approved_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))

    # Client verification (for self-service)
    client_ip: Mapped[str | None] = mapped_column(String(50))
    client_email: Mapped[str | None] = mapped_column(String(255))
    approval_token: Mapped[str] = mapped_column(String(64), unique=True, default=lambda: secrets.token_urlsafe(32))
    approval_method: Mapped[str] = mapped_column(String(30))  # email_link, portal, admin_dashboard, sms, phone

    # Frozen snapshot of what was approved
    snapshot_json: Mapped[str] = mapped_column(Text)  # JSON: line items, totals, terms

    # Future: e-signature
    signature_data: Mapped[str | None] = mapped_column(Text)

    # Admin notes (for on-behalf approvals)
    notes: Mapped[str | None] = mapped_column(Text)

    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
