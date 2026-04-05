"""DeepBlue retention + monthly usage rollup.

Policy:
- Soft-delete private unpinned non-case conversations after 90 days inactive
- Hard-delete soft-deleted conversations after 30 more days (120 total)
- Before hard delete, roll up usage into deepblue_usage_monthly
- Delete message logs older than 90 days
- Delete knowledge gaps older than 90 days
"""

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Haiku pricing (approximate, for cost estimation during rollup)
HAIKU_INPUT_PER_M = 0.80
HAIKU_OUTPUT_PER_M = 4.00


async def run_retention_cleanup(db: AsyncSession) -> dict:
    """Run all cleanup tasks. Returns counts of affected rows."""
    from src.models.deepblue_conversation import DeepBlueConversation
    from src.models.deepblue_message_log import DeepBlueMessageLog
    from src.models.deepblue_knowledge_gap import DeepBlueKnowledgeGap

    now = datetime.now(timezone.utc)
    soft_delete_cutoff = now - timedelta(days=90)
    hard_delete_cutoff = now - timedelta(days=30)  # from soft-delete timestamp
    log_cutoff = now - timedelta(days=90)

    counts = {
        "soft_deleted": 0,
        "hard_deleted": 0,
        "logs_purged": 0,
        "gaps_purged": 0,
        "rolled_up": 0,
    }

    # 1. Soft-delete stale private conversations
    stale = (await db.execute(
        select(DeepBlueConversation).where(
            DeepBlueConversation.visibility == "private",
            DeepBlueConversation.pinned == False,
            DeepBlueConversation.case_id.is_(None),
            DeepBlueConversation.deleted_at.is_(None),
            DeepBlueConversation.updated_at < soft_delete_cutoff,
        )
    )).scalars().all()
    for c in stale:
        c.deleted_at = now
        counts["soft_deleted"] += 1

    # 2. Hard-delete soft-deleted past retention window, rolling up first
    to_hard_delete = (await db.execute(
        select(DeepBlueConversation).where(
            DeepBlueConversation.deleted_at.isnot(None),
            DeepBlueConversation.deleted_at < hard_delete_cutoff,
        )
    )).scalars().all()

    for conv in to_hard_delete:
        await _rollup_to_monthly(db, conv)
        counts["rolled_up"] += 1
        await db.delete(conv)
        counts["hard_deleted"] += 1

    # 3. Purge old message logs
    result = await db.execute(
        delete(DeepBlueMessageLog).where(DeepBlueMessageLog.created_at < log_cutoff)
    )
    counts["logs_purged"] = result.rowcount or 0

    # 4. Purge old knowledge gaps
    result = await db.execute(
        delete(DeepBlueKnowledgeGap).where(DeepBlueKnowledgeGap.created_at < log_cutoff)
    )
    counts["gaps_purged"] = result.rowcount or 0

    await db.commit()
    logger.info(f"DeepBlue retention cleanup: {counts}")
    return counts


async def _rollup_to_monthly(db: AsyncSession, conv) -> None:
    """Aggregate a conversation's usage into deepblue_usage_monthly before deletion."""
    from src.models.deepblue_usage_monthly import DeepBlueUsageMonthly  # will create below

    created = conv.created_at
    year = created.year
    month = created.month

    # Find or create monthly row
    existing = (await db.execute(
        select(DeepBlueUsageMonthly).where(
            DeepBlueUsageMonthly.organization_id == conv.organization_id,
            DeepBlueUsageMonthly.user_id == conv.user_id,
            DeepBlueUsageMonthly.year == year,
            DeepBlueUsageMonthly.month == month,
        )
    )).scalar_one_or_none()

    import json as _json
    message_count = len(_json.loads(conv.messages_json or "[]"))

    cost_est = (
        conv.total_input_tokens * HAIKU_INPUT_PER_M / 1_000_000
        + conv.total_output_tokens * HAIKU_OUTPUT_PER_M / 1_000_000
    )

    if existing:
        existing.conversations_created += 1
        existing.messages_sent += message_count
        existing.total_input_tokens += conv.total_input_tokens
        existing.total_output_tokens += conv.total_output_tokens
        existing.total_cost_usd_estimated = float(existing.total_cost_usd_estimated or 0) + cost_est
    else:
        db.add(DeepBlueUsageMonthly(
            organization_id=conv.organization_id,
            user_id=conv.user_id,
            year=year,
            month=month,
            conversations_created=1,
            messages_sent=message_count,
            total_input_tokens=conv.total_input_tokens,
            total_output_tokens=conv.total_output_tokens,
            total_cost_usd_estimated=cost_est,
        ))
