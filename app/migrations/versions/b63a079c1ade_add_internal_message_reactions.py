"""add internal_message_reactions table

Per-user emoji reactions on internal staff messages. Unique on
(message_id, user_id, emoji) — a user can add different emojis to a
message but each emoji only once. Toggle semantics live at the API layer.

Revision ID: b63a079c1ade
Revises: 113707d187f7
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b63a079c1ade"
down_revision: Union[str, None] = "113707d187f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "internal_message_reactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "message_id",
            sa.String(36),
            sa.ForeignKey("internal_messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("emoji", sa.String(16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("message_id", "user_id", "emoji", name="uq_imr_msg_user_emoji"),
    )
    op.create_index("ix_imr_message_id", "internal_message_reactions", ["message_id"])


def downgrade() -> None:
    op.drop_index("ix_imr_message_id", table_name="internal_message_reactions")
    op.drop_table("internal_message_reactions")
