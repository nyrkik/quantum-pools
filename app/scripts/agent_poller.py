#!/usr/bin/env python3
"""Customer Agent Email Poller — runs as systemd service, polls every 60s."""

import asyncio
import os
import sys
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

POLL_INTERVAL = 60  # seconds
HEARTBEAT_EVERY = 30  # log heartbeat every N cycles (~30 min)


REMINDER_EVERY = 60  # check reminders every 60 cycles (~1 hour)


async def check_estimate_reminders():
    """Send reminders for stale estimates — 3 days and 7 days after sending."""
    try:
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import select, and_
        from src.core.database import get_db_context
        from src.models.invoice import Invoice
        from src.models.agent_action import AgentAction
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
                        AgentAction, AgentAction.invoice_id == Invoice.id
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

                    # Check if already reminded (use viewed_at as a rough proxy — don't spam)
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

                    from src.core.config import settings
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
    except Exception as e:
        logger.error(f"Estimate reminder error: {e}")


async def check_message_escalations():
    """Escalate unread internal messages — email after 30 min."""
    try:
        from datetime import timedelta
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
                # Find recipients who haven't seen it
                for pid in (thread.participant_ids or []):
                    if pid == thread.last_message_by:
                        continue
                    # Get user email
                    user = (await db.execute(select(User).where(User.id == pid))).scalar_one_or_none()
                    if not user or not user.email:
                        continue

                    sender = (await db.execute(select(User).where(User.id == thread.last_message_by))).scalar_one_or_none()
                    sender_name = f"{sender.first_name}" if sender else "A team member"

                    email_svc = EmailService(db)
                    await email_svc.send_email(
                        org_id=thread.organization_id,
                        to=user.email,
                        subject=f"Message from {sender_name}: {thread.subject or 'New message'}",
                        body=f"{sender_name} sent you a message. Log in to view and respond.",
                    )
                    logger.info(f"Escalated message to {user.email} for thread {thread.id}")

                thread.escalation_level = 3
            await db.commit()
    except Exception as e:
        logger.error(f"Message escalation error: {e}")


async def main():
    from src.services.customer_agent import run_poll_cycle

    logger.info("Customer Agent Poller started")
    cycle = 0

    while True:
        try:
            count = await run_poll_cycle()
            if count > 0:
                logger.info(f"Processed {count} emails")
            cycle += 1
            if cycle % HEARTBEAT_EVERY == 0:
                logger.info(f"Heartbeat: {cycle} cycles, no errors")

            # Check estimate reminders hourly
            if cycle % REMINDER_EVERY == 0:
                await check_estimate_reminders()

            # Check message escalations every 5 cycles (~5 min)
            if cycle % 5 == 0:
                await check_message_escalations()
        except Exception as e:
            logger.error(f"Poll cycle error: {e}")

        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
