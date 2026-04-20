"""phase4 org_workflow_config table

Phase 4 Step 1 migration. See docs/ai-platform-phase-4.md §5.

Creates the org_workflow_config table — one row per org (lazy-created
on first write). Stores the post-creation handler map + the
default-assignee strategy. System defaults live in code
(`WorkflowConfigService.get_or_default`); this migration does NOT
backfill existing orgs.

Revision ID: b7e4a21c9f10
Revises: 45c1d6086806
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg


revision: str = 'b7e4a21c9f10'
down_revision: Union[str, None] = '45c1d6086806'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # organizations.id and users.id are String(36) varchars in existing
    # schema (not native UUID); FK types must match.
    op.create_table(
        "org_workflow_config",
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "post_creation_handlers",
            pg.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "default_assignee_strategy",
            pg.JSONB(),
            nullable=False,
            server_default=sa.text(
                "'{\"strategy\":\"last_used_by_user\"}'::jsonb"
            ),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("org_workflow_config")
