"""Provider-agnostic inbound email processing via webhooks."""

import logging
import re
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.organization import Organization
from src.services.inbox_routing_service import check_sender_blocked

logger = logging.getLogger(__name__)


class ParsedEmail:
    """Normalized email from any provider."""

    __slots__ = (
        "from_email", "from_name", "to_email", "subject",
        "body_plain", "body_html", "headers", "raw_payload",
    )

    def __init__(
        self,
        from_email: str,
        to_email: str,
        subject: str,
        body_plain: str = "",
        body_html: str = "",
        from_name: str = "",
        headers: dict | None = None,
        raw_payload: dict | None = None,
    ):
        self.from_email = from_email
        self.from_name = from_name
        self.to_email = to_email
        self.subject = subject
        self.body_plain = body_plain
        self.body_html = body_html
        self.headers = headers or {}
        self.raw_payload = raw_payload or {}


class InboundEmailService:
    """Provider-agnostic inbound email processing."""

    PROVIDER_PARSERS = {
        "sendgrid": "_parse_sendgrid",
        "postmark": "_parse_postmark",
        "mailgun": "_parse_mailgun",
        "generic": "_parse_generic",
    }

    async def process_webhook(
        self,
        db: AsyncSession,
        org_slug: str,
        payload: dict,
        provider: str = "generic",
    ) -> dict:
        """Process an inbound email webhook.

        1. Look up org by slug
        2. Parse payload via provider adapter
        3. Check block rules
        4. Process via existing pipeline (process_incoming_email)

        Returns dict with status and details.
        """
        # 1. Look up org
        result = await db.execute(
            select(Organization).where(
                Organization.slug == org_slug,
                Organization.is_active == True,
            )
        )
        org = result.scalar_one_or_none()
        if not org:
            logger.warning(f"Webhook for unknown org slug: {org_slug}")
            return {"status": "error", "detail": "Organization not found"}

        # 2. Parse payload
        parser_name = self.PROVIDER_PARSERS.get(provider, "_parse_generic")
        parser = getattr(self, parser_name)
        try:
            parsed = parser(payload)
        except Exception as e:
            logger.error(f"Failed to parse {provider} webhook for {org_slug}: {e}")
            return {"status": "error", "detail": "Failed to parse email payload"}

        if not parsed.from_email:
            return {"status": "error", "detail": "No sender email in payload"}

        # 3. Check block rules
        block_rule = await check_sender_blocked(db, org.id, parsed.from_email)
        if block_rule:
            logger.info(f"Webhook blocked by rule '{block_rule.address_pattern}': {parsed.from_email}")
            return {"status": "blocked", "detail": f"Sender blocked by rule: {block_rule.address_pattern}"}

        # 4. Build an email.message.EmailMessage to pass to process_incoming_email
        email_msg = self._build_email_message(parsed)

        # Generate a stable UID from message headers or content
        message_id = parsed.headers.get("Message-ID", parsed.headers.get("message-id", ""))
        uid = f"webhook-{org_slug}-{hash(message_id or (parsed.from_email + parsed.subject))}"

        from src.services.agents.orchestrator import process_incoming_email
        try:
            await process_incoming_email(uid, email_msg, organization_id=org.id)
            logger.info(f"Webhook processed for {org_slug}: {parsed.from_email} -> {parsed.subject[:60]}")
            return {"status": "processed", "from": parsed.from_email, "subject": parsed.subject}
        except Exception as e:
            logger.error(f"Webhook processing failed for {org_slug}: {e}", exc_info=True)
            return {"status": "error", "detail": "Processing failed"}

    def _parse_sendgrid(self, payload: dict) -> ParsedEmail:
        """Parse SendGrid Inbound Parse webhook format.

        SendGrid sends form-encoded data with fields:
        from, to, subject, text, html, headers, envelope, etc.
        """
        from_raw = payload.get("from", "")
        from_match = re.search(r"<(.+?)>", from_raw)
        from_email = from_match.group(1) if from_match else from_raw
        from_name_match = re.match(r'"?([^"<]+)"?\s*<', from_raw)
        from_name = from_name_match.group(1).strip() if from_name_match else ""

        headers = {}
        raw_headers = payload.get("headers", "")
        if raw_headers:
            for line in raw_headers.split("\n"):
                if ": " in line:
                    key, val = line.split(": ", 1)
                    headers[key.strip()] = val.strip()

        return ParsedEmail(
            from_email=from_email.strip(),
            from_name=from_name,
            to_email=payload.get("to", ""),
            subject=payload.get("subject", ""),
            body_plain=payload.get("text", ""),
            body_html=payload.get("html", ""),
            headers=headers,
            raw_payload=payload,
        )

    def _parse_postmark(self, payload: dict) -> ParsedEmail:
        """Parse Postmark Inbound webhook JSON format."""
        from_email = payload.get("FromFull", {}).get("Email", payload.get("From", ""))
        from_name = payload.get("FromFull", {}).get("Name", "")

        to_recipients = payload.get("ToFull", [])
        to_email = to_recipients[0].get("Email", "") if to_recipients else payload.get("To", "")

        headers = {}
        for h in payload.get("Headers", []):
            headers[h.get("Name", "")] = h.get("Value", "")

        return ParsedEmail(
            from_email=from_email,
            from_name=from_name,
            to_email=to_email,
            subject=payload.get("Subject", ""),
            body_plain=payload.get("TextBody", ""),
            body_html=payload.get("HtmlBody", ""),
            headers=headers,
            raw_payload=payload,
        )

    def _parse_mailgun(self, payload: dict) -> ParsedEmail:
        """Parse Mailgun Routes webhook format."""
        from_raw = payload.get("from", payload.get("sender", ""))
        from_match = re.search(r"<(.+?)>", from_raw)
        from_email = from_match.group(1) if from_match else from_raw
        from_name_match = re.match(r'"?([^"<]+)"?\s*<', from_raw)
        from_name = from_name_match.group(1).strip() if from_name_match else ""

        headers = {}
        raw_headers = payload.get("message-headers")
        if isinstance(raw_headers, list):
            for pair in raw_headers:
                if isinstance(pair, list) and len(pair) >= 2:
                    headers[pair[0]] = pair[1]

        return ParsedEmail(
            from_email=from_email.strip(),
            from_name=from_name,
            to_email=payload.get("recipient", payload.get("To", "")),
            subject=payload.get("subject", payload.get("Subject", "")),
            body_plain=payload.get("body-plain", payload.get("stripped-text", "")),
            body_html=payload.get("body-html", payload.get("stripped-html", "")),
            headers=headers,
            raw_payload=payload,
        )

    def _parse_generic(self, payload: dict) -> ParsedEmail:
        """Generic format for testing and custom integrations."""
        return ParsedEmail(
            from_email=payload.get("from_email", payload.get("from", "")),
            from_name=payload.get("from_name", ""),
            to_email=payload.get("to_email", payload.get("to", "")),
            subject=payload.get("subject", ""),
            body_plain=payload.get("body_plain", payload.get("body", payload.get("text", ""))),
            body_html=payload.get("body_html", payload.get("html", "")),
            headers=payload.get("headers", {}),
            raw_payload=payload,
        )

    def _build_email_message(self, parsed: ParsedEmail) -> EmailMessage:
        """Build a stdlib EmailMessage from parsed webhook data.

        This lets us pass webhook emails into the same process_incoming_email()
        function used by the IMAP poller.
        """
        msg = EmailMessage()

        # Set From with display name if available
        if parsed.from_name:
            msg["From"] = f'"{parsed.from_name}" <{parsed.from_email}>'
        else:
            msg["From"] = parsed.from_email

        msg["To"] = parsed.to_email
        msg["Subject"] = parsed.subject
        msg["Delivered-To"] = parsed.to_email

        # Copy relevant headers
        if "Message-ID" in parsed.headers:
            msg["Message-ID"] = parsed.headers["Message-ID"]
        if "Date" in parsed.headers:
            msg["Date"] = parsed.headers["Date"]
        if "In-Reply-To" in parsed.headers:
            msg["In-Reply-To"] = parsed.headers["In-Reply-To"]
        if "References" in parsed.headers:
            msg["References"] = parsed.headers["References"]

        # Set body — prefer plain text
        msg.set_content(parsed.body_plain or parsed.body_html or "")

        return msg
