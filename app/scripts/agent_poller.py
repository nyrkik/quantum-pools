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
from datetime import datetime, timedelta, timezone
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
DUNNING_EVERY = 60 * 24  # daily — dunning cadence is in days, no need to check faster

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

async def run_dunning_for_all_orgs():
    """Daily pass: advance every org's eligible past-due invoices through
    the next dunning step. Per-org error isolation so one broken org's
    dunning can't block the others."""
    from sqlalchemy import select
    from src.core.database import get_db_context
    from src.models.organization import Organization
    from src.services.billing_service import BillingService

    async with get_db_context() as db:
        org_ids = [
            r[0]
            for r in (await db.execute(select(Organization.id))).all()
        ]

    total_sent = 0
    for org_id in org_ids:
        try:
            async with get_db_context() as db:
                svc = BillingService(db)
                summary = await svc.run_dunning_sequence(org_id)
                total_sent += summary.get("sent", 0)
        except Exception as e:
            logger.error(f"Dunning sequence failed for org {org_id}: {e}")
            sentry_sdk.capture_exception(e)

    if total_sent > 0:
        logger.info(f"Dunning daily run: sent {total_sent} email(s) across {len(org_ids)} org(s)")


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


# Per-integration backoff window. Populated when Gmail returns 429 with a
# Retry-After (or its body's "Retry after <RFC 3339>"). Skipping cycles inside
# this window stops us from extending the rate-limit lockout each minute.
# In-memory only — on poller restart we forget and observe the 429 once more,
# which is fine.
_gmail_retry_after: dict[str, datetime] = {}

# Visibility for non-connected integrations. Without this, a row that flips
# from 'connected' to 'connecting'/'error'/'disconnected' silently drops out
# of the poller loop and nobody notices that customer mail has stopped
# flowing. _integration_unhealthy_since marks first-sighting per poller run;
# _integration_unhealthy_alerted tracks which we've already pinged about so
# the ntfy fires once per outage, not every cycle.
_integration_unhealthy_since: dict[str, datetime] = {}
_integration_unhealthy_alerted: set[str] = set()
INTEGRATION_UNHEALTHY_ALERT_HOURS = 2


def _parse_gmail_retry_after(error: Exception) -> datetime | None:
    """Extract a Retry-After timestamp from a googleapiclient HttpError, if any.

    Gmail surfaces rate-limit timing in two places:
      * HTTP `Retry-After` header (seconds or HTTP-date)
      * Body `"Retry after 2026-04-28T10:04:16.279Z"` substring on 429s

    Returns a UTC datetime, or None if nothing parseable.
    """
    import re
    from email.utils import parsedate_to_datetime
    from googleapiclient.errors import HttpError

    if not isinstance(error, HttpError):
        return None

    try:
        retry_hdr = error.resp.get("retry-after") if error.resp else None
    except Exception:
        retry_hdr = None
    if retry_hdr:
        try:
            return datetime.now(timezone.utc) + timedelta(seconds=int(retry_hdr))
        except ValueError:
            try:
                dt = parsedate_to_datetime(retry_hdr)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except Exception:
                pass

    m = re.search(r"Retry after (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)", str(error))
    if m:
        try:
            return datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
        except ValueError:
            pass
    return None


