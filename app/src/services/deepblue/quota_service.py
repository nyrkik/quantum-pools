"""DeepBlue quota and rate-limit enforcement."""

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.deepblue_user_usage import DeepBlueUserUsage
from src.models.organization import Organization
from src.core.redis_client import get_redis

logger = logging.getLogger(__name__)


class QuotaExceeded(Exception):
    def __init__(self, reason: str, reset_at: str | None = None):
        self.reason = reason
        self.reset_at = reset_at
        super().__init__(reason)


async def check_rate_limit(org_id: str, user_id: str, limit_per_minute: int) -> None:
    """Redis-backed sliding window rate limit. 60s bucket per user."""
    redis = await get_redis()
    if not redis:
        return  # Fail open if Redis is down — don't block DeepBlue

    key = f"deepblue:rate:{user_id}:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}"
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 65)
        if count > limit_per_minute:
            raise QuotaExceeded(
                f"Rate limit reached ({limit_per_minute} messages/minute). Please wait a moment."
            )
    except QuotaExceeded:
        raise
    except Exception as e:
        logger.warning(f"Rate limit check failed (allowing request): {e}")


async def check_quotas(db: AsyncSession, org_id: str, user_id: str) -> Organization:
    """Check user daily, user monthly, and org monthly quotas. Raises QuotaExceeded if any hit."""
    org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one_or_none()
    if not org:
        raise QuotaExceeded("Organization not found")

    # Rate limit
    await check_rate_limit(org_id, user_id, org.deepblue_rate_limit_per_minute or 30)

    today = date.today()
    month_start = today.replace(day=1)

    # User daily
    user_today = (await db.execute(
        select(DeepBlueUserUsage).where(
            DeepBlueUserUsage.user_id == user_id,
            DeepBlueUserUsage.date == today,
        )
    )).scalar_one_or_none()
    if user_today:
        if user_today.input_tokens >= org.deepblue_user_daily_input_tokens:
            raise QuotaExceeded(
                f"Daily input token limit reached ({org.deepblue_user_daily_input_tokens:,}). Resets at midnight.",
                reset_at="midnight",
            )
        if user_today.output_tokens >= org.deepblue_user_daily_output_tokens:
            raise QuotaExceeded(
                f"Daily output token limit reached ({org.deepblue_user_daily_output_tokens:,}). Resets at midnight.",
                reset_at="midnight",
            )

    # User monthly
    user_month = (await db.execute(
        select(
            func.coalesce(func.sum(DeepBlueUserUsage.input_tokens), 0),
            func.coalesce(func.sum(DeepBlueUserUsage.output_tokens), 0),
        ).where(
            DeepBlueUserUsage.user_id == user_id,
            DeepBlueUserUsage.date >= month_start,
        )
    )).one()
    if user_month[0] >= org.deepblue_user_monthly_input_tokens:
        raise QuotaExceeded(
            f"Monthly input token limit reached ({org.deepblue_user_monthly_input_tokens:,}). Contact your admin."
        )
    if user_month[1] >= org.deepblue_user_monthly_output_tokens:
        raise QuotaExceeded(
            f"Monthly output token limit reached ({org.deepblue_user_monthly_output_tokens:,}). Contact your admin."
        )

    # Org monthly
    org_month = (await db.execute(
        select(
            func.coalesce(func.sum(DeepBlueUserUsage.input_tokens), 0),
            func.coalesce(func.sum(DeepBlueUserUsage.output_tokens), 0),
        ).where(
            DeepBlueUserUsage.organization_id == org_id,
            DeepBlueUserUsage.date >= month_start,
        )
    )).one()
    if org_month[0] >= org.deepblue_org_monthly_input_tokens:
        raise QuotaExceeded(
            f"Organization monthly input budget exhausted. The owner can adjust this in Settings."
        )
    if org_month[1] >= org.deepblue_org_monthly_output_tokens:
        raise QuotaExceeded(
            f"Organization monthly output budget exhausted. The owner can adjust this in Settings."
        )

    return org


async def record_usage(
    db: AsyncSession,
    org_id: str,
    user_id: str,
    input_tokens: int,
    output_tokens: int,
    tool_count: int = 0,
    off_topic: bool = False,
) -> None:
    """Upsert today's usage row for this user."""
    today = date.today()

    existing = (await db.execute(
        select(DeepBlueUserUsage).where(
            DeepBlueUserUsage.user_id == user_id,
            DeepBlueUserUsage.date == today,
        )
    )).scalar_one_or_none()

    if existing:
        existing.message_count += 1
        existing.input_tokens += input_tokens
        existing.output_tokens += output_tokens
        existing.tool_calls_count += tool_count
        if off_topic:
            existing.off_topic_count += 1
        existing.updated_at = datetime.now(timezone.utc)
    else:
        row = DeepBlueUserUsage(
            organization_id=org_id,
            user_id=user_id,
            date=today,
            message_count=1,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tool_calls_count=tool_count,
            off_topic_count=1 if off_topic else 0,
        )
        db.add(row)
