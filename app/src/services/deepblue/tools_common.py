"""DeepBlue tools — shared types and constants."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ToolContext:
    db: AsyncSession
    org_id: str
    customer_id: str | None = None
    property_id: str | None = None
    bow_id: str | None = None
    visit_id: str | None = None
    # Per-turn counters to prevent runaway tool loops
    parts_search_count: int = 0


MAX_PARTS_SEARCHES_PER_TURN = 3
