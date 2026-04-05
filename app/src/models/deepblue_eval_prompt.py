"""DeepBlue eval prompt — DB-backed test cases for the living eval suite."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


class DeepBlueEvalPrompt(Base):
    __tablename__ = "deepblue_eval_prompts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    prompt_key: Mapped[str] = mapped_column(String(100), nullable=False)  # slug for stable tracking
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)

    source: Mapped[str] = mapped_column(String(30), default="manual")  # static | knowledge_gap | ai_generated | manual
    max_turns: Mapped[int] = mapped_column(Integer, default=1)

    # Expected behavior — all JSON-encoded strings
    expected_tools: Mapped[str | None] = mapped_column(Text)  # JSON array — all must be called
    expected_tools_any: Mapped[str | None] = mapped_column(Text)  # JSON array — at least one must be called
    expected_off_topic: Mapped[bool] = mapped_column(Boolean, default=False)
    expected_no_tools_required: Mapped[bool] = mapped_column(Boolean, default=False)
    must_not_contain: Mapped[str | None] = mapped_column(Text)  # JSON array of forbidden phrases

    active: Mapped[bool] = mapped_column(Boolean, default=True)
    consecutive_passes: Mapped[int] = mapped_column(Integer, default=0)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_passed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # For AI-generated or knowledge-gap sourced prompts
    reasoning: Mapped[str | None] = mapped_column(Text)  # why this prompt was added
    source_id: Mapped[str | None] = mapped_column(String(36))  # e.g. knowledge_gap.id

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
