"""Preset-permission junction — maps permissions to presets with scope."""

from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class PresetPermission(Base):
    __tablename__ = "preset_permissions"

    preset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("permission_presets.id", ondelete="CASCADE"), primary_key=True,
    )
    permission_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True,
    )
    scope: Mapped[str] = mapped_column(String(10), default="all")

    preset = relationship("PermissionPreset", back_populates="permissions", lazy="noload")
    permission = relationship("Permission", lazy="noload")
