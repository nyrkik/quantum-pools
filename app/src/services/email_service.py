"""Provider-agnostic email service.

All email sending in the app goes through EmailService. The provider (SMTP, Postmark,
SES, etc.) is swappable via the EmailProvider interface.
"""

import base64
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from dataclasses import dataclass, field
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders

import aiosmtplib
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.models.organization import Organization
from src.services.email_templates import (
    invoice_email_template,
    estimate_email_template,
    notification_template,
    password_changed_template,
    password_reset_template,
    team_invite_template,
)

logger = logging.getLogger(__name__)
settings = Settings()


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class EmailMessage:
    """Structured email message."""
    to: str
    subject: str
    text_body: str
    html_body: str | None = None
    from_email: str | None = None
    from_name: str | None = None
    reply_to: str | None = None
    cc: str | None = None
    attachments: list[dict] | None = None  # [{filename, content_bytes, mime_type}]
    # Inline attachments referenced from HTML via cid: URLs. Shape matches
    # `attachments` entries + `content_id` (without angle brackets).
    # Used for the signature logo; kept separate so plain "user added
    # attachments" can't accidentally be treated as inline.
    inline_attachments: list[dict] | None = None


@dataclass
class EmailResult:
    """Result of a send attempt."""
    success: bool
    message_id: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Provider interface + SMTP implementation
# ---------------------------------------------------------------------------

class EmailProvider(ABC):
    """Abstract provider — swap to Postmark/SES by implementing this."""

    @abstractmethod
    async def send(self, message: EmailMessage) -> EmailResult:
        ...


class SmtpProvider(EmailProvider):
    """Gmail / generic SMTP provider."""

    def __init__(self):
        self.host = os.environ.get("AGENT_SMTP_HOST", "smtp.gmail.com")
        self.port = int(os.environ.get("AGENT_SMTP_PORT", "587"))
        self.username = os.environ.get("AGENT_GMAIL_USER", "")
        self.password = os.environ.get("AGENT_GMAIL_PASSWORD", "")

    async def send(self, message: EmailMessage) -> EmailResult:
        if not self.username or not self.password:
            return EmailResult(success=False, error="SMTP credentials not configured")

        mime = MIMEMultipart("mixed")
        mime["From"] = f"{message.from_name} <{message.from_email}>" if message.from_name else message.from_email or ""
        mime["To"] = message.to
        if message.cc:
            mime["Cc"] = message.cc
        mime["Subject"] = message.subject
        if message.reply_to:
            mime["Reply-To"] = message.reply_to

        # Text + HTML alternative part
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(message.text_body, "plain"))
        if message.html_body:
            alt.attach(MIMEText(message.html_body, "html"))
        mime.attach(alt)

        # Attachments
        if message.attachments:
            for att in message.attachments:
                part = MIMEBase(*att["mime_type"].split("/", 1))
                part.set_payload(att["content_bytes"])
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", "attachment", filename=att["filename"])
                mime.attach(part)

        try:
            result = await aiosmtplib.send(
                mime,
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                start_tls=True,
            )
            msg_id = result[1] if isinstance(result, tuple) and len(result) > 1 else None
            return EmailResult(success=True, message_id=str(msg_id) if msg_id else None)
        except Exception as e:
            return EmailResult(success=False, error=str(e))


class PostmarkProvider(EmailProvider):
    """Postmark transactional email provider."""

    API_URL = "https://api.postmarkapp.com/email"

    def __init__(self, server_token: str):
        self.server_token = server_token

    async def send(self, message: EmailMessage) -> EmailResult:
        from_str = (
            f"{message.from_name} <{message.from_email}>"
            if message.from_name
            else message.from_email or ""
        )

        body: dict = {
            "From": from_str,
            "To": message.to,
            "Subject": message.subject,
            "TextBody": message.text_body,
            "MessageStream": "outbound",
        }
        if message.cc:
            body["Cc"] = message.cc
        if message.html_body:
            body["HtmlBody"] = message.html_body
        if message.reply_to:
            body["ReplyTo"] = message.reply_to

        postmark_atts: list[dict] = []
        if message.attachments:
            postmark_atts.extend(
                {
                    "Name": att["filename"],
                    "Content": base64.b64encode(att["content_bytes"]).decode(),
                    "ContentType": att["mime_type"],
                }
                for att in message.attachments
            )
        if message.inline_attachments:
            # Postmark convention: ContentID = `cid:<id>` marks it inline
            # (referenced via <img src="cid:<id>"> in the HTML body).
            postmark_atts.extend(
                {
                    "Name": att["filename"],
                    "Content": base64.b64encode(att["content_bytes"]).decode(),
                    "ContentType": att["mime_type"],
                    "ContentID": f"cid:{att['content_id']}",
                }
                for att in message.inline_attachments
            )
        if postmark_atts:
            body["Attachments"] = postmark_atts

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Postmark-Server-Token": self.server_token,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(self.API_URL, json=body, headers=headers)

            if resp.status_code == 200:
                data = resp.json()
                return EmailResult(success=True, message_id=data.get("MessageID"))
            else:
                error_msg = resp.json().get("Message", resp.text[:200])
                logger.error(f"Postmark send failed ({resp.status_code}): {error_msg}")
                return EmailResult(success=False, error=f"Postmark {resp.status_code}: {error_msg}")
        except Exception as e:
            logger.error(f"Postmark send error: {e}")
            return EmailResult(success=False, error=str(e))


