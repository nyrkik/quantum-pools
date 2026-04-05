"""DeepBlue knowledge gap — records queries that needed the meta-tool or went unanswered."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


class DeepBlueKnowledgeGap(Base):
    __tablename__ = "deepblue_knowledge_gaps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    user_question: Mapped[str] = mapped_column(Text, nullable=False)
    # meta_tool | unresolved
    resolution: Mapped[str] = mapped_column(String(20), nullable=False)
    sql_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Once reviewed by admin
    reviewed: Mapped[bool] = mapped_column(default=False)
    promoted_to_tool: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
