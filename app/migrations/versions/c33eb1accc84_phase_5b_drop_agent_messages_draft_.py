"""Phase 5b — drop agent_messages.draft_response

AI drafts migrated to `agent_proposals(entity_type='email_reply')` in
Phase 5 (2026-04-24). The R7 audit enforcer blocks any `.draft_response`
attribute access in `app/src/`; this migration drops the now-unused
column. `final_response` stays — it's actively written by the email_reply
proposal creator and read by 6 downstream sites (denormalization
cleanup is a separate, bigger project).

The port script (`scripts/port_draft_response_to_proposals.py`) ran on
Sapphire 2026-04-24 and persisted 150 proposals + 144 corrections before
this column drop; no data is being lost.

Revision ID: c33eb1accc84
Revises: 0002c096bcdc
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c33eb1accc84"
down_revision: Union[str, None] = "0002c096bcdc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("agent_messages", "draft_response")


def downgrade() -> None:
    op.add_column(
        "agent_messages",
        sa.Column("draft_response", sa.Text(), nullable=True),
    )