def get_provider() -> EmailProvider:
    """Return the best available email provider based on env config."""
    token = os.environ.get("POSTMARK_SERVER_TOKEN")
    if token:
        return PostmarkProvider(token)
    return SmtpProvider()


# ---------------------------------------------------------------------------
# EmailService
# ---------------------------------------------------------------------------

class EmailService:
    """Central email service — loads org config, delegates to provider."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._provider: EmailProvider = get_provider()

    async def _get_org(self, org_id: str) -> Organization | None:
        result = await self.db.execute(select(Organization).where(Organization.id == org_id))
        return result.scalar_one_or_none()

    async def _resolve_user_sig_fields(self, org_id: str, sender_name: str | None) -> tuple[str | None, str | None]:
        """Return (email_signature, email_signoff) for the sender. Matches
        by first_name (case-insensitive) against users in the org. Returns
        (None, None) when no match — caller falls back to org defaults."""
        if not sender_name:
            return None, None
        from src.models.organization_user import OrganizationUser
        from src.models.user import User
        first_name = sender_name.split()[0].strip()
        if not first_name:
            return None, None
        row = (await self.db.execute(
            select(OrganizationUser.email_signature, OrganizationUser.email_signoff)
            .join(User, User.id == OrganizationUser.user_id)
            .where(
                OrganizationUser.organization_id == org_id,
                func.lower(User.first_name) == first_name.lower(),
            )
            .limit(1)
        )).one_or_none()
        if not row:
            return None, None
        return row[0] or None, row[1] or None

    async def _resolve_user_signature(self, org_id: str, sender_name: str | None) -> str | None:
        """Backwards-compat wrapper returning just the signature text."""
        sig, _ = await self._resolve_user_sig_fields(org_id, sender_name)
        return sig

    # In-process cache for signature logos. Keyed on (org_id, logo_url) —
    # logo_url changes trigger a fetch; otherwise the bytes are reused for
    # the life of the worker process. Small footprint (<200KB per org is
    # reasonable), no TTL because logos rarely change.
    _logo_cache: dict[tuple[str, str], tuple[bytes, str]] = {}

    async def _fetch_logo_bytes(self, org_id: str, logo_url: str) -> tuple[bytes | None, str | None]:
        """Return (bytes, mime) for the org's signature logo, or (None, None)
        on failure. Cached per (org_id, logo_url)."""
        key = (org_id, logo_url)
        hit = self._logo_cache.get(key)
        if hit is not None:
            return hit
        try:
            import httpx
            # Local uploads come through as relative paths like
            # "/uploads/..." — resolve to the backend origin.
            fetch_url = logo_url
            if fetch_url.startswith("/"):
                backend_base = os.environ.get("APP_BASE_URL", "http://localhost:7061").rstrip("/")
                fetch_url = backend_base + logo_url
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                resp = await client.get(fetch_url)
                resp.raise_for_status()
                content_type = (resp.headers.get("content-type") or "").split(";", 1)[0].strip().lower() or None
                self._logo_cache[key] = (resp.content, content_type)
                return resp.content, content_type
        except Exception as e:  # noqa: BLE001
            logger.warning("Signature logo fetch failed for org %s (%s): %s", org_id, logo_url, e)
            return None, None

    def _apply_org_defaults(self, message: EmailMessage, org: Organization | None) -> None:
        """Fill in from_email / from_name from org config when not overridden."""
        if not message.from_email:
            if org and org.agent_from_email:
                message.from_email = org.agent_from_email
            else:
                message.from_email = os.environ.get("AGENT_FROM_EMAIL", "noreply@quantumpoolspro.com")
        if not message.from_name:
            if org and org.agent_from_name:
                message.from_name = org.agent_from_name
            else:
                message.from_name = os.environ.get("AGENT_FROM_NAME", "QuantumPools")

    async def send_email(self, org_id: str, message: EmailMessage) -> EmailResult:
        """Send email using org's configured sender. Falls back to SMTP if Postmark fails."""
        org = await self._get_org(org_id)
        self._apply_org_defaults(message, org)

        result = await self._provider.send(message)
        if result.success:
            logger.info(f"Email sent to {message.to}: {message.subject}")
            return result

        # Log failure — no silent fallback. Postmark is the provider.
        logger.error(f"Email send failed to {message.to}: {result.error}")
        return result

    async def send_team_invite(
        self, org_id: str, to: str, user_name: str, setup_url: str
    ) -> EmailResult:
        """Send team member invitation email."""
        org = await self._get_org(org_id)
        org_name = org.name if org else "QuantumPools"
        color = getattr(org, "branding_color", None) or "#1a1a2e"

        text, html = team_invite_template(org_name, user_name, setup_url, branding_color=color)
        msg = EmailMessage(
            to=to,
            subject=f"You've been invited to {org_name}",
            text_body=text,
            html_body=html,
        )
        return await self.send_email(org_id, msg)

    async def send_password_reset(
        self, org_id: str, to: str, user_name: str, reset_url: str, expires_in_hours: int = 1
    ) -> EmailResult:
        """Send password reset email with token link."""
        org = await self._get_org(org_id)
        org_name = org.name if org else "QuantumPools"
        color = getattr(org, "branding_color", None) or "#1a1a2e"

        text, html = password_reset_template(
            org_name, user_name, reset_url, expires_in_hours=expires_in_hours, branding_color=color
        )
        msg = EmailMessage(
            to=to,
            subject=f"Reset your {org_name} password",
            text_body=text,
            html_body=html,
        )
        return await self.send_email(org_id, msg)

    async def send_password_changed(
        self, org_id: str, to: str, user_name: str
    ) -> EmailResult:
        """Notify user that their password was changed."""
        org = await self._get_org(org_id)
        org_name = org.name if org else "QuantumPools"
        color = getattr(org, "branding_color", None) or "#1a1a2e"

        text, html = password_changed_template(org_name, user_name, branding_color=color)
        msg = EmailMessage(
            to=to,
            subject=f"Your {org_name} password was changed",
            text_body=text,
            html_body=html,
        )
        return await self.send_email(org_id, msg)

    async def send_invoice_email(
        self,
        org_id: str,
        to: str,
        customer_name: str,
        invoice_number: str,
        subject: str,
        total: str,
        due_date: str,
        view_url: str,
    ) -> EmailResult:
        """Send invoice email with formatted template."""
        org = await self._get_org(org_id)
        org_name = org.name if org else "QuantumPools"
        color = getattr(org, "branding_color", None) or "#1a1a2e"

        text, html = invoice_email_template(
            org_name, customer_name, invoice_number, subject, total, due_date, view_url,
            branding_color=color,
        )
        msg = EmailMessage(to=to, subject=subject, text_body=text, html_body=html)
        return await self.send_email(org_id, msg)

    async def send_estimate_email(
        self,
        org_id: str,
        to: str,
        estimate_number: str,
        subject: str,
        total: float,
        view_url: str,
        property_line: str = "",
        recipient_first_name: str = "",
        # Deprecated — kept for backward compat, ignored
        customer_name: str = "",
    ) -> EmailResult:
        """Send estimate email with formatted template."""
        org = await self._get_org(org_id)
        org_name = org.name if org else "QuantumPools"
        color = getattr(org, "branding_color", None) or "#1a1a2e"

        formatted_total = f"${total:,.2f}"
        # Strip "Estimate: " prefix from subject for the body text
        estimate_subject = subject.removeprefix("Estimate: ") if subject.startswith("Estimate: ") else subject

        text, html = estimate_email_template(
            org_name, estimate_number, estimate_subject, formatted_total, view_url,
            property_line=property_line,
            recipient_first_name=recipient_first_name,
            branding_color=color,
        )
        msg = EmailMessage(to=to, subject=subject, text_body=text, html_body=html)
        return await self.send_email(org_id, msg)

    async def send_notification_email(
        self, org_id: str, to: str, subject: str, body: str
    ) -> EmailResult:
        """Send a generic notification email."""
        org = await self._get_org(org_id)
        org_name = org.name if org else "QuantumPools"
        color = getattr(org, "branding_color", None) or "#1a1a2e"

        text, html = notification_template(org_name, subject, body, branding_color=color)
        msg = EmailMessage(to=to, subject=subject, text_body=text, html_body=html)
        return await self.send_email(org_id, msg)

    async def send_agent_reply(
        self, org_id: str, to: str, subject: str, body_text: str,
        from_address: str | None = None,
        sender_name: str | None = None,
        is_new: bool = False,
        cc: str | None = None,
        attachments: list[dict] | None = None,
    ) -> EmailResult:
        """SINGLE EXIT POINT for all outbound customer-facing email.

        Every email to a customer — replies, followups, compose, agent drafts —
        must go through this method. It handles:
        - Signature: sender first name + org name + org signature block
        - Subject: adds Re: prefix unless is_new=True
        - From address: override for multi-address orgs

        Args:
            org_id: Organization ID
            to: Recipient email
            subject: Email subject (Re: prefix added automatically for replies)
            body_text: Email body (plain text, no signature — we append it)
            from_address: Override FROM email address
            sender_name: Human sender name (e.g. "Brian Parrotte") — first name used in signature
            is_new: If True, don't prepend Re: to subject
        """
        org = await self._get_org(org_id)
        org_name = org.name if org else ""
        org_sig = getattr(org, "agent_signature", None) if org else None
        auto_prefix = bool(getattr(org, "auto_signature_prefix", True)) if org else True
        include_logo = bool(getattr(org, "include_logo_in_signature", False)) if org else False
        logo_url = getattr(org, "logo_url", None) if org else None
        website_url = getattr(org, "website_url", None) if org else None
        allow_per_user = bool(getattr(org, "allow_per_user_signature", True)) if org else True

        # From-address normalization. The raw `from_address` is usually the
        # thread's delivered_to (preserves per-alias identity on replies —
        # customer emailed contact@, reply goes from contact@). But a
        # Workspace converted from a personal Gmail keeps the legacy
        # `sapphpools@gmail.com` identity live on the same mailbox; if the
        # customer has that old address on file, `delivered_to` points at
        # `@gmail.com`, and without this check QP keeps reinforcing the old
        # identity on every reply. Rule: if the caller's `from_address`
        # isn't on the org's primary domain (derived from agent_from_email),
        # override to the org's configured agent_from_email. Legacy aliases
        # never leak outbound.
        org_from = getattr(org, "agent_from_email", None) if org else None
        expected_domain = None
        if org_from and "@" in org_from:
            expected_domain = org_from.split("@", 1)[1].lower()
        if from_address and expected_domain:
            actual_domain = from_address.split("@")[-1].lower() if "@" in from_address else ""
            if actual_domain != expected_domain:
                logger.info(
                    "Overriding from_address %s -> %s (not on org domain %s)",
                    from_address, org_from, expected_domain,
                )
                from_address = org_from

        # Resolve per-user signature + sign-off from organization_users for
        # the sender. Falls back to org_sig if the user hasn't set one.
        # When the admin has disabled per-user customization, skip user
        # fields entirely — every outbound ships with only org settings.
        if allow_per_user:
            user_sig, user_signoff = await self._resolve_user_sig_fields(org_id, sender_name)
        else:
            user_sig, user_signoff = None, None

        # Fetch logo bytes if the admin toggle is on. Cached per-org so we
        # don't hit the URL on every send.
        logo_bytes, logo_mime = (None, None)
        if include_logo and logo_url:
            logo_bytes, logo_mime = await self._fetch_logo_bytes(org_id, logo_url)

        from src.services.email_signature import compose_signature
        sig = compose_signature(
            sender_first_name=sender_name.split()[0] if sender_name else None,
            org_name=org_name or None,
            auto_signature_prefix=auto_prefix,
            user_signature=user_sig,
            org_signature=org_sig,
            include_logo=include_logo,
            logo_url=logo_url,
            logo_bytes=logo_bytes,
            logo_mime_type=logo_mime,
            user_signoff=user_signoff,
            website_url=website_url,
        )

        full_body = body_text + (sig.plain or "")

        final_subject = subject or ""
        if not is_new and final_subject and not final_subject.startswith("Re:"):
            final_subject = f"Re: {final_subject}"

        from_name = f"{sender_name} at {org_name}" if sender_name and org_name else org_name or None

        # Generate HTML version from plain text — use the bare body (no
        # plain-text signature baked in, since we're appending a richer HTML
        # signature block below that can include autolinks + logo).
        from src.services.email_templates import customer_email_template
        color = getattr(org, "branding_color", None) or "#1a1a2e"
        _, html_body = customer_email_template(org_name or "QuantumPools", body_text, branding_color=color)
        if sig.html:
            # Insert the HTML signature before the closing </body> tag if
            # present; otherwise append at the end.
            if "</body>" in html_body.lower():
                # Find the actual (case-preserving) closing tag position.
                lower = html_body.lower()
                idx = lower.rfind("</body>")
                html_body = html_body[:idx] + sig.html + html_body[idx:]
            else:
                html_body = html_body + sig.html

        # --- Multi-mode dispatch (Phase 5b.1+) -------------------------------
        # If the org has a connected gmail_api EmailIntegration, route this
        # human reply through the Gmail API so it appears in the user's
        # actual Gmail Sent folder. Otherwise fall through to Postmark.
        # Transactional sends (invoices, estimates, notifications) always use
        # Postmark via send_email() — they should NOT go through this path.
        from src.models.email_integration import EmailIntegration, IntegrationStatus
        integration_row = (await self.db.execute(
            select(EmailIntegration).where(
                EmailIntegration.organization_id == org_id,
                EmailIntegration.type == "gmail_api",
                EmailIntegration.status == IntegrationStatus.connected.value,
                EmailIntegration.is_primary == True,  # noqa: E712
            )
        )).scalar_one_or_none()

        if not integration_row:
            # If a gmail_api integration exists for this org but isn't connected+primary,
            # fail fast with a user-visible error. Falling through to Postmark here
            # would send from the user's Gmail address, which is almost never a verified
            # Postmark Sender Signature → guaranteed 422. Better to tell the user to
            # reconnect Gmail than to silently 500.
            stale = (await self.db.execute(
                select(EmailIntegration).where(
                    EmailIntegration.organization_id == org_id,
                    EmailIntegration.type == "gmail_api",
                )
            )).scalars().first()
            if stale:
                return EmailResult(
                    success=False,
                    message_id=None,
                    error=(
                        f"Gmail integration is not connected (status: {stale.status}). "
                        f"Reconnect it in Inbox → Integrations."
                    ),
                )

        if integration_row:
            try:
                from src.services.gmail.outbound import send_reply as gmail_send_reply
                from src.services.gmail.client import GmailClientError
                result = await gmail_send_reply(
                    integration_row,
                    to=to,
                    subject=final_subject,
                    body_text=full_body,
                    html_body=html_body,
                    from_address=from_address or integration_row.account_email,
                    from_name=from_name,
                    attachments=attachments,
                    inline_attachments=[sig.logo_inline] if sig.logo_inline else None,
                    cc=cc,
                )
                # Persist any token-refresh side effects from build_gmail_client
                await self.db.commit()
                return EmailResult(
                    success=True,
                    message_id=result.get("id"),
                    error=None,
                )
            except GmailClientError as e:
                logger.error(f"Gmail send failed for org {org_id}, falling through to Postmark: {e}")
                # Mark the integration as errored so the UI can surface a reconnect
                # banner. Without this, OAuth disconnects fail silently — every send
                # falls through to Postmark and the user never knows their Gmail
                # integration is broken until they go check Settings → Email manually.
                try:
                    integration_row.status = IntegrationStatus.error.value
                    integration_row.last_error = str(e)[:500]
                    integration_row.last_error_at = datetime.now(timezone.utc)
                    await self.db.commit()
                except Exception as commit_err:
                    logger.warning(f"Failed to flag integration {integration_row.id} as errored: {commit_err}")
                # Fall through to Postmark below — better to deliver via the
                # transactional path than fail the user's reply outright.
            except Exception as e:
                logger.error(f"Unexpected error in Gmail send for org {org_id}: {e}", exc_info=True)
                # Fall through

        msg = EmailMessage(
            to=to, subject=final_subject, text_body=full_body, html_body=html_body,
            from_email=from_address, from_name=from_name, cc=cc, attachments=attachments,
            inline_attachments=[sig.logo_inline] if sig.logo_inline else None,
        )
        return await self.send_email(org_id, msg)

    async def send_payment_failed_email(
        self, org_id: str, to: str, customer_name: str,
        invoice_number: str, amount: float, pay_url: str,
        attempt_number: int,
    ) -> EmailResult:
        """Send payment failure notification to customer."""
        org = await self._get_org(org_id)
        org_name = org.name if org else "QuantumPools"

        if attempt_number >= 3:
            subject = f"Action Required — Payment for Invoice {invoice_number}"
            body = (
                f"Hi {customer_name},\n\n"
                f"We've been unable to process your payment of ${amount:.2f} for invoice {invoice_number} "
                f"after multiple attempts.\n\n"
                f"Please update your payment method or pay directly using the link below:\n"
                f"{pay_url}\n\n"
                f"If you have any questions, please don't hesitate to reach out.\n\n"
                f"Thank you,\n{org_name}"
            )
        else:
            subject = f"Payment Update — Invoice {invoice_number}"
            body = (
                f"Hi {customer_name},\n\n"
                f"We were unable to process your automatic payment of ${amount:.2f} for invoice {invoice_number}. "
                f"We'll try again in a few days.\n\n"
                f"If you'd like to pay now, you can use this link:\n"
                f"{pay_url}\n\n"
                f"Thank you,\n{org_name}"
            )

        from src.services.email_templates import customer_email_template
        color = getattr(org, "branding_color", None) or "#1a1a2e"
        _, html_body = customer_email_template(org_name, body, branding_color=color)

        msg = EmailMessage(to=to, subject=subject, text_body=body, html_body=html_body)
        return await self.send_email(org_id, msg)

    async def send_autopay_receipt(
        self, org_id: str, to: str, customer_name: str,
        invoice_number: str, amount: float,
    ) -> EmailResult:
        """Send autopay payment confirmation to customer."""
        org = await self._get_org(org_id)
        org_name = org.name if org else "QuantumPools"

        subject = f"Payment Received — Invoice {invoice_number}"
        body = (
            f"Hi {customer_name},\n\n"
            f"Your automatic payment of ${amount:.2f} for invoice {invoice_number} "
            f"has been processed successfully.\n\n"
            f"Thank you for your continued business.\n\n"
            f"Best regards,\n{org_name}"
        )

        from src.services.email_templates import customer_email_template
        color = getattr(org, "branding_color", None) or "#1a1a2e"
        _, html_body = customer_email_template(org_name, body, branding_color=color)

        msg = EmailMessage(to=to, subject=subject, text_body=body, html_body=html_body)
        return await self.send_email(org_id, msg)


