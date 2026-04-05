"""DeepBlue Field conversation persistence."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, Integer, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


class DeepBlueConversation(Base):
    __tablename__ = "deepblue_conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    # Page context at time of conversation
    context_json: Mapped[str] = mapped_column(Text, default="{}")  # {customer_id, property_id, bow_id, visit_id}
    title: Mapped[str | None] = mapped_column(String(200))  # Auto-generated from first message

    # Conversation messages stored as JSON array
    # [{role: "user"|"assistant", content: str, tool_calls?: [...], tool_results?: [...], timestamp: iso}]
    messages_json: Mapped[str] = mapped_column(Text, default="[]")

    # Case linkage — persistent conversations attached to a service case
    case_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("service_cases.id", ondelete="SET NULL"), nullable=True, index=True,
    )

    # Conversation management
    visibility: Mapped[str] = mapped_column(String(20), default="private")  # private | shared | case
    pinned: Mapped[bool] = mapped_column(default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    shared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    shared_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Cost tracking
    model_tier: Mapped[str] = mapped_column(String(20), default="fast")  # fast (haiku) or standard (sonnet)
    total_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_output_tokens: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
