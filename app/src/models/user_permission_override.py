"""User permission override — per-user grants or revocations."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class UserPermissionOverride(Base):
    __tablename__ = "user_permission_overrides"
    __table_args__ = (
        UniqueConstraint("org_user_id", "permission_id", name="uq_user_perm_override"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organization_users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    permission_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    scope: Mapped[str] = mapped_column(String(10), default="all")
    granted: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    org_user = relationship("OrganizationUser", lazy="noload")
    permission = relationship("Permission", lazy="noload")
