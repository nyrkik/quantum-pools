"""PlatformEvent — the unified event stream.

**Note**: the production table is declarative-partitioned by RANGE(created_at).
This SQLAlchemy model represents the logical row shape; partitioning lives
in the Alembic migration (`7cc81fcba9da_platform_events_phase1.py`).

`PlatformEventService.emit()` writes via raw SQL, NOT through this ORM
model. The model exists primarily so:

  1. `Base.metadata.create_all` in tests creates a plain (non-partitioned)
     platform_events table — tests don't need partitioning.
  2. TRUNCATE-between-tests machinery in conftest picks up the table.

See docs/event-taxonomy.md for the canonical field contract and
docs/ai-platform-phase-1.md §4 for production schema rationale.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class PlatformEvent(Base):
    __tablename__ = "platform_events"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    organization_id: Mapped[str | None] = mapped_column(String(36))
    actor_user_id: Mapped[str | None] = mapped_column(String(36))
    acting_as_user_id: Mapped[str | None] = mapped_column(String(36))
    view_as_role: Mapped[str | None] = mapped_column(String(30))
    actor_type: Mapped[str] = mapped_column(String(10), nullable=False)
    actor_agent_type: Mapped[str | None] = mapped_column(String(50))
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_refs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    request_id: Mapped[str | None] = mapped_column(String(36))
    session_id: Mapped[str | None] = mapped_column(String(36))
    job_run_id: Mapped[str | None] = mapped_column(String(36))
    client_emit_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        primary_key=True,  # composite PK — part of the partition key in prod
    )


class DataDeletionRequest(Base):
    __tablename__ = "data_deletion_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    requested_by_user_id: Mapped[str | None] = mapped_column(String(36))
    target_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    target_type: Mapped[str] = mapped_column(String(30), nullable=False)
    scope: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_rows_affected: Mapped[int | None] = mapped_column()
    note: Mapped[str | None] = mapped_column()
