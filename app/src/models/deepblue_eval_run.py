"""DeepBlue eval run history — tracks tool selection accuracy over time."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


class DeepBlueEvalRun(Base):
    __tablename__ = "deepblue_eval_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    run_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )

    total: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)

    model_used: Mapped[str | None] = mapped_column(String(100))
    system_prompt_hash: Mapped[str | None] = mapped_column(String(32))
    results_json: Mapped[str] = mapped_column(Text)  # full per-prompt breakdown

    notes: Mapped[str | None] = mapped_column(Text)  # optional human notes
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True,
    )
