"""EmailIntegration — per-org (per-account) email integration mode and config.

One row per (organization, connected email account). An org with one Gmail
account has one row. An org with managed mode and a personal Gmail layered
on top has two rows. The active integration drives both inbound parsing
and outbound sending; the dispatch is in EmailIntegrationService and the
EmailService.

See `docs/email-integrations-plan.md` and `docs/email-strategy.md` for the
full multi-mode strategy.
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    String,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class IntegrationType(str, enum.Enum):
    """How a single email account is integrated with QP."""
    managed = "managed"          # we host inbound (Cloudflare/Postmark) + outbound (Postmark)
    gmail_api = "gmail_api"      # OAuth into customer's Gmail / Workspace
    ms_graph = "ms_graph"        # OAuth into customer's Outlook / Microsoft 365
    forwarding = "forwarding"    # customer forwards to our unique inbound address
    manual = "manual"            # no integration, manual entry only


class IntegrationStatus(str, enum.Enum):
    setup_required = "setup_required"
    connecting = "connecting"
    connected = "connected"
    error = "error"
    disconnected = "disconnected"


class EmailIntegration(Base):
    __tablename__ = "email_integrations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=IntegrationStatus.setup_required.value)

    # The OAuth-connected account email (e.g., "brian@sapphire-pools.com" for
    # gmail_api). NULL for managed/forwarding/manual modes that aren't tied
    # to a specific user account.
    account_email: Mapped[str | None] = mapped_column(String(255))

    # The customer-facing inbound address (e.g., "contact@sapphire-pools.com").
    # Used for routing rules and as the From address in some outbound paths.
    inbound_sender_address: Mapped[str | None] = mapped_column(String(255))

    # Where outbound human replies go. For Gmail mode this is gmail_api so
    # replies appear in the user's Sent folder. For managed/forwarding it's
    # postmark. (Transactional outbound — invoices, estimates — always
    # uses Postmark regardless of this field.)
    outbound_provider: Mapped[str] = mapped_column(String(20), default="postmark")

    # Encrypted JSON blob holding mode-specific config:
    # - gmail_api: oauth_token, refresh_token, token_expiry, scope, history_id, watch_expiration
    # - managed: cloudflare_worker_id, postmark_inbound_url
    # - forwarding: forwarding_address (the org-{slug}@inbound.quantumpoolspro.com address)
    # - ms_graph: oauth_token, refresh_token, etc.
    # Stored as encrypted Fernet token in TEXT (round-trip via core.encryption).
    config_encrypted: Mapped[str | None] = mapped_column(Text)

    # Sync state for Gmail/MS modes
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_history_id: Mapped[str | None] = mapped_column(String(50))
    last_error: Mapped[str | None] = mapped_column(Text)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Whether this integration is the org's PRIMARY for routing fallback.
    # In a multi-account org, exactly one integration should be primary.
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    organization = relationship("Organization", lazy="noload")

    __table_args__ = (
        # An org can have multiple integrations but each (org, account_email)
        # pair must be unique. Multiple managed/manual rows with NULL
        # account_email are allowed (NULLS NOT DISTINCT not used here so
        # NULLs collide naturally — one managed row per org).
        UniqueConstraint(
            "organization_id", "account_email",
            name="uq_email_integrations_org_account",
        ),
    )

    # ---- helpers ----

    def get_config(self) -> dict:
        """Decrypt and return the config dict, or {} if not set."""
        if not self.config_encrypted:
            return {}
        from src.core.encryption import decrypt_dict
        try:
            return decrypt_dict(self.config_encrypted)
        except Exception:
            return {}

    def set_config(self, config: dict):
        """Encrypt and store the config dict."""
        from src.core.encryption import encrypt_dict
        self.config_encrypted = encrypt_dict(config)
