#!/usr/bin/env python3
"""Background agent service — runs as systemd service, ticks every 60s.

Inbound email is handled by Postmark webhooks (not polling).
This service handles scheduled tasks: estimate reminders, message escalations,
stale visit auto-close, and heartbeat monitoring.

Monitoring:
- Sentry: all exceptions captured with full tracebacks
- ntfy: push alerts after consecutive failures (immediate visibility on phone)
- Consecutive failure tracking per function — escalates, doesn't silently loop
"""

import asyncio
import os
import sys
import logging
import traceback
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import sentry_sdk
from src.core.config import settings

# Initialize Sentry for the poller process
if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=0.1,
    )

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

POLL_INTERVAL = 60  # seconds
HEARTBEAT_EVERY = 30  # log heartbeat every N cycles (~30 min)
REMINDER_EVERY = 60  # check reminders every 60 cycles (~1 hour)

# --- Monitoring: ntfy + failure tracking ---

NTFY_URL = os.environ.get("NTFY_URL", "http://localhost:7031")
NTFY_TOPIC = "qp-alerts"
ALERT_THRESHOLD = 3  # consecutive failures before alerting
ALERT_COOLDOWN = 1800  # 30 min between ntfy alerts per function

# Track consecutive failures per function
_failure_counts: dict[str, int] = {}
_last_alert_time: dict[str, float] = {}


