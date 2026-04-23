"""Gmail outbound — send replies via the Gmail API.

When a Gmail-mode org sends a customer reply via QP's compose UI, the
message goes through this path so it appears in the user's actual Gmail
Sent folder. This is the key UX win over Postmark for Gmail-mode orgs:
the user can see what QP sent on their behalf, threaded with their own
manual replies.

Threading is handled by setting the `threadId` field on the API call —
Gmail uses its own thread IDs which we store on AgentMessage when we sync.
For new threads (no prior message), we omit threadId.
"""

from __future__ import annotations

import base64
import logging
from email.message import EmailMessage as StdlibEmailMessage
from typing import Any

from googleapiclient.errors import HttpError

from src.models.email_integration import EmailIntegration
from src.services.gmail.client import build_gmail_client, GmailClientError

logger = logging.getLogger(__name__)


def _build_mime(
    *,
    to: str,
    cc: str | None = None,
    subject: str,
    body_text: str,
    html_body: str | None,
    from_address: str,
    from_name: str | None,
    in_reply_to: str | None,
    references: str | None,
    attachments: list[dict] | None = None,
    inline_attachments: list[dict] | None = None,
) -> str:
    """Build an RFC 5322 message and base64url-encode it for the Gmail API.

    `inline_attachments` are MIME parts referenced from the HTML body via
    `cid:<content_id>` — used for the signature logo. They become related
    parts of the HTML alternative (multipart/related) so mail clients
    render them inline, not as downloadable attachments.
    """
    msg = StdlibEmailMessage()
    if from_name:
        msg["From"] = f'"{from_name}" <{from_address}>'
    else:
        msg["From"] = from_address
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    msg["Subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references

    # Plain text + optional HTML alternative
    msg.set_content(body_text)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
        if inline_attachments:
            html_part = msg.get_body(preferencelist=("html",))
            if html_part is not None:
                for att in inline_attachments:
                    maintype, _, subtype = att["mime_type"].partition("/")
                    html_part.add_related(
                        att["content_bytes"],
                        maintype=maintype,
                        subtype=subtype or "octet-stream",
                        cid=f"<{att['content_id']}>",
                        filename=att.get("filename") or "inline",
                    )

    # File attachments
    if attachments:
        for att in attachments:
            maintype, _, subtype = att["mime_type"].partition("/")
            msg.add_attachment(
                att["content_bytes"],
                maintype=maintype,
                subtype=subtype or "octet-stream",
                filename=att["filename"],
            )

    raw = msg.as_bytes()
    return base64.urlsafe_b64encode(raw).decode("ascii")


async def send_reply(
    integration: EmailIntegration,
    *,
    to: str,
    subject: str,
    body_text: str,
    html_body: str | None = None,
    from_address: str | None = None,
    from_name: str | None = None,
    gmail_thread_id: str | None = None,
    in_reply_to_message_id: str | None = None,
    references: str | None = None,
    attachments: list[dict] | None = None,
    inline_attachments: list[dict] | None = None,
    cc: str | None = None,
) -> dict[str, Any]:
    """Send an outbound email via the Gmail API.

    Args:
        integration: The connected gmail_api EmailIntegration row.
        to: Recipient email
        subject: Subject line (caller handles Re: prefix)
        body_text: Plain text body
        html_body: Optional HTML alternative
        from_address: Override from email; defaults to integration.account_email
        from_name: Display name for the From field
        gmail_thread_id: If replying within an existing Gmail thread, set its ID
            so the message lands in that conversation
        in_reply_to_message_id: RFC 5322 Message-ID being replied to (for the In-Reply-To header)
        references: RFC 5322 References header value (chain of prior Message-IDs)

    Returns:
        dict with the response from the Gmail API: id, threadId, labelIds.
    """
    sender = from_address or integration.account_email
    if not sender:
        raise GmailClientError(f"integration {integration.id} has no account_email to send from")

    raw = _build_mime(
        to=to,
        cc=cc,
        subject=subject,
        body_text=body_text,
        html_body=html_body,
        from_address=sender,
        from_name=from_name,
        in_reply_to=in_reply_to_message_id,
        references=references,
        attachments=attachments,
        inline_attachments=inline_attachments,
    )

    body: dict[str, Any] = {"raw": raw}
    if gmail_thread_id:
        body["threadId"] = gmail_thread_id

    client = build_gmail_client(integration)

    try:
        # Run the blocking google API call in a thread so we don't stall the event loop
        import asyncio

        def _send():
            return client.users().messages().send(userId="me", body=body).execute()

        result = await asyncio.to_thread(_send)
        logger.info(
            f"Gmail send: integration={integration.id} to={to} message_id={result.get('id')} thread_id={result.get('threadId')}"
        )
        return result
    except HttpError as e:
        raise GmailClientError(f"Gmail API send failed: {e}") from e
