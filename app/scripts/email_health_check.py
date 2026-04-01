#!/usr/bin/env python3
"""Email health check — runs every 10 minutes via cron.

Checks:
1. Agent poller is running and has polled recently
2. No stuck pending emails in Gmail (ingested but not recorded)
3. No outbound emails stuck in queued status
4. SMTP credentials are working

Sends alert email on failure. Uses direct SMTP (not the app) so it works
even if the app is broken.
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

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

NOTIFICATION_EMAIL = os.environ.get("NOTIFICATION_EMAIL", "")
GMAIL_USER = os.environ.get("AGENT_GMAIL_USER", "")
GMAIL_PASS = os.environ.get("AGENT_GMAIL_PASSWORD", "")
ALERT_FILE = Path("/tmp/qp_email_health_last_alert")
ALERT_COOLDOWN = 1800  # 30 min between alerts


def should_alert() -> bool:
    """Rate limit alerts."""
    if ALERT_FILE.exists():
        last = float(ALERT_FILE.read_text().strip())
        if (datetime.now().timestamp() - last) < ALERT_COOLDOWN:
            return False
    return True


def send_alert(subject: str, body: str):
    """Send alert via direct SMTP (bypasses app entirely)."""
    if not NOTIFICATION_EMAIL or not GMAIL_USER or not GMAIL_PASS:
        logger.error(f"Cannot send alert — missing credentials. Subject: {subject}")
        return
    if not should_alert():
        logger.info(f"Alert suppressed (cooldown): {subject}")
        return

    try:
        msg = MIMEText(body)
        msg["Subject"] = f"⚠ QP Email Health: {subject}"
        msg["From"] = GMAIL_USER
        msg["To"] = NOTIFICATION_EMAIL

        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.starttls()
            s.login(GMAIL_USER, GMAIL_PASS)
            s.send_message(msg)

        ALERT_FILE.write_text(str(datetime.now().timestamp()))
        logger.info(f"Alert sent: {subject}")
    except Exception as e:
        logger.error(f"Failed to send alert: {e}")


def check_poller_running() -> list[str]:
    """Check if agent poller service is active and has logged recently."""
    import subprocess
    issues = []

    # Check systemd status
    result = subprocess.run(
        ["systemctl", "is-active", "quantumpools-agent"],
        capture_output=True, text=True
    )
    if result.stdout.strip() != "active":
        issues.append("Agent poller service is NOT running")
        return issues

    # Check for recent activity (should log every 60s)
    result = subprocess.run(
        ["journalctl", "-u", "quantumpools-agent", "--since", "5 min ago", "--no-pager", "-q"],
        capture_output=True, text=True
    )
    if not result.stdout.strip():
        issues.append("Agent poller has no log output in the last 5 minutes — may be hung")

    # Check for recent errors
    lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
    error_lines = [l for l in lines if "Error" in l or "Exception" in l or "Traceback" in l]
    if len(error_lines) >= 3:
        issues.append(f"Agent poller has {len(error_lines)} errors in last 5 min: {error_lines[-1][:120]}")

    return issues


def check_gmail_connectivity() -> list[str]:
    """Verify we can connect to Gmail IMAP."""
    issues = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_USER, GMAIL_PASS)
        mail.select("INBOX")
        mail.logout()
    except Exception as e:
        issues.append(f"Gmail IMAP connection failed: {e}")
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


async def send_in_app_alert(issues: list[str]):
    """Create in-app notification for owner/admin users."""
    try:
        from src.core.database import get_session_maker
        from src.models.notification import Notification
        from src.models.organization_user import OrganizationUser
        from sqlalchemy import select

        sm = get_session_maker()
        async with sm() as db:
            # Notify all owners and admins
            result = await db.execute(
                select(OrganizationUser).where(
                    OrganizationUser.role.in_(("owner", "admin"))
                )
            )
            org_users = result.scalars().all()

            summary = "; ".join(issues)[:200]
            for ou in org_users:
                db.add(Notification(
                    organization_id=ou.organization_id,
                    user_id=ou.user_id,
                    type="system_alert",
                    title="Email system issue detected",
                    body=summary,
                    link="/settings",
                ))
            await db.commit()
            logger.info(f"In-app alert sent to {len(org_users)} user(s)")
    except Exception as e:
        logger.error(f"Failed to send in-app alert: {e}")


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

    # Run all checks
    all_issues.extend(check_poller_running())
    all_issues.extend(check_gmail_connectivity())
    all_issues.extend(await check_queued_emails())
    all_issues.extend(await check_backend_health())

    if all_issues:
        body = "Email system health check FAILED:\n\n"
        for issue in all_issues:
            body += f"  • {issue}\n"
        body += f"\nTimestamp: {datetime.now().isoformat()}"
        body += "\nCheck: sudo journalctl -u quantumpools-agent -f"
        body += "\nCheck: sudo journalctl -u quantumpools-backend -f"

        logger.error(f"Health check failed: {len(all_issues)} issue(s)")
        for issue in all_issues:
            logger.error(f"  {issue}")

        send_alert(f"{len(all_issues)} issue(s) detected", body)
        await send_in_app_alert(all_issues)
    else:
        logger.info("All checks passed")


if __name__ == "__main__":
    asyncio.run(main())
