#!/usr/bin/env python3
"""Email health check — runs every 10 minutes via cron.

Checks:
1. Agent background service is running
2. Postmark API is reachable and sending works
3. Webhook endpoint is responding
4. No outbound emails stuck in queued status
5. Backend API is healthy

Sends alerts via ntfy (primary) and Postmark email (secondary).
"""

import asyncio
import logging
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

NOTIFICATION_EMAIL = os.environ.get("NOTIFICATION_EMAIL", "")
POSTMARK_TOKEN = os.environ.get("POSTMARK_SERVER_TOKEN", "")
NTFY_URL = os.environ.get("NTFY_URL", "http://localhost:7031")
NTFY_TOPIC = "qp-alerts"
ALERT_FILE = Path("/tmp/qp_email_health_last_alert")
ALERT_COOLDOWN = 1800  # 30 min between alerts


def should_alert() -> bool:
    """Rate limit alerts."""
    if ALERT_FILE.exists():
        last = float(ALERT_FILE.read_text().strip())
        if (datetime.now().timestamp() - last) < ALERT_COOLDOWN:
            return False
    return True


def send_ntfy_alert(subject: str, body: str):
    """Send alert via ntfy push notification."""
    try:
        req = urllib.request.Request(
            f"{NTFY_URL}/{NTFY_TOPIC}",
            data=body.encode(),
            headers={"Title": f"QP Health: {subject}", "Priority": "high", "Tags": "warning"},
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        logger.error(f"ntfy alert failed: {e}")


def send_email_alert(subject: str, body: str):
    """Send alert via Postmark (not Gmail SMTP)."""
    if not NOTIFICATION_EMAIL or not POSTMARK_TOKEN:
        return
    import json
    try:
        from_email = os.environ.get("AGENT_FROM_EMAIL", "noreply@quantumpoolspro.com")
        data = json.dumps({
            "From": from_email,
            "To": NOTIFICATION_EMAIL,
            "Subject": f"QP Email Health: {subject}",
            "TextBody": body,
            "MessageStream": "outbound",
        }).encode()
        req = urllib.request.Request(
            "https://api.postmarkapp.com/email",
            data=data,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Postmark-Server-Token": POSTMARK_TOKEN,
            },
        )
        urllib.request.urlopen(req, timeout=10)
        logger.info(f"Email alert sent: {subject}")
    except Exception as e:
        logger.error(f"Email alert failed: {e}")


def send_alert(subject: str, body: str):
    """Send alert via ntfy (primary) and email (secondary)."""
    if not should_alert():
        logger.info(f"Alert suppressed (cooldown): {subject}")
        return
    send_ntfy_alert(subject, body)
    send_email_alert(subject, body)
    ALERT_FILE.write_text(str(datetime.now().timestamp()))


def check_agent_service() -> list[str]:
    """Check if agent background service is active and healthy."""
    import subprocess
    issues = []

    result = subprocess.run(
        ["systemctl", "is-active", "quantumpools-agent"],
        capture_output=True, text=True
    )
    if result.stdout.strip() != "active":
        issues.append("Agent background service is NOT running")
        return issues

    # Check for recent activity
    result = subprocess.run(
        ["journalctl", "-u", "quantumpools-agent", "--since", "5 min ago", "--no-pager", "-q"],
        capture_output=True, text=True
    )
    if not result.stdout.strip():
        issues.append("Agent service has no log output in the last 5 minutes — may be hung")

    # Check for error loops
    lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
    error_lines = [l for l in lines if " ERROR " in l or "Error" in l or "Exception" in l or "Traceback" in l]
    if len(error_lines) >= 3:
        issues.append(f"Agent service has {len(error_lines)} errors in last 5 min: {error_lines[-1][:200]}")
        # Detect same-error loops
        msgs = []
        for l in error_lines:
            if " ERROR " in l:
                msgs.append(l.split(" ERROR ", 1)[-1][:80])
        if msgs and len(set(msgs)) == 1:
            issues.append(f"Agent service stuck in error loop: {msgs[0]}")

    return issues


