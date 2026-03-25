"""Provider-agnostic email service.

All email sending in the app goes through EmailService. The provider (SMTP, Postmark,
SES, etc.) is swappable via the EmailProvider interface.
"""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders

import aiosmtplib
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.models.organization import Organization
from src.services.email_templates import (
    invoice_email_template,
    estimate_email_template,
    notification_template,
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
    attachments: list[dict] | None = None  # [{filename, content_bytes, mime_type}]


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


# ---------------------------------------------------------------------------
# EmailService
# ---------------------------------------------------------------------------

class EmailService:
    """Central email service — loads org config, delegates to provider."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._provider: EmailProvider = SmtpProvider()

    async def _get_org(self, org_id: str) -> Organization | None:
        result = await self.db.execute(select(Organization).where(Organization.id == org_id))
        return result.scalar_one_or_none()

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
        """Send email using org's configured sender."""
        org = await self._get_org(org_id)
        self._apply_org_defaults(message, org)

        result = await self._provider.send(message)
        if result.success:
            logger.info(f"Email sent to {message.to}: {message.subject}")
        else:
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
        customer_name: str,
        estimate_number: str,
        subject: str,
        total: str,
        view_url: str,
    ) -> EmailResult:
        """Send estimate email with formatted template."""
        org = await self._get_org(org_id)
        org_name = org.name if org else "QuantumPools"
        color = getattr(org, "branding_color", None) or "#1a1a2e"

        text, html = estimate_email_template(
            org_name, customer_name, estimate_number, subject, total, view_url,
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
        self, org_id: str, to: str, subject: str, body_text: str
    ) -> EmailResult:
        """Send an agent email reply (plain text, Re: prefix handled by caller)."""
        re_subject = f"Re: {subject}" if subject and not subject.startswith("Re:") else subject
        msg = EmailMessage(to=to, subject=re_subject, text_body=body_text)
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

    provider = SmtpProvider()
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
