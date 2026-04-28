"""Customer-facing portal: magic-link sign-in + persistent sessions.

Customers don't have passwords. They sign in by clicking a link emailed
to a `customer_contacts.email` address. The link is single-use,
short-lived (15 min). Consuming it issues a long-lived session cookie
(30 days, sliding window refreshed on activity).

Email enumeration is intentionally prevented: requesting a link for an
unknown email returns the same shape as a successful request — a caller
cannot tell whether the email exists in the system. Every code path
through `request_magic_link` returns silently.

Multiple `customer_contacts` rows can share an email (different
customers, different orgs). For now we send a link to the first match
ordered by created_at (oldest contact wins). Multi-link-per-email is a
future enhancement when we have multi-customer/multi-org portal users.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.models.customer_contact import CustomerContact
from src.models.customer_portal import CustomerMagicLink, CustomerPortalSession
from src.models.organization import Organization
from src.services.email_service import EmailService, EmailMessage
from src.services.email_templates import customer_portal_magic_link_template

logger = logging.getLogger(__name__)

MAGIC_LINK_TTL_MINUTES = 15
SESSION_TTL_DAYS = 30
# How long a session can be idle before refresh sliding-window kicks it
# out without explicit user activity. Anything ≥ SESSION_TTL_DAYS is a
# no-op (no refresh ever extends past expires_at).
SESSION_IDLE_REFRESH_THRESHOLD_SECONDS = 60 * 5


def _new_token() -> str:
    """64-char URL-safe random token. ~48 bytes of entropy."""
    return secrets.token_urlsafe(48)[:64]


class CustomerPortalService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Magic-link sign-in ─────────────────────────────────────────────

    async def request_magic_link(
        self, email: str, requested_ip: str | None = None
    ) -> None:
        """Email a sign-in link to the contact whose email matches.

        Always returns None. The caller MUST NOT branch on whether a
        link was sent — that would leak which emails exist in the system.
        On success: a `CustomerMagicLink` is inserted and an email is
        sent. On no-match or any failure: silently no-op.
        """
        email_normalized = (email or "").strip().lower()
        if not email_normalized:
            return

        # Oldest contact wins when multiple share an email. Future:
        # send a link per match so a person tied to multiple customers
        # gets a chooser.
        contact = (await self.db.execute(
            select(CustomerContact).where(
                CustomerContact.email.ilike(email_normalized)
            ).order_by(CustomerContact.created_at.asc()).limit(1)
        )).scalar_one_or_none()

        if not contact:
            logger.info(f"Magic link requested for unknown email {email_normalized!r} — silently dropping")
            return

        token = _new_token()
        now = datetime.now(timezone.utc)
        link = CustomerMagicLink(
            contact_id=contact.id,
            customer_id=contact.customer_id,
            organization_id=contact.organization_id,
            token=token,
            expires_at=now + timedelta(minutes=MAGIC_LINK_TTL_MINUTES),
            requested_ip=requested_ip,
        )
        self.db.add(link)
        await self.db.flush()

        await self._send_magic_link_email(contact, token)
        await self.db.commit()

    async def consume_magic_link(
        self,
        token: str,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> CustomerPortalSession | None:
        """Validate and consume a magic-link token. Returns a fresh session.

        Returns None if token is invalid, expired, or already consumed.
        On success: marks the link as consumed and creates a portal
        session in the same transaction.
        """
        if not token:
            return None

        link = (await self.db.execute(
            select(CustomerMagicLink).where(CustomerMagicLink.token == token)
        )).scalar_one_or_none()

        if not link:
            return None

        now = datetime.now(timezone.utc)
        if link.consumed_at is not None:
            logger.warning(f"Magic link {link.id} already consumed at {link.consumed_at.isoformat()}")
            return None
        if link.expires_at < now:
            logger.info(f"Magic link {link.id} expired at {link.expires_at.isoformat()}")
            return None

        link.consumed_at = now

        session = CustomerPortalSession(
            contact_id=link.contact_id,
            customer_id=link.customer_id,
            organization_id=link.organization_id,
            token=_new_token(),
            expires_at=now + timedelta(days=SESSION_TTL_DAYS),
            last_seen_at=now,
            last_ip=ip,
            user_agent=(user_agent or "")[:500] or None,
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        logger.info(f"Customer portal session {session.id} created for contact {link.contact_id}")
        return session

    # ── Session management ─────────────────────────────────────────────

    async def get_session(
        self, token: str, refresh: bool = True, ip: str | None = None
    ) -> CustomerPortalSession | None:
        """Look up a session by cookie token.

        Returns None if the token is unknown, revoked, or expired.
        When `refresh=True`, slides expires_at forward by SESSION_TTL_DAYS
        and updates last_seen_at — but only if the session has been idle
        for at least SESSION_IDLE_REFRESH_THRESHOLD_SECONDS, to avoid
        writing on every request.
        """
        if not token:
            return None

        session = (await self.db.execute(
            select(CustomerPortalSession).where(
                CustomerPortalSession.token == token
            )
        )).scalar_one_or_none()

        if not session:
            return None

        now = datetime.now(timezone.utc)
        if session.revoked_at is not None:
            return None
        if session.expires_at < now:
            return None

        if refresh:
            idle_seconds = (now - session.last_seen_at).total_seconds()
            if idle_seconds >= SESSION_IDLE_REFRESH_THRESHOLD_SECONDS:
                session.last_seen_at = now
                session.expires_at = now + timedelta(days=SESSION_TTL_DAYS)
                if ip:
                    session.last_ip = ip
                await self.db.commit()
                await self.db.refresh(session)

        return session

    async def revoke_session(self, token: str) -> bool:
        """Revoke a session by token. Returns True if found and marked revoked."""
        if not token:
            return False
        session = (await self.db.execute(
            select(CustomerPortalSession).where(
                CustomerPortalSession.token == token
            )
        )).scalar_one_or_none()
        if not session or session.revoked_at is not None:
            return False
        session.revoked_at = datetime.now(timezone.utc)
        await self.db.commit()
        return True

    async def revoke_all_sessions_for_contact(self, contact_id: str) -> int:
        """Revoke every active session for a contact. Returns count revoked.

        Used when a contact is deleted, when the org admin removes them,
        or when the customer asks to sign out everywhere.
        """
        now = datetime.now(timezone.utc)
        sessions = (await self.db.execute(
            select(CustomerPortalSession).where(
                CustomerPortalSession.contact_id == contact_id,
                CustomerPortalSession.revoked_at.is_(None),
                CustomerPortalSession.expires_at > now,
            )
        )).scalars().all()
        for s in sessions:
            s.revoked_at = now
        await self.db.commit()
        return len(sessions)

    # ── Maintenance ────────────────────────────────────────────────────

    async def sweep_expired(self, magic_link_retention_days: int = 7) -> dict:
        """Delete expired sessions and old magic links.

        Sessions: any past expires_at OR revoked.
        Magic links: any past expires_at AND created_at older than
        `magic_link_retention_days` days (keep recent ones for forensics
        in case a security team wants to see what was attempted).

        Designed to be called from the agent_poller hourly.
        """
        from sqlalchemy import delete, or_
        now = datetime.now(timezone.utc)
        retention_cutoff = now - timedelta(days=magic_link_retention_days)

        sessions_result = await self.db.execute(
            delete(CustomerPortalSession).where(
                or_(
                    CustomerPortalSession.expires_at < now,
                    CustomerPortalSession.revoked_at.isnot(None),
                )
            )
        )
        links_result = await self.db.execute(
            delete(CustomerMagicLink).where(
                CustomerMagicLink.expires_at < now,
                CustomerMagicLink.created_at < retention_cutoff,
            )
        )
        await self.db.commit()
        return {
            "sessions_deleted": sessions_result.rowcount or 0,
            "magic_links_deleted": links_result.rowcount or 0,
        }

    # ── Internal helpers ───────────────────────────────────────────────

    async def _send_magic_link_email(self, contact: CustomerContact, token: str) -> None:
        """Send the magic-link email via the contact's org's email provider."""
        org = (await self.db.execute(
            select(Organization).where(Organization.id == contact.organization_id)
        )).scalar_one_or_none()
        if not org or not contact.email:
            return

        org_name = org.name or "Quantum Pools"
        branding_color = getattr(org, "branding_color", None) or "#1a1a2e"

        contact_name = (
            f"{contact.first_name or ''} {contact.last_name or ''}".strip()
            or contact.email.split("@")[0]
        )

        login_url = f"{settings.frontend_url.rstrip('/')}/portal/login/{token}"

        text, html = customer_portal_magic_link_template(
            org_name=org_name,
            contact_name=contact_name,
            login_url=login_url,
            expires_in_minutes=MAGIC_LINK_TTL_MINUTES,
            branding_color=branding_color,
        )

        msg = EmailMessage(
            to=contact.email,
            subject=f"Sign in to {org_name}",
            text_body=text,
            html_body=html,
        )

        email_svc = EmailService(self.db)
        try:
            await email_svc.send_email(contact.organization_id, msg)
        except Exception as e:
            # Don't leak send failures to the caller — they'd let an
            # attacker probe whether the SMTP path works for an email.
            logger.error(f"Magic-link email send failed for contact {contact.id}: {e}")