def check_postmark_api() -> list[str]:
    """Verify Postmark API is reachable."""
    issues = []
    if not POSTMARK_TOKEN:
        issues.append("POSTMARK_SERVER_TOKEN not configured")
        return issues
    try:
        req = urllib.request.Request(
            "https://api.postmarkapp.com/server",
            headers={
                "Accept": "application/json",
                "X-Postmark-Server-Token": POSTMARK_TOKEN,
            },
        )
        resp = urllib.request.urlopen(req, timeout=10)
        if resp.status != 200:
            issues.append(f"Postmark API returned {resp.status}")
    except Exception as e:
        issues.append(f"Postmark API unreachable: {e}")
    return issues


def check_webhook_endpoint() -> list[str]:
    """Verify webhook endpoint is responding."""
    issues = []
    try:
        req = urllib.request.Request(
            "http://localhost:7061/api/v1/inbound-email/webhook/sapphire",
            method="HEAD",
        )
        resp = urllib.request.urlopen(req, timeout=10)
        if resp.status not in (200, 405):  # 405 = method not allowed (POST only) is fine
            issues.append(f"Webhook endpoint returned {resp.status}")
    except Exception as e:
        issues.append(f"Webhook endpoint unreachable: {e}")
    return issues


async def check_queued_emails() -> list[str]:
    """Check for outbound emails stuck in queued status."""
    from sqlalchemy import select, func
    from src.core.database import get_session_maker
    from src.models.agent_message import AgentMessage

    issues = []
    try:
        sm = get_session_maker()
        async with sm() as db:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
            count = (await db.execute(
                select(func.count(AgentMessage.id)).where(
                    AgentMessage.status == "queued",
                    AgentMessage.received_at < cutoff,
                )
            )).scalar() or 0
            if count > 0:
                issues.append(f"{count} outbound email(s) stuck in 'queued' status for >10 min")

            # Check for recent bounces
            bounced = (await db.execute(
                select(func.count(AgentMessage.id)).where(
                    AgentMessage.status == "bounced",
                    AgentMessage.received_at > cutoff,
                )
            )).scalar() or 0
            if bounced > 0:
                issues.append(f"{bounced} email(s) bounced in last 10 min")

            # Check for failed sends
            failed = (await db.execute(
                select(func.count(AgentMessage.id)).where(
                    AgentMessage.status == "failed",
                    AgentMessage.received_at > cutoff,
                )
            )).scalar() or 0
            if failed > 0:
                issues.append(f"{failed} outbound email(s) failed to send in last 10 min")
    except Exception as e:
        issues.append(f"Database check failed: {e}")
    return issues


async def check_backend_health() -> list[str]:
    """Check backend API is responding."""
    import subprocess
    issues = []
    result = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
         "http://localhost:7061/api/v1/auth/me"],
        capture_output=True, text=True, timeout=10
    )
    code = result.stdout.strip()
    if code != "401":
        issues.append(f"Backend API returned {code} (expected 401)")

    # Check for recent 500s
    result = subprocess.run(
        ["journalctl", "-u", "quantumpools-backend", "--since", "10 min ago", "--no-pager", "-q"],
        capture_output=True, text=True
    )
    lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
    errors_500 = [l for l in lines if "500 Internal Server Error" in l]
    if len(errors_500) >= 3:
        issues.append(f"{len(errors_500)} API 500 errors in last 10 min")

    return issues


async def main():
    all_issues = []

    all_issues.extend(check_agent_service())
    all_issues.extend(check_postmark_api())
    all_issues.extend(check_webhook_endpoint())
    all_issues.extend(await check_queued_emails())
    all_issues.extend(await check_backend_health())

    if all_issues:
        body = "Email system health check FAILED:\n\n"
        for issue in all_issues:
            body += f"  - {issue}\n"
        body += f"\nTimestamp: {datetime.now().isoformat()}"
        body += "\nCheck: sudo journalctl -u quantumpools-agent -f"
        body += "\nCheck: sudo journalctl -u quantumpools-backend -f"

        logger.error(f"Health check failed: {len(all_issues)} issue(s)")
        for issue in all_issues:
            logger.error(f"  {issue}")

        send_alert(f"{len(all_issues)} issue(s) detected", body)
    else:
        logger.info("All checks passed")


if __name__ == "__main__":
    asyncio.run(main())
