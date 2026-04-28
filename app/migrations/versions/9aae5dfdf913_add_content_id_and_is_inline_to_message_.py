"""add content_id and is_inline to message_attachments

Inline images in email HTML bodies use `<img src="cid:<id>">` to reference
parts attached as `Content-Disposition: inline` with a matching `Content-ID`
header. Without a way to resolve cid: refs, our sandboxed iframe rendered
those as broken images while the same parts also appeared as full-size
square thumbnails in the attachment grid below. This migration adds the
columns the API needs to (a) flag inline-only attachments (excluded from
the grid) and (b) rewrite `cid:` URLs to attachment-download URLs so the
body iframe renders inline images at their intended size.

Revision ID: 9aae5dfdf913
Revises: 1c1891f70983
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9aae5dfdf913'
down_revision: Union[str, None] = '1c1891f70983'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "message_attachments",
        sa.Column("content_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "message_attachments",
        sa.Column(
            "is_inline", sa.Boolean(), nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        "ix_message_attachments_content_id",
        "message_attachments",
        ["content_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_message_attachments_content_id", table_name="message_attachments")
    op.drop_column("message_attachments", "is_inline")
    op.drop_column("message_attachments", "content_id")
