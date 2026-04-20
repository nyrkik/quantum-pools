"""Provider-agnostic inbound email processing via webhooks.

Handles inbound emails from Postmark (primary), SendGrid, Mailgun, and generic webhooks.
Also handles Postmark bounce and delivery webhooks for outbound tracking.
"""

import logging
import re
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.organization import Organization

logger = logging.getLogger(__name__)


class ParsedEmail:
    """Normalized email from any provider."""

    __slots__ = (
        "from_email", "from_name", "to_email", "subject",
        "body_plain", "body_html", "headers", "raw_payload",
        "attachments",
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
        attachments: list[dict] | None = None,
    ):
        self.from_email = from_email
        self.from_name = from_name
        self.to_email = to_email
        self.subject = subject
        self.body_plain = body_plain
        self.body_html = body_html
        self.headers = headers or {}
        self.raw_payload = raw_payload or {}
        self.attachments = attachments or []


class InboundEmailService:
    """Provider-agnostic inbound email processing."""

    PROVIDER_PARSERS = {
        "sendgrid": "_parse_sendgrid",
        "postmark": "_parse_postmark",
        "mailgun": "_parse_mailgun",
        "cloudflare": "_parse_generic",
        "generic": "_parse_generic",
    }

    async def process_webhook(
        self,
        db: AsyncSession,
        org_slug: str,
        payload: dict,
        provider: str = "generic",
        webhook_type: str | None = None,
    ) -> dict:
        """Process an inbound email webhook.

        1. Look up org by slug
        2. Parse payload via provider adapter
        3. Check block rules
        4. Process via existing pipeline (process_incoming_email)

        Returns dict with status and details.
        """
        # Handle bounce/delivery/opens/spam_complaint webhooks (Postmark).
        # Routed by ?type= query param on the inbound webhook URL — see
        # docs/email-pipeline.md → "Webhook authentication & deploy".
        if webhook_type in ("bounce", "delivery", "opens", "spam_complaint"):
            return await self._handle_status_webhook(db, org_slug, payload, webhook_type)

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

        # 3. Block rules now route to Spam folder (handled by orchestrator),
        # do NOT drop here. We let the message through so it's recoverable.

        # 4. Build an email.message.EmailMessage to pass to process_incoming_email
        email_msg = self._build_email_message(parsed)

        # Stable UID from Message-ID hash — must fit in 100 chars
        import hashlib
        message_id = parsed.headers.get("Message-ID", parsed.headers.get("message-id", ""))
        if message_id:
            uid = f"pm-{hashlib.sha256(message_id.encode()).hexdigest()[:32]}"
        else:
            content = f"{parsed.from_email}|{parsed.subject}|{parsed.headers.get('Date', '')}"
            uid = f"pm-{hashlib.sha256(content.encode()).hexdigest()[:32]}"

        from src.services.agents.orchestrator import process_incoming_email
        try:
            # Attachments are added to email_msg in _build_email_message —
            # the orchestrator persists them via MessageAttachment rows.
            await process_incoming_email(uid, email_msg, organization_id=org.id)
            logger.info(f"Webhook processed for {org_slug}: {parsed.from_email} -> {parsed.subject[:60]}")

            return {"status": "processed", "from": parsed.from_email, "subject": parsed.subject}
        except Exception as e:
            logger.error(f"Webhook processing failed for {org_slug}: {e}", exc_info=True)
            return {"status": "error", "detail": "Processing failed"}

    async def _handle_status_webhook(
        self, db: AsyncSession, org_slug: str, payload: dict, webhook_type: str,
    ) -> dict:
        """Handle Postmark bounce/delivery status webhooks."""
        from src.models.agent_message import AgentMessage

        message_id = payload.get("MessageID", "")
        if not message_id:
            return {"status": "ignored", "detail": "No MessageID in payload"}

        # Resolve org from the URL slug — the webhook URL is per-org and the
        # signature gate (verify_postmark_webhook_token) ensures this request
        # is actually from us. We then constrain the message lookup to that
        # org, so a forged status update can't cross tenants even if the gate
        # is ever bypassed. (docs/inbox-security-audit-2026-04-13.md H4.)
        org_row = (await db.execute(
            select(Organization.id).where(
                Organization.slug == org_slug,
                Organization.is_active == True,  # noqa: E712
            )
        )).scalar_one_or_none()
        if not org_row:
            logger.warning(f"Status webhook for unknown org slug: {org_slug}")
            return {"status": "ignored", "detail": "Organization not found"}

        # Find the outbound message by Postmark message ID, scoped to org.
        result = await db.execute(
            select(AgentMessage).where(
                AgentMessage.postmark_message_id == message_id,
                AgentMessage.organization_id == org_row,
            )
        )
        msg = result.scalar_one_or_none()

        # NOTE: every branch writes to msg.delivery_status (delivery state),
        # NOT msg.status (workflow state). msg.status stays 'sent'/'auto_sent'
        # for the workflow tracker; delivery_status tracks what happened after
        # the send. Mixing the two (the old code did) breaks the Failed filter
        # and confuses the timeline chip.
        from datetime import datetime, timezone as _tz

        if webhook_type == "bounce":
            bounce_type = payload.get("Type", "")
            description = payload.get("Description", "")
            email_addr = payload.get("Email", "")
            logger.warning(f"Bounce ({bounce_type}): {email_addr} — {description[:120]}")

            if msg:
                msg.delivery_status = "bounced"
                msg.delivery_error = f"{bounce_type}: {description}"[:500]
                await db.commit()
                logger.info(f"Marked message {msg.id} as bounced")

            return {"status": "processed", "type": "bounce", "email": email_addr}

        elif webhook_type == "delivery":
            if msg:
                # Don't downgrade an already-bounced/spam message back to delivered
                # if Postmark sends events out-of-order.
                if msg.delivery_status not in ("bounced", "spam_complaint"):
                    msg.delivery_status = "delivered"
                    msg.delivered_at = datetime.now(_tz.utc)
                    await db.commit()

            return {"status": "processed", "type": "delivery"}

        elif webhook_type == "opens":
            # Open events fire each time a tracking pixel loads. We bump the
            # counter and stamp first_opened_at the first time only. Don't
            # touch delivery_status if it's already in a terminal failure
            # state (bounced/spam) — opens after a bounce can happen if the
            # bounce was a soft "deferred" that eventually delivered.
            if msg:
                msg.open_count = (msg.open_count or 0) + 1
                if not msg.first_opened_at:
                    msg.first_opened_at = datetime.now(_tz.utc)
                if msg.delivery_status not in ("bounced", "spam_complaint"):
                    msg.delivery_status = "opened"
                await db.commit()

            return {"status": "processed", "type": "opens"}

        elif webhook_type == "spam_complaint":
            email_addr = payload.get("Email", "")
            logger.warning(f"Spam complaint from {email_addr} for message {message_id}")
            if msg:
                msg.delivery_status = "spam_complaint"
                msg.delivery_error = "Recipient marked as spam"
                await db.commit()
            return {"status": "processed", "type": "spam_complaint", "email": email_addr}

        return {"status": "ignored", "detail": f"unknown webhook_type: {webhook_type}"}

    def _parse_sendgrid(self, payload: dict) -> ParsedEmail:
        """Parse SendGrid Inbound Parse webhook format."""
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
        """Parse Postmark Inbound webhook JSON format.

        Postmark JSON includes: FromFull, ToFull, Subject, TextBody, HtmlBody,
        Headers (list of {Name, Value}), Attachments (list of {Name, Content,
        ContentType, ContentLength}), OriginalRecipient, MessageID, Date.

        **Body sourcing (priority order):**

        1. ``RawEmail`` — if the Postmark Server has "Include raw email
           content in JSON payload" enabled, we parse the RFC 5322 bytes
           directly with ``email.message_from_string`` + ``extract_bodies``.
           Same pipeline Gmail raw ingest uses, so MIME / Content-Transfer-
           Encoding / charset quirks are handled by Python's email lib —
           NOT by trusting Postmark's pre-parsed text.
        2. ``TextBody`` / ``HtmlBody`` — fallback when ``RawEmail`` isn't
           included. These are Postmark's best-effort decode of the
           upstream MIME; some senders (confirmed: Yardi ACH notifications)
           arrive with raw QP-encoded HTML in TextBody. ``_normalize_body``
           inside ``extract_bodies`` catches that as defense-in-depth, but
           the RawEmail path is the real fix — flip the Postmark setting
           and this branch is rarely hit.
        """
        from_email = payload.get("FromFull", {}).get("Email", payload.get("From", ""))
        from_name = payload.get("FromFull", {}).get("Name", "")

        to_recipients = payload.get("ToFull", [])
        to_email = to_recipients[0].get("Email", "") if to_recipients else payload.get("To", "")

        # Parse headers from Postmark's list format
        headers = {}
        for h in payload.get("Headers", []):
            headers[h.get("Name", "")] = h.get("Value", "")

        # Postmark provides OriginalRecipient at top level (the actual envelope recipient)
        # This is the Delivered-To equivalent — critical for routing rules
        original_recipient = payload.get("OriginalRecipient", "")
        if original_recipient:
            headers["Delivered-To"] = original_recipient

        # Postmark provides MessageID and Date at top level too
        if payload.get("MessageID") and "Message-ID" not in headers:
            headers["Message-ID"] = f"<{payload['MessageID']}@inbound.postmarkapp.com>"
        if payload.get("Date") and "Date" not in headers:
            headers["Date"] = payload["Date"]

        # Parse attachments
        attachments = []
        for att in payload.get("Attachments", []):
            attachments.append({
                "Name": att.get("Name", ""),
                "Content": att.get("Content", ""),
                "ContentType": att.get("ContentType", "application/octet-stream"),
                "ContentLength": att.get("ContentLength", 0),
            })

        # Prefer RawEmail when available — gives us a real RFC 5322
        # envelope to hand to Python's email lib, identical to the Gmail
        # raw path. Provider-level body pre-parsing (TextBody/HtmlBody)
        # becomes the fallback for Postmark servers that haven't enabled
        # the raw-content option.
        body_plain, body_html = self._postmark_bodies(payload)

        return ParsedEmail(
            from_email=from_email,
            from_name=from_name,
            to_email=to_email,
            subject=payload.get("Subject", ""),
            body_plain=body_plain,
            body_html=body_html,
            headers=headers,
            raw_payload=payload,
            attachments=attachments,
        )

    @staticmethod
    def _postmark_bodies(payload: dict) -> tuple[str, str]:
        """Resolve (text_plain, text_html) from a Postmark webhook payload.

        RawEmail → parse MIME ourselves (authoritative).
        TextBody/HtmlBody → fallback, still passes through
        ``extract_bodies`` via the ``_build_email_message`` step downstream
        so ``_normalize_body`` can still repair known quirks.
        """
        raw = payload.get("RawEmail") or ""
        if raw:
            try:
                import email as _email
                from email import policy as _policy
                from src.services.agents.mail_agent import extract_bodies
                msg = _email.message_from_string(raw, policy=_policy.default)
                text, html = extract_bodies(msg)
                return text or "", html or ""
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "Postmark RawEmail parse failed, falling back to "
                    "TextBody/HtmlBody: %s", e,
                )
        return payload.get("TextBody", "") or "", payload.get("HtmlBody", "") or ""

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
        function used by the IMAP poller (during transition) and webhook handler.
        """
        msg = EmailMessage()

        # Set From with display name if available
        if parsed.from_name:
            msg["From"] = f'"{parsed.from_name}" <{parsed.from_email}>'
        else:
            msg["From"] = parsed.from_email

        msg["To"] = parsed.to_email
        msg["Subject"] = parsed.subject

        # Set Delivered-To from headers (OriginalRecipient for Postmark)
        delivered_to = parsed.headers.get("Delivered-To", parsed.to_email)
        msg["Delivered-To"] = delivered_to

        # Copy relevant headers for threading and dedup
        for header in ("Message-ID", "Date", "In-Reply-To", "References"):
            if header in parsed.headers:
                msg[header] = parsed.headers[header]

        # Set body — prefer plain text, fall back to HTML conversion
        if parsed.body_plain:
            msg.set_content(parsed.body_plain)
        elif parsed.body_html:
            from src.services.agents.mail_agent import _clean_html
            msg.set_content(_clean_html(parsed.body_html))
        else:
            msg.set_content("")

        # Attach files so the orchestrator's unified attachment path picks them up.
        # Webhook payloads (Postmark/Mailgun/SendGrid) deliver attachments out-of-band;
        # we re-attach them here so they live on the EmailMessage like a Gmail raw fetch.
        import base64
        for att in (parsed.attachments or []):
            content_b64 = att.get("Content", "")
            if not content_b64:
                continue
            try:
                content_bytes = base64.b64decode(content_b64)
            except Exception:
                continue
            filename = att.get("Name", att.get("FileName", "attachment"))
            ctype = att.get("ContentType", "application/octet-stream")
            maintype, _, subtype = ctype.partition("/")
            if not subtype:
                maintype, subtype = "application", "octet-stream"
            try:
                msg.add_attachment(content_bytes, maintype=maintype, subtype=subtype, filename=filename)
            except Exception as e:
                logger.warning(f"Failed to attach {filename}: {e}")

        return msg
