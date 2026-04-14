"""ServiceCase — groups all work for a single customer issue.

A case is the parent entity for jobs (AgentAction), email threads (AgentThread),
invoices/estimates (Invoice), and internal messages (InternalThread).
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Float, Boolean, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class ServiceCase(Base):
    __tablename__ = "service_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    customer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("customers.id", ondelete="SET NULL"))
    case_number: Mapped[str] = mapped_column(String(20), unique=True)
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(25), default="new")
    priority: Mapped[str] = mapped_column(String(10), default="normal")
    assigned_to_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    assigned_to_name: Mapped[str | None] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(30))  # email, manual, internal_message, estimate_approval
    billing_name: Mapped[str | None] = mapped_column(String(200))  # For non-DB customers (one-off jobs)

    # Ownership
    manager_name: Mapped[str | None] = mapped_column(String(100))  # Case coordinator
    current_actor_name: Mapped[str | None] = mapped_column(String(100))  # Who needs to act next (derived)

    # Denormalized counts
    job_count: Mapped[int] = mapped_column(Integer, default=0)
    open_job_count: Mapped[int] = mapped_column(Integer, default=0)
    thread_count: Mapped[int] = mapped_column(Integer, default=0)
    invoice_count: Mapped[int] = mapped_column(Integer, default=0)
    internal_thread_count: Mapped[int] = mapped_column(Integer, default=0)
    deepblue_conversation_count: Mapped[int] = mapped_column(Integer, default=0)
    total_invoiced: Mapped[float] = mapped_column(Float, default=0.0)
    total_paid: Mapped[float] = mapped_column(Float, default=0.0)

    # Attention flags (computed by update_status_from_children)
    flag_estimate_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_estimate_rejected: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_payment_received: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_customer_replied: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_jobs_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_invoice_overdue: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_stale: Mapped[bool] = mapped_column(Boolean, default=False)

    created_by: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    jobs = relationship("AgentAction", back_populates="case", order_by="AgentAction.created_at")
    threads = relationship("AgentThread", back_populates="case", order_by="AgentThread.created_at")
    invoices = relationship("Invoice", back_populates="case", order_by="Invoice.created_at")
    internal_threads = relationship("InternalThread", back_populates="case")
    customer = relationship("Customer", lazy="noload")

    __table_args__ = (
        Index("ix_service_cases_org_status", "organization_id", "status"),
        Index("ix_service_cases_org_customer", "organization_id", "customer_id"),
        Index("ix_service_cases_org_updated", "organization_id", "updated_at"),
    )
