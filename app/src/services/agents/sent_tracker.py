"""Track outbound emails sent via Gmail (not through the app).

When someone replies from Gmail or an alias, the sent email appears in
[Gmail]/Sent Mail. We match it to an existing thread and record it as an
outbound message, marking the thread as handled.
"""

import re
import logging
import uuid as uuid_mod
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from email.header import decode_header

from sqlalchemy import select

from src.core.database import get_db_context
from src.models.agent_thread import AgentThread
from src.models.agent_message import AgentMessage
from src.models.agent_action import AgentAction, AgentActionComment

from .mail_agent import fetch_sent_emails, mark_sent_processed, extract_text_body
from .thread_manager import update_thread_status

logger = logging.getLogger(__name__)


async def process_sent_emails(org_id: str) -> int:
    """Track outbound emails sent via Gmail. Returns count of newly tracked emails."""
    sent = fetch_sent_emails()
    if not sent:
        return 0

    count = 0
    for uid, msg in sent:
        try:
            from_email = msg.get("From", "")
            to_email = msg.get("To", "")
            subject = msg.get("Subject", "")

            # Only track emails FROM org addresses
            if not any(addr in from_email.lower() for addr in ["sapphire-pools.com", "sapphire_pools", "quantumpoolspro.com"]):
                mark_sent_processed(uid)
                continue

            # Skip emails sent to org addresses (internal)
            if not to_email or all(addr in to_email.lower() for addr in ["sapphire-pools.com", "quantumpoolspro.com"]):
                mark_sent_processed(uid)
                continue

            # Skip system emails (invites, password resets, etc.)
            subject_lower = (subject or "").lower()
            if any(skip in subject_lower for skip in ["invited to", "set up your", "password reset", "verify your", "welcome to"]):
                mark_sent_processed(uid)
                continue

            # Extract recipient email
            to_match = re.search(r'[\w.+-]+@[\w.-]+', to_email)
            if not to_match:
                mark_sent_processed(uid)
                continue
            recipient = to_match.group().lower()

            # Extract sender name
            from_match = re.match(r'"?([^"<]+)"?\s*<', from_email)
            sender_name = from_match.group(1).strip() if from_match else "Team"

            body = extract_text_body(msg)
            date_header = msg.get("Date")
            sent_at = parsedate_to_datetime(date_header) if date_header else datetime.now(timezone.utc)

            # Decode MIME-encoded subject
            decoded_parts = decode_header(subject)
            clean_subject = ""
            for part, charset in decoded_parts:
                if isinstance(part, bytes):
                    clean_subject += part.decode(charset or "utf-8", errors="replace")
                else:
                    clean_subject += part
            subject = clean_subject.strip()

            # Find existing thread only — do NOT create new threads for sent emails
            async with get_db_context() as db:
                thread_result = await db.execute(
                    select(AgentThread).where(
                        AgentThread.organization_id == org_id,
                        AgentThread.contact_email == recipient,
                    ).order_by(AgentThread.last_message_at.desc()).limit(5)
                )
                thread = None
                for t in thread_result.scalars().all():
                    t_subj = re.sub(r'^(?:Re|Fwd|Fw):\s*', '', t.subject or '', flags=re.IGNORECASE).strip().lower()
                    s_subj = re.sub(r'^(?:Re|Fwd|Fw):\s*', '', subject, flags=re.IGNORECASE).strip().lower()
                    if t_subj == s_subj or t_subj in s_subj or s_subj in t_subj:
                        thread = t
                        break

                if not thread:
                    mark_sent_processed(uid)
                    continue

                # Check if we already recorded this
                time_window = sent_at - timedelta(minutes=5)
                existing = await db.execute(
                    select(AgentMessage).where(
                        AgentMessage.thread_id == thread.id,
                        AgentMessage.direction == "outbound",
                        AgentMessage.received_at >= time_window,
                    ).limit(1)
                )
                if existing.scalar_one_or_none():
                    mark_sent_processed(uid)
                    continue

                # Record the outbound message
                outbound = AgentMessage(
                    id=str(uuid_mod.uuid4()),
                    organization_id=org_id,
                    direction="outbound",
                    from_email=from_email,
                    to_email=to_email,
                    subject=subject,
                    body=body,
                    status="sent",
                    sent_at=sent_at,
                    received_at=sent_at,
                    thread_id=thread.id,
                )
                db.add(outbound)

                # Link to open jobs on this thread
                if thread.id:
                    open_actions = (await db.execute(
                        select(AgentAction).where(
                            AgentAction.thread_id == thread.id,
                            AgentAction.organization_id == org_id,
                            AgentAction.status.in_(("open", "in_progress")),
                        )
                    )).scalars().all()
                    for action in open_actions:
                        comment = AgentActionComment(
                            organization_id=org_id,
                            action_id=action.id,
                            author=sender_name or "Team",
                            text=f"Email sent to {recipient}: {subject}",
                        )
                        db.add(comment)

                await db.commit()

            # Recalculate thread status
            await update_thread_status(thread.id)

            mark_sent_processed(uid)
            logger.info(f"Tracked sent email from {sender_name} to {recipient}: {subject[:50]}")
            count += 1

        except Exception as e:
            logger.error(f"Error tracking sent email {uid}: {e}", exc_info=True)
            mark_sent_processed(uid)

    return count