async def gmail_incremental_sync():
    """Pull new mail from every connected Gmail integration.

    Runs every cycle (60s). Without this, mail sent directly to the connected
    Gmail account (not via the *@org-domain alias path) only arrives in QP
    when someone manually clicks Sync. Discovered 2026-04-13: 30+ hour gap
    where two real customer emails sat in Gmail and never reached the inbox.

    Per-integration try/except so one broken integration can't block others.
    On persistent failure (3 consecutive), the integration is flipped to
    status='error' with last_error so the inbox banner surfaces it.

    On 429 with Retry-After, the integration is parked until that timestamp
    passes. Without this, the original 2026-04-28 incident extended Gmail's
    rate-limit lockout for hours by retrying every minute.
    """
    from sqlalchemy import select
    from src.core.database import get_db_context
    from src.models.email_integration import EmailIntegration, IntegrationStatus
    from src.services.gmail.sync import GmailSyncService

    async with get_db_context() as db:
        integrations = (await db.execute(
            select(EmailIntegration).where(
                EmailIntegration.type == "gmail_api",
            )
        )).scalars().all()
        # Detach the rows so we can use them outside this DB session.
        all_rows = [(i.id, i.organization_id, i.account_email, i.status) for i in integrations]

    now = datetime.now(timezone.utc)

    # Visibility on non-connected integrations: log first sighting, ntfy after
    # INTEGRATION_UNHEALTHY_ALERT_HOURS. Then build the actual sync target list
    # from only the connected ones.
    targets = []
    for integ_id, org_id, account, status in all_rows:
        if status == IntegrationStatus.connected.value:
            targets.append((integ_id, org_id, account))
            if integ_id in _integration_unhealthy_since:
                # Recovered
                _integration_unhealthy_since.pop(integ_id, None)
                _integration_unhealthy_alerted.discard(integ_id)
                logger.info(f"Gmail integration {account} recovered to status='connected'")
            continue

        if integ_id not in _integration_unhealthy_since:
            _integration_unhealthy_since[integ_id] = now
            logger.warning(
                f"Gmail integration {account} (id={integ_id}) in non-connected "
                f"status: {status!r}. Poller will skip it until reconnected."
            )

        duration = now - _integration_unhealthy_since[integ_id]
        if (
            duration > timedelta(hours=INTEGRATION_UNHEALTHY_ALERT_HOURS)
            and integ_id not in _integration_unhealthy_alerted
        ):
            _integration_unhealthy_alerted.add(integ_id)
            _send_ntfy(
                title=f"QP Gmail integration silent: {account}",
                message=(
                    f"Status has been {status!r} for "
                    f"{duration.total_seconds() / 3600:.1f}h. Poller is skipping it — "
                    f"real customer mail may not be reaching the inbox. Reconnect "
                    f"via /inbox/integrations or check email_integrations.id={integ_id}."
                ),
                priority="high",
                tags="warning,email,gmail",
            )

    for integ_id, org_id, account in targets:
        per_key = f"gmail_sync_{integ_id}"

        retry_at = _gmail_retry_after.get(integ_id)
        if retry_at and now < retry_at:
            # Still inside the rate-limit cool-down. Skip silently.
            continue
        if retry_at and now >= retry_at:
            _gmail_retry_after.pop(integ_id, None)

        # Cross-path park (set by outbound send / read-sync 429s) — survives
        # poller restart unlike the in-memory dict above. Skip silently if
        # another path has already noted a Retry-After we should respect.
        from src.services.gmail.rate_limit import (
            is_gmail_rate_limited,
            record_gmail_rate_limit,
        )
        if await is_gmail_rate_limited(integ_id):
            continue

        try:
            # Re-fetch with a fresh session so each integration's sync gets a
            # clean session for token-refresh writes.
            async with get_db_context() as db:
                fresh = (await db.execute(
                    select(EmailIntegration).where(EmailIntegration.id == integ_id)
                )).scalar_one_or_none()
                if not fresh or fresh.status != IntegrationStatus.connected.value:
                    continue
                svc = GmailSyncService(fresh)
                stats = await svc.incremental_sync()
            if stats.get("ingested", 0) > 0:
                logger.info(f"Gmail sync {account}: ingested {stats['ingested']} (errors={stats.get('errors',0)})")
            _clear_failures(per_key)
        except Exception as e:
            retry_at = _parse_gmail_retry_after(e)
            if retry_at:
                _gmail_retry_after[integ_id] = retry_at
                # Persist too so other paths (outbound, read-sync) honour the
                # park even if the poller restarts.
                await record_gmail_rate_limit(integ_id, retry_at)
                logger.warning(
                    f"Gmail sync rate-limited for {account} until {retry_at.isoformat()} — backing off"
                )
                # Don't count rate-limit responses as a "broken integration"
                # signal; they self-heal once the cool-down passes.
                continue

            _failure_counts[per_key] = _failure_counts.get(per_key, 0) + 1
            logger.warning(f"Gmail sync failed for {account} (count={_failure_counts[per_key]}): {e}")
            # After 3 consecutive failures, flip the integration to error so the
            # banner surfaces it. Capture the actual reason in last_error.
            if _failure_counts[per_key] >= 3:
                try:
                    async with get_db_context() as db:
                        fresh = (await db.execute(
                            select(EmailIntegration).where(EmailIntegration.id == integ_id)
                        )).scalar_one_or_none()
                        if fresh:
                            fresh.status = IntegrationStatus.error.value
                            fresh.last_error = f"{type(e).__name__}: {e}"[:500]
                            fresh.last_error_at = datetime.now(timezone.utc)
                            await db.commit()
                    _send_ntfy(
                        title=f"QP Gmail sync: {account} broken",
                        message=f"3+ consecutive Gmail sync failures for {account}.\nLast error: {e}\nReconnect in /settings/email.",
                    )
                except Exception as inner:
                    logger.error(f"Failed to flag integration {integ_id} as errored: {inner}")


