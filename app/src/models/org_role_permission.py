"""Org role permission junction — maps permissions to custom org roles with scope."""

from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class OrgRolePermission(Base):
    __tablename__ = "org_role_permissions"

    org_role_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("org_roles.id", ondelete="CASCADE"), primary_key=True,
    )
    permission_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True,
    )
    scope: Mapped[str] = mapped_column(String(10), default="all")

    org_role = relationship("OrgRole", back_populates="permissions", lazy="noload")
    permission = relationship("Permission", lazy="noload")