# ---------------------------------------------------------------------------
# Standalone helpers (backward-compat for scraper alert, etc.)
# ---------------------------------------------------------------------------

async def send_scraper_alert(
    found: int, new: int, pdfs: int, errors: list[str], duration: float,
    scrape_dates: list[str] | None = None,
):
    """Send EMD scraper run summary to notification email."""
    to = settings.notification_email
    if not to:
        logger.warning("No notification email configured")
        return False

    from datetime import date as date_type
    today = date_type.today().strftime("%b %d, %Y")
    date_range = " & ".join(scrape_dates) if scrape_dates else today
    status_str = "completed" if not errors else f"completed with {len(errors)} errors"
    subject = f"EMD Scraper {today}: {new} new, {found} on portal" if found else f"EMD Scraper {today}: no inspections on portal"

    body = f"""EMD Scraper Run — {date_range}
─────────────────────
Status: {status_str}
Duration: {duration:.0f}s

On portal: {found}
New to our database: {new}
PDFs on file: {pdfs}
"""
    if errors:
        body += "\nErrors:\n" + "\n".join(f"  • {e}" for e in errors[:10])
        if len(errors) > 10:
            body += f"\n  ... and {len(errors) - 10} more"

    provider = get_provider()
    msg = EmailMessage(
        to=to,
        subject=subject,
        text_body=body,
        from_email=settings.smtp_from_email or os.environ.get("AGENT_FROM_EMAIL", "noreply@quantumpoolspro.com"),
        from_name=settings.smtp_from_name,
    )
    result = await provider.send(msg)
    if result.success:
        logger.info(f"Scraper alert sent to {to}")
    else:
        logger.error(f"Failed to send scraper alert: {result.error}")
    return result.success
