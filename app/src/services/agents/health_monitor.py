"""Agent health monitoring — threshold-based alerting.

Runs periodically (via cron or manual trigger), checks recent agent logs against
thresholds, and fires in-app notifications to org owners/admins when metrics degrade.

FUTURE: anomaly detection (plan-agent-anomaly-detection.md in memory) — replace
static thresholds with baseline comparison + pattern detection for smarter alerts.
"""

import json
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.notification import Notification
from src.models.organization import Organization
from src.models.organization_user import OrganizationUser
from src.services.agents.observability import AgentLog

logger = logging.getLogger(__name__)

# Thresholds (org-wide; per-agent checks are stricter)
THRESHOLD_SUCCESS_RATE = 90  # percent
THRESHOLD_HOURLY_FAILURES = 5  # total failures in last hour
THRESHOLD_PER_AGENT_HOURLY_FAILURES = 3  # per-agent failures in last hour

# Deduplication — don't re-alert within this window for the same issue
DEDUP_WINDOW_MINUTES = 60


async def check_org_health(db: AsyncSession, org_id: str) -> dict:
    """Run health checks on one organization. Returns dict of issues found."""
    now = datetime.now(timezone.utc)
    hour_ago = now - timedelta(hours=1)
    day_ago = now - timedelta(hours=24)

    issues = []

    # 1. 24h success rate
    total_24h = (await db.execute(
        select(func.count(AgentLog.id)).where(
            AgentLog.organization_id == org_id,
            AgentLog.created_at >= day_ago,
        )
    )).scalar() or 0

    if total_24h > 10:  # need enough volume to matter
        failures_24h = (await db.execute(
            select(func.count(AgentLog.id)).where(
                AgentLog.organization_id == org_id,
                AgentLog.created_at >= day_ago,
                AgentLog.success == False,
            )
        )).scalar() or 0
        success_rate = round(100 * (total_24h - failures_24h) / total_24h, 1)
        if success_rate < THRESHOLD_SUCCESS_RATE:
            issues.append({
                "severity": "high",
                "type": "success_rate_low",
                "title": f"Agent success rate dropped to {success_rate}%",
                "body": f"{failures_24h} of {total_24h} agent calls failed in the last 24 hours. Check the admin dashboard for details.",
                "dedup_key": f"success_rate_low_{int(success_rate)}",
            })

    # 2. Per-agent failure spikes in last hour
    per_agent_failures = (await db.execute(
        select(AgentLog.agent_name, func.count(AgentLog.id).label("fail_count"))
        .where(
            AgentLog.organization_id == org_id,
            AgentLog.created_at >= hour_ago,
            AgentLog.success == False,
        )
        .group_by(AgentLog.agent_name)
        .having(func.count(AgentLog.id) >= THRESHOLD_PER_AGENT_HOURLY_FAILURES)
    )).all()

    for agent_name, fail_count in per_agent_failures:
        # Get a sample error message
        sample_error = (await db.execute(
            select(AgentLog.error).where(
                AgentLog.organization_id == org_id,
                AgentLog.agent_name == agent_name,
                AgentLog.success == False,
                AgentLog.created_at >= hour_ago,
            ).order_by(AgentLog.created_at.desc()).limit(1)
        )).scalar()

        clean_name = agent_name.replace("_", " ").title()
        issues.append({
            "severity": "high",
            "type": "agent_failures",
            "title": f"{clean_name} failing ({fail_count} errors in last hour)",
            "body": f"Last error: {(sample_error or 'unknown')[:200]}" if sample_error else "Check the admin dashboard for details.",
            "dedup_key": f"agent_failures_{agent_name}",
        })

    # 3. Total failure spike org-wide
    total_failures_hour = (await db.execute(
        select(func.count(AgentLog.id)).where(
            AgentLog.organization_id == org_id,
            AgentLog.created_at >= hour_ago,
            AgentLog.success == False,
        )
    )).scalar() or 0

    if total_failures_hour >= THRESHOLD_HOURLY_FAILURES * 2:
        issues.append({
            "severity": "critical",
            "type": "failure_spike",
            "title": f"Agent failure spike: {total_failures_hour} errors in last hour",
            "body": "Multiple agents failing. Check the admin dashboard to investigate.",
            "dedup_key": "failure_spike",
        })

    return {"org_id": org_id, "issues": issues, "checked_at": now.isoformat()}


async def fire_alerts(db: AsyncSession, org_id: str, issues: list[dict]) -> int:
    """Create notifications for org owners/admins for each issue, with dedup."""
    if not issues:
        return 0

    now = datetime.now(timezone.utc)
    dedup_cutoff = now - timedelta(minutes=DEDUP_WINDOW_MINUTES)

    # Get org owners/admins to notify
    recipients = (await db.execute(
        select(OrganizationUser).where(
            OrganizationUser.organization_id == org_id,
            OrganizationUser.role.in_(("owner", "admin")),
            OrganizationUser.is_active == True,
        )
    )).scalars().all()

    if not recipients:
        return 0

    notifications_created = 0

    for issue in issues:
        dedup_key = issue.get("dedup_key", issue["title"])
        # Check if a similar notification was created recently for ANY user in this org
        existing = (await db.execute(
            select(func.count(Notification.id)).where(
                Notification.organization_id == org_id,
                Notification.type == "agent_health",
                Notification.title == issue["title"],
                Notification.created_at >= dedup_cutoff,
            )
        )).scalar() or 0

        if existing > 0:
            logger.info(f"Skipping dup agent_health alert: {issue['title']}")
            continue

        for ou in recipients:
            db.add(Notification(
                organization_id=org_id,
                user_id=ou.user_id,
                type="agent_health",
                title=issue["title"],
                body=issue["body"],
                link="/admin",
            ))
            notifications_created += 1

    await db.commit()
    return notifications_created


async def run_health_check_all_orgs(db: AsyncSession) -> dict:
    """Check health across all active orgs. Returns summary."""
    orgs = (await db.execute(
        select(Organization).where(Organization.is_active == True)
    )).scalars().all()

    total_issues = 0
    total_notifications = 0

    for org in orgs:
        try:
            result = await check_org_health(db, org.id)
            issues = result["issues"]
            if issues:
                total_issues += len(issues)
                created = await fire_alerts(db, org.id, issues)
                total_notifications += created
                logger.info(f"Org {org.name}: {len(issues)} issues, {created} notifications created")
        except Exception as e:
            logger.error(f"Health check failed for org {org.id}: {e}")

    return {
        "orgs_checked": len(orgs),
        "total_issues": total_issues,
        "total_notifications_created": total_notifications,
    }
