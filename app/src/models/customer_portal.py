"""Customer-facing portal auth: magic-link sign-in + persistent session.

Customers don't have a password — they sign in by clicking a magic link
sent to a `customer_contacts.email` address. The link itself is a
single-use, short-lived token (`CustomerMagicLink`); consuming it
issues a long-lived session cookie (`CustomerPortalSession`) used for
all subsequent portal requests.

Both tables cascade on contact / customer / org deletion so a deleted
contact can't continue holding a live session.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class CustomerMagicLink(Base):
    """Short-lived single-use sign-in token emailed to a CustomerContact."""

    __tablename__ = "customer_magic_links"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    contact_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("customer_contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    customer_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_ip: Mapped[str | None] = mapped_column(String(45))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    contact = relationship("CustomerContact", lazy="noload")


class CustomerPortalSession(Base):
    """Persistent portal session cookie. Sliding-window expiry refreshed on activity."""

    __tablename__ = "customer_portal_sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    contact_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("customer_contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    customer_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    last_ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(500))

    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    contact = relationship("CustomerContact", lazy="noload")
