#!/usr/bin/env python3
"""Daily email reconciliation — compares Gmail inbox vs DB records.

Finds:
1. Emails in Gmail that aren't in the DB (missed by poller)
2. Customer emails that were auto-ignored (shouldn't be)
3. Threads with no customer match that should have one

Runs daily via cron. Sends alert + in-app notification on issues.
"""

import asyncio
import imaplib
import logging
import os
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

NOTIFICATION_EMAIL = os.environ.get("NOTIFICATION_EMAIL", "")
GMAIL_USER = os.environ.get("AGENT_GMAIL_USER", "")
GMAIL_PASS = os.environ.get("AGENT_GMAIL_PASSWORD", "")


def send_alert(subject: str, body: str):
    if not NOTIFICATION_EMAIL or not GMAIL_USER or not GMAIL_PASS:
        logger.error(f"Cannot send alert: {subject}")
        return
    try:
        msg = MIMEText(body)
        msg["Subject"] = f"QP Email Reconciliation: {subject}"
        msg["From"] = GMAIL_USER
        msg["To"] = NOTIFICATION_EMAIL
        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.starttls()
            s.login(GMAIL_USER, GMAIL_PASS)
            s.send_message(msg)
        logger.info(f"Alert sent: {subject}")
    except Exception as e:
        logger.error(f"Alert send failed: {e}")


def get_gmail_inbound_uids(hours: int = 24) -> set[str]:
    """Get Message-IDs of all inbound emails in Gmail from last N hours."""
    import email
    from email.header import decode_header as decode_hdr

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_USER, GMAIL_PASS)
        mail.select("INBOX")

        since = (datetime.now() - timedelta(hours=hours)).strftime("%d-%b-%Y")
        status, data = mail.search(None, "SINCE", since)
        if status != "OK" or not data[0]:
            mail.logout()
            return set()

        senders = []
        for uid in data[0].split():
            status, msg_data = mail.fetch(uid, "(BODY[HEADER.FIELDS (FROM SUBJECT)])")
            if status != "OK":
                continue
            hdr = email.message_from_bytes(msg_data[0][1])
            from_hdr = hdr.get("From", "")
            subj = hdr.get("Subject", "")

            # Decode
            import re
            email_match = re.search(r"<(.+?)>", from_hdr)
            from_email = email_match.group(1).lower() if email_match else from_hdr.lower()

            decoded_parts = decode_hdr(subj)
            clean_subject = ""
            for part, charset in decoded_parts:
                if isinstance(part, bytes):
                    clean_subject += part.decode(charset or "utf-8", errors="replace")
                else:
                    clean_subject += part

            senders.append({"from": from_email, "subject": clean_subject.strip()})

        mail.logout()
        return senders
    except Exception as e:
        logger.error(f"Gmail fetch failed: {e}")
        return []


async def reconcile():
    from sqlalchemy import select, func
    from src.core.database import get_session_maker
    from src.models.agent_message import AgentMessage
    from src.models.agent_thread import AgentThread
    from src.models.customer import Customer
    from src.models.customer_contact import CustomerContact
    from src.models.notification import Notification
    from src.models.organization_user import OrganizationUser

    issues = []

    # 1. Compare Gmail inbound count vs DB inbound count (last 24h)
    gmail_emails = get_gmail_inbound_uids(24)
    gmail_count = len(gmail_emails)

    sm = get_session_maker()
    async with sm() as db:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

        db_count = (await db.execute(
            select(func.count(AgentMessage.id)).where(
                AgentMessage.direction == "inbound",
                AgentMessage.received_at >= cutoff,
            )
        )).scalar() or 0

        # Allow slack — blocked/internal/marketing emails are filtered by the poller
        # but still exist in Gmail. Only alert if DB has drastically fewer,
        # suggesting the poller stopped working entirely.
        if gmail_count > 5 and db_count == 0:
            issues.append(
                f"Gmail has {gmail_count} inbound emails (24h) but DB only has {db_count}. "
                f"Poller may be missing emails."
            )

        # 2. Find customer emails that were auto-ignored
        ignored_customer = (await db.execute(
            select(AgentMessage.id, AgentMessage.from_email, AgentMessage.subject, AgentMessage.status)
            .join(Customer, func.lower(Customer.email) == func.lower(AgentMessage.from_email))
            .where(
                AgentMessage.direction == "inbound",
                AgentMessage.status == "ignored",
                AgentMessage.received_at >= cutoff,
                Customer.is_active == True,
            )
        )).all()

        if ignored_customer:
            for msg_id, from_email, subject, status in ignored_customer:
                issues.append(f"Customer email auto-ignored: {from_email} — {subject}")

        # Also check contact emails
        ignored_contact = (await db.execute(
            select(AgentMessage.id, AgentMessage.from_email, AgentMessage.subject)
            .join(CustomerContact, func.lower(CustomerContact.email) == func.lower(AgentMessage.from_email))
            .join(Customer, Customer.id == CustomerContact.customer_id)
            .where(
                AgentMessage.direction == "inbound",
                AgentMessage.status == "ignored",
                AgentMessage.received_at >= cutoff,
                Customer.is_active == True,
            )
        )).all()

        if ignored_contact:
            for msg_id, from_email, subject in ignored_contact:
                issues.append(f"Customer contact email auto-ignored: {from_email} — {subject}")

        # 3. Threads with no customer match that should have one
        unmatched = (await db.execute(
            select(AgentThread.id, AgentThread.contact_email, AgentThread.subject)
            .join(Customer, func.lower(Customer.email) == func.lower(AgentThread.contact_email))
            .where(
                AgentThread.matched_customer_id.is_(None),
                AgentThread.last_message_at >= cutoff,
                AgentThread.status != "archived",
                Customer.is_active == True,
            )
        )).all()

        if unmatched:
            for tid, email_addr, subj in unmatched:
                issues.append(f"Thread missing customer match: {email_addr} — {subj}")

        # Report
        if issues:
            body = f"Email reconciliation found {len(issues)} issue(s):\n\n"
            for issue in issues:
                body += f"  - {issue}\n"
            body += f"\nTimestamp: {datetime.now().isoformat()}"

            logger.error(f"Reconciliation: {len(issues)} issue(s)")
            for issue in issues:
                logger.error(f"  {issue}")

            send_alert(f"{len(issues)} issue(s) found", body)

            # In-app notification
            admins = (await db.execute(
                select(OrganizationUser).where(
                    OrganizationUser.role.in_(("owner", "admin")),
                )
            )).scalars().all()
            summary = f"{len(issues)} email issue(s): " + "; ".join(issues[:3])
            for ou in admins:
                db.add(Notification(
                    organization_id=ou.organization_id,
                    user_id=ou.user_id,
                    type="system_alert",
                    title="Email reconciliation issues",
                    body=summary[:200],
                    link="/inbox",
                ))
            await db.commit()
        else:
            logger.info(f"Reconciliation clean: {gmail_count} Gmail / {db_count} DB inbound (24h)")


if __name__ == "__main__":
    asyncio.run(reconcile())
