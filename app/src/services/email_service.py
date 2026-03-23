"""Email service — sends notifications via SMTP."""

import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import aiosmtplib
from src.core.config import Settings

logger = logging.getLogger(__name__)
settings = Settings()


async def send_email(to: str, subject: str, body_text: str, body_html: str | None = None) -> bool:
    """Send an email. Returns True on success."""
    if not settings.smtp_host or not settings.smtp_user:
        logger.warning("SMTP not configured — skipping email")
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body_text, "plain"))
    if body_html:
        msg.attach(MIMEText(body_html, "html"))

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            start_tls=True,
        )
        logger.info(f"Email sent to {to}: {subject}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to}: {e}")
        return False


async def send_scraper_alert(found: int, new: int, pdfs: int, errors: list[str], duration: float, scrape_dates: list[str] | None = None):
    """Send EMD scraper run summary to notification email."""
    to = settings.notification_email
    if not to:
        logger.warning("No notification email configured")
        return False

    from datetime import date as date_type
    today = date_type.today().strftime("%b %d, %Y")
    date_range = " & ".join(scrape_dates) if scrape_dates else today
    status = "completed" if not errors else f"completed with {len(errors)} errors"
    subject = f"EMD Scraper {today}: {new} new, {found} on portal" if found else f"EMD Scraper {today}: no inspections on portal"

    body = f"""EMD Scraper Run — {date_range}
─────────────────────
Status: {status}
Duration: {duration:.0f}s

On portal: {found}
New to our database: {new}
PDFs on file: {pdfs}
"""
    if errors:
        body += f"\nErrors:\n" + "\n".join(f"  • {e}" for e in errors[:10])
        if len(errors) > 10:
            body += f"\n  ... and {len(errors) - 10} more"

    return await send_email(to, subject, body)