INBOUND_FRESHNESS_EVERY = 5  # check every 5 cycles (~5 min)
INBOUND_BUSINESS_HOURS_THRESHOLD_MIN = 6 * 60   # 6h during business hours
INBOUND_OFF_HOURS_THRESHOLD_MIN = 24 * 60       # 24h overnight/weekends
RECONCILE_EVERY = 30  # every 30 cycles (~30 min)


def _is_business_hours_pacific() -> bool:
    """Mon-Fri, 7am-8pm Pacific. Used to pick the inbound-freshness threshold."""
    try:
        from zoneinfo import ZoneInfo
        from datetime import datetime as _dt
        now = _dt.now(ZoneInfo("America/Los_Angeles"))
        return now.weekday() < 5 and 7 <= now.hour < 20
    except Exception:
        return True  # default to stricter threshold on error


async def inbound_freshness_check():
    """Alert if no inbound email has arrived recently — system-wide canary.

    This catches the failure mode where every per-integration health probe
    looks fine but no mail is actually flowing (Postmark webhook endpoint
    broken, Cloudflare worker down, all integrations dead, MX misconfig…).

    Threshold is generous outside business hours since real customer email
    can legitimately go quiet overnight.
    """
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select, func
    from src.core.database import get_db_context
    from src.models.agent_message import AgentMessage

    threshold_min = INBOUND_BUSINESS_HOURS_THRESHOLD_MIN if _is_business_hours_pacific() else INBOUND_OFF_HOURS_THRESHOLD_MIN
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=threshold_min)

    async with get_db_context() as db:
        latest = (await db.execute(
            select(func.max(AgentMessage.received_at)).where(
                AgentMessage.direction == "inbound",
            )
        )).scalar()

    if latest is None:
        # Empty database / brand-new install — nothing to alert on yet.
        return

    if latest >= cutoff:
        # Recent inbound — clear any prior staleness flag.
        _clear_failures("inbound_freshness")
        return

    # Stale. Calculate how stale and alert via ntfy with a 1-hour cooldown
    # so we don't spam every 5 min during a multi-hour outage.
    age_min = int((datetime.now(timezone.utc) - latest).total_seconds() / 60)
    age_str = f"{age_min // 60}h{age_min % 60:02d}m" if age_min >= 60 else f"{age_min}m"
    label = f"INBOUND STALE ({age_str})"

    # Use _failure_counts to drive the cooldown via _send_ntfy's threshold logic.
    _failure_counts["inbound_freshness"] = _failure_counts.get("inbound_freshness", 0) + 1
    _send_ntfy(
        title="QP inbox: no inbound mail",
        message=(
            f"No inbound email received in {age_str} (threshold {threshold_min // 60}h).\n"
            f"Last inbound: {latest.isoformat()}\n"
            f"Check: webhook delivery (Postmark dashboard), Gmail integration health, "
            f"MX records, Cloudflare worker logs."
        ),
        priority="urgent",
        tags="rotating_light,email",
    )
    logger.warning(f"{label} — last inbound {latest.isoformat()}, threshold {threshold_min}m")


async def reconcile_thread_state():
    """Detect and fix denormalized thread fields that have drifted from reality.

    Thread fields like message_count, has_pending, last_message_at,
    last_direction, last_snippet are denormalized for query speed and kept in
    sync by `update_thread_status()` after every mutation. If a code path ever
    forgets to call it (or crashes mid-mutation), the thread silently shows
    stale state in the inbox UI. This job catches and fixes that drift.

    Compares thread.message_count against the actual count for every thread.
    Any mismatch triggers a full update_thread_status recompute on that thread.
    """
    from sqlalchemy import select, func
    from src.core.database import get_db_context
    from src.models.agent_thread import AgentThread
    from src.models.agent_message import AgentMessage
    from src.services.agents.thread_manager import update_thread_status

    async with get_db_context() as db:
        # Pull (thread_id, denorm_count, actual_count) for every thread.
        rows = (await db.execute(
            select(
                AgentThread.id,
                AgentThread.message_count,
                func.count(AgentMessage.id).label("actual"),
            )
            .select_from(AgentThread)
            .outerjoin(AgentMessage, AgentMessage.thread_id == AgentThread.id)
            .group_by(AgentThread.id, AgentThread.message_count)
        )).all()

    drifted = [r.id for r in rows if (r.message_count or 0) != (r.actual or 0)]
    if not drifted:
        return

    logger.warning(f"Thread reconciliation: fixing {len(drifted)} drifted thread(s)")
    for tid in drifted:
        try:
            await update_thread_status(tid)
        except Exception as e:
            logger.warning(f"Thread reconciliation: update_thread_status failed for {tid}: {e}")

    # If we had to fix more than 5 in one pass, something upstream is dropping
    # update_thread_status calls — alert ops to investigate.
    if len(drifted) > 5:
        _send_ntfy(
            title="QP inbox: high thread-state drift",
            message=(
                f"Reconciliation just fixed {len(drifted)} threads with mismatched "
                f"message_count. Something upstream is creating/deleting messages "
                f"without calling update_thread_status. Check recent commits + logs."
            ),
            priority="high",
            tags="warning",
        )


