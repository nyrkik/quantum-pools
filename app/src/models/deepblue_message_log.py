"""DeepBlue per-message log — anomaly detection foundation."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


class DeepBlueMessageLog(Base):
    __tablename__ = "deepblue_message_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    message_index: Mapped[int] = mapped_column(Integer, default=0)  # position in conversation

    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)

    tool_calls_made: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array of tool names
    tool_count: Mapped[int] = mapped_column(Integer, default=0)

    user_prompt_hash: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    user_prompt_length: Mapped[int] = mapped_column(Integer, default=0)
    response_length: Mapped[int] = mapped_column(Integer, default=0)

    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category: Mapped[str] = mapped_column(String(30), default="unknown", index=True)  # pool_service | business_ops | off_topic | unknown
    off_topic_detected: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    model_used: Mapped[str] = mapped_column(String(20), default="fast")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
