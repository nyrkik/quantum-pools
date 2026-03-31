"""AgentCorrection — captures every human correction to AI output for learning."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


class AgentCorrection(Base):
    __tablename__ = "agent_corrections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    agent_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # email_classifier, email_drafter, deepblue_responder, command_executor,
    # job_evaluator, estimate_generator, customer_matcher, equipment_resolver

    correction_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # "edit", "rejection", "acceptance"

    category: Mapped[str | None] = mapped_column(String(50), index=True)
    # email category, job type, equipment type — for relevance matching

    customer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("customers.id", ondelete="SET NULL"), index=True)

    input_context: Mapped[str | None] = mapped_column(Text)  # what the agent saw (truncated)
    original_output: Mapped[str | None] = mapped_column(Text)  # what the agent produced
    corrected_output: Mapped[str | None] = mapped_column(Text)  # what the human changed it to (null = rejection)

    source_id: Mapped[str | None] = mapped_column(String(36))  # FK to message, action, equipment_item, etc.
    source_type: Mapped[str | None] = mapped_column(String(30))  # "agent_message", "agent_action", "equipment_item"

    applied_count: Mapped[int] = mapped_column(Integer, default=0)  # how many times this correction was injected into a prompt
    last_applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