REDIS_HEALTH_CHECK_EVERY = 1  # every cycle = 60s


async def redis_health_probe():
    """Proactive Redis health probe. Resets the cached client if Redis is
    unreachable so the next user-facing op gets a fresh connection attempt
    instead of a stale broken client.

    Without this, a Redis blip would silently break realtime events for
    every connected client until either the backend restarts or someone
    manually resets the cache.
    """
    from src.core.redis_client import redis_health_check
    healthy = await redis_health_check()
    if not healthy:
        # Don't ntfy on every cycle — that would spam if Redis is down.
        # Use _failure_counts so the existing alert-after-N-failures logic
        # gives us a single notification, not 60+ per hour.
        _failure_counts["redis_health"] = _failure_counts.get("redis_health", 0) + 1
        if _failure_counts["redis_health"] == ALERT_THRESHOLD:
            _send_ntfy(
                title="QP Redis: unreachable",
                message=(
                    f"Redis health probe failed {ALERT_THRESHOLD} consecutive times.\n"
                    f"Realtime events are degraded — UI falls back to polling.\n"
                    f"Check: sudo docker ps | grep redis ; sudo docker logs quantumpools-redis"
                ),
                priority="high",
                tags="warning",
            )
    else:
        _clear_failures("redis_health")


async def main():
    logger.info("Background agent service started (monitoring: Sentry + ntfy)")
    logger.info("Inbound email: Postmark webhooks + Gmail incremental sync (every 60s)")
    logger.info(f"Dunning sequence: every {DUNNING_EVERY} min (daily)")
    logger.info(f"Inbound freshness canary: every {INBOUND_FRESHNESS_EVERY} min")
    logger.info(f"Thread state reconciliation: every {RECONCILE_EVERY} min")
    logger.info(f"Redis health probe: every {REDIS_HEALTH_CHECK_EVERY} min")
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

        # --- Redis health probe (every cycle = 60s) ---
        # Self-heals stale Redis clients so realtime events recover quickly
        # after a Redis blip without waiting for a user request to fail.
        try:
            await redis_health_probe()
        except Exception as e:
            _handle_error("redis_health_probe", e)

        # --- Gmail incremental sync (every cycle = 60s) ---
        # Per-integration error handling lives inside this function.
        try:
            await gmail_incremental_sync()
        except Exception as e:
            _handle_error("gmail_incremental_sync", e)

        # --- Estimate reminders (hourly) ---
        if cycle % REMINDER_EVERY == 0:
            try:
                await check_estimate_reminders()
                _clear_failures("estimate_reminders")
            except Exception as e:
                _handle_error("estimate_reminders", e)

        # --- Dunning sequence (daily) — INTENTIONALLY DISABLED ---
        # Code is loaded so Brian can trigger a manual run via
        # POST /v1/billing/dunning/run (with ?dry_run=true to preview).
        # First scheduled run would email the past-due-invoice backlog
        # (~51 Sapphire customers as of 2026-04-28); do not enable auto
        # without reviewing that backlog. To enable: uncomment below.
        # if cycle % DUNNING_EVERY == 0:
        #     try:
        #         await run_dunning_for_all_orgs()
        #         _clear_failures("dunning_sequence")
        #     except Exception as e:
        #         _handle_error("dunning_sequence", e)

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

        # --- Inbound freshness canary (every 5 min) ---
        # System-wide alert if no inbound mail has arrived recently.
        if cycle % INBOUND_FRESHNESS_EVERY == 0:
            try:
                await inbound_freshness_check()
            except Exception as e:
                _handle_error("inbound_freshness_check", e)

        # --- Thread state reconciliation (every 30 min) ---
        # Detects + fixes drift in denormalized thread fields.
        if cycle % RECONCILE_EVERY == 0:
            try:
                await reconcile_thread_state()
                _clear_failures("reconcile_thread_state")
            except Exception as e:
                _handle_error("reconcile_thread_state", e)

        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