def _send_ntfy(title: str, message: str, priority: str = "high", tags: str = "warning"):
    """Push alert to ntfy. Non-blocking, never raises."""
    import urllib.request
    import time
    try:
        req = urllib.request.Request(
            f"{NTFY_URL}/{NTFY_TOPIC}",
            data=message.encode(),
            headers={
                "Title": title,
                "Priority": priority,
                "Tags": tags,
            },
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass  # ntfy failure must never break the poller


def _handle_error(func_name: str, error: Exception):
    """Central error handler: log, track, capture to Sentry, alert via ntfy."""
    import time

    # Always log with full traceback
    logger.error(f"{func_name} error: {error}\n{traceback.format_exc()}")

    # Always capture to Sentry
    sentry_sdk.capture_exception(error)

    # Track consecutive failures
    _failure_counts[func_name] = _failure_counts.get(func_name, 0) + 1
    count = _failure_counts[func_name]

    # Alert via ntfy after threshold consecutive failures
    if count >= ALERT_THRESHOLD:
        now = time.time()
        last_alert = _last_alert_time.get(func_name, 0)
        if (now - last_alert) >= ALERT_COOLDOWN:
            _send_ntfy(
                title=f"QP Poller: {func_name} failing",
                message=f"{count} consecutive failures.\nLatest: {error}\nCheck: sudo journalctl -u quantumpools-agent -f",
                priority="urgent" if count >= 10 else "high",
                tags="rotating_light" if count >= 10 else "warning",
            )
            _last_alert_time[func_name] = now
            logger.warning(f"ntfy alert sent for {func_name} ({count} consecutive failures)")


def _clear_failures(func_name: str):
    """Reset failure count on success."""
    if _failure_counts.get(func_name, 0) > 0:
        prev = _failure_counts[func_name]
        _failure_counts[func_name] = 0
        if prev >= ALERT_THRESHOLD:
            # Recovery notification
            _send_ntfy(
                title=f"QP Poller: {func_name} recovered",
                message=f"Back to normal after {prev} consecutive failures.",
                priority="default",
                tags="white_check_mark",
            )
            logger.info(f"{func_name} recovered after {prev} consecutive failures")


# --- Poller functions ---

async def check_estimate_reminders():
    """Send reminders for stale estimates — 3 days and 7 days after sending."""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select
    from src.core.database import get_db_context
    from src.models.invoice import Invoice
    from src.models.agent_action import AgentAction
    from src.models.job_invoice import JobInvoice
    from src.models.customer import Customer
    from src.services.email_service import EmailService

    now = datetime.now(timezone.utc)
    reminder_windows = [
        (timedelta(days=3), timedelta(days=3, hours=2)),  # 3-day reminder
        (timedelta(days=7), timedelta(days=7, hours=2)),  # 7-day reminder
    ]

    async with get_db_context() as db:
        for min_age, max_age in reminder_windows:
            cutoff_start = now - max_age
            cutoff_end = now - min_age

            result = await db.execute(
                select(Invoice, AgentAction).join(
                    JobInvoice, JobInvoice.invoice_id == Invoice.id
                ).join(
                    AgentAction, AgentAction.id == JobInvoice.action_id
                ).where(
                    Invoice.document_type == "estimate",
                    Invoice.status == "sent",
                    Invoice.sent_at.between(cutoff_start, cutoff_end),
                    AgentAction.status == "pending_approval",
                )
            )

            for invoice, action in result.all():
                if not invoice.customer_id:
                    continue

                cust_result = await db.execute(
                    select(Customer).where(Customer.id == invoice.customer_id)
                )
                customer = cust_result.scalar_one_or_none()
                if not customer or not customer.email:
                    continue

                days = (now - invoice.sent_at).days
                customer_name = f"{customer.first_name} {customer.last_name}".strip()

                email_svc = EmailService(db)
                from src.models.estimate_approval import EstimateApproval
                approval_result = await db.execute(
                    select(EstimateApproval).where(EstimateApproval.invoice_id == invoice.id)
                )
                approval = approval_result.scalar_one_or_none()
                if not approval:
                    continue

                base_url = getattr(settings, "FRONTEND_URL", None) or "https://app.quantumpoolspro.com"
                approve_url = f"{base_url}/approve/{approval.approval_token}"

                await email_svc.send_estimate_email(
                    org_id=invoice.organization_id,
                    to=customer.email,
                    customer_name=customer_name,
                    estimate_number=invoice.invoice_number,
                    subject=f"Reminder: Estimate {invoice.invoice_number} — {invoice.subject or 'Service Estimate'}",
                    total=float(invoice.total or 0),
                    view_url=approve_url,
                )
                logger.info(f"Sent {days}-day estimate reminder to {customer.email} for {invoice.invoice_number}")

        await db.commit()


async def check_message_escalations():
    """Escalate unread internal messages — email after 30 min."""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select
    from src.core.database import get_db_context
    from src.models.internal_message import InternalThread
    from src.models.user import User
    from src.services.email_service import EmailService

    now = datetime.now(timezone.utc)
    thirty_min_ago = now - timedelta(minutes=30)

    async with get_db_context() as db:
        result = await db.execute(
            select(InternalThread).where(
                InternalThread.status == "active",
                InternalThread.escalation_level < 3,
                InternalThread.last_message_at <= thirty_min_ago,
                InternalThread.last_message_by.isnot(None),
            )
        )
        for thread in result.scalars().all():
            for pid in (thread.participant_ids or []):
                if pid == thread.last_message_by:
                    continue
                user = (await db.execute(select(User).where(User.id == pid))).scalar_one_or_none()
                if not user or not user.email:
                    continue

                sender = (await db.execute(select(User).where(User.id == thread.last_message_by))).scalar_one_or_none()
                sender_name = f"{sender.first_name}" if sender else "A team member"

                email_svc = EmailService(db)
                from src.services.email_service import EmailMessage
                await email_svc.send_email(
                    org_id=thread.organization_id,
                    message=EmailMessage(
                        to=user.email,
                        subject=f"Message from {sender_name}: {thread.subject or 'New message'}",
                        text_body=f"{sender_name} sent you a message. Log in to view and respond.",
                    ),
                )
                logger.info(f"Escalated message to {user.email} for thread {thread.id}")

            thread.escalation_level = 3
        await db.commit()


AUTO_CLOSE_EVERY = 30  # check stale visits every 30 cycles (~30 min)


async def auto_close_stale_visits():
    """Auto-close stale visits (visits started but never completed)."""
    from src.services.agents.orchestrator import auto_close_stale_visits as _close
    await _close()


async def main():
    logger.info("Background agent service started (monitoring: Sentry + ntfy)")
    logger.info("Inbound email: Postmark webhooks (no IMAP polling)")
    cycle = 0

    while True:
        cycle += 1

        # --- Heartbeat ---
        if cycle % HEARTBEAT_EVERY == 0:
            fails = {k: v for k, v in _failure_counts.items() if v > 0}
            if fails:
                logger.info(f"Heartbeat: {cycle} cycles, active failures: {fails}")
            else:
                logger.info(f"Heartbeat: {cycle} cycles, all healthy")

        # --- Estimate reminders (hourly) ---
        if cycle % REMINDER_EVERY == 0:
            try:
                await check_estimate_reminders()
                _clear_failures("estimate_reminders")
            except Exception as e:
                _handle_error("estimate_reminders", e)

        # --- Message escalations (every 5 min) ---
        if cycle % 5 == 0:
            try:
                await check_message_escalations()
                _clear_failures("message_escalations")
            except Exception as e:
                _handle_error("message_escalations", e)

        # --- Stale visit auto-close (every 30 min) ---
        if cycle % AUTO_CLOSE_EVERY == 0:
            try:
                await auto_close_stale_visits()
                _clear_failures("auto_close_visits")
            except Exception as e:
                _handle_error("auto_close_visits", e)

        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
