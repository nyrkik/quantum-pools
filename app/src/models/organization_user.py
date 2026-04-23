"""OrganizationUser junction model with role-based access."""

import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Integer, Text, ForeignKey, Enum, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class OrgRole(str, enum.Enum):
    owner = "owner"
    admin = "admin"
    manager = "manager"
    technician = "technician"
    readonly = "readonly"
    custom = "custom"


class OrganizationUser(Base):
    __tablename__ = "organization_users"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_org_user"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    role: Mapped[OrgRole] = mapped_column(
        Enum(OrgRole, name="org_role", native_enum=False), nullable=False, default=OrgRole.readonly,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_developer: Mapped[bool] = mapped_column(Boolean, default=False)
    org_role_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("org_roles.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    role_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    permission_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # JSON array of sender emails this user has dismissed from contact learning prompts
    dismissed_sender_emails: Mapped[str] = mapped_column(Text, default="[]")

    # Per-user email signature tail (applied AFTER any org-level auto-prepend
    # of first name + org name + logo). Admin sets the org-wide format; each
    # user's signature content is their own. Falls back to
    # Organization.agent_signature when the user hasn't set one.
    email_signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Optional sign-off (valediction) rendered between the body and the
    # auto-prepended name line. Examples: "Best,", "v/r,", "Cheers,".
    # Null/empty = no sign-off (abrupt style).
    email_signoff: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    organization = relationship("Organization", back_populates="members")
    user = relationship("User", back_populates="org_memberships")
    custom_role = relationship("OrgRole", lazy="noload")
