"""Inbox routing rule matching service."""

import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.inbox_routing_rule import InboxRoutingRule

logger = logging.getLogger(__name__)


async def match_routing_rule(
    db: AsyncSession,
    org_id: str,
    delivered_to: str,
) -> InboxRoutingRule | None:
    """Match an email address against active routing rules.

    Rules are evaluated in priority order (lower = first). First match wins.
    Returns None if no rule matches.
    """
    if not delivered_to:
        return None

    addr = delivered_to.lower().strip()

    result = await db.execute(
        select(InboxRoutingRule)
        .where(
            InboxRoutingRule.organization_id == org_id,
            InboxRoutingRule.is_active == True,
        )
        .order_by(InboxRoutingRule.priority)
    )
    rules = result.scalars().all()

    for rule in rules:
        pattern = rule.address_pattern.lower().strip()
        if rule.match_type == "exact":
            if addr == pattern:
                return rule
        elif rule.match_type == "contains":
            if pattern in addr:
                return rule

    return None


def extract_delivered_to(msg) -> str | None:
    """Extract the Delivered-To address from an email message.

    Falls back to parsing org addresses from To/Cc headers.
    """
    from src.services.agents.mail_agent import decode_email_header
    import re

    # Primary: Delivered-To header (most reliable for Gmail aliases)
    delivered_to = msg.get("Delivered-To", "")
    if delivered_to:
        delivered_to = decode_email_header(delivered_to).strip()
        # Extract just the email address
        match = re.search(r"<(.+?)>", delivered_to)
        if match:
            return match.group(1).lower()
        if "@" in delivered_to:
            return delivered_to.lower()

    # Fallback: parse To header for org addresses
    to_header = decode_email_header(msg.get("To", ""))
    if to_header:
        addresses = re.findall(r'[\w.+-]+@[\w.-]+', to_header)
        for addr in addresses:
            return addr.lower()

    return None
