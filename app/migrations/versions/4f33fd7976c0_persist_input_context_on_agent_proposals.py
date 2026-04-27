"""persist input_context on agent_proposals

Was a transient `_input_context` attr stashed on the in-memory model;
making it a real column lets the value survive across sessions so
proposal accept/reject in a different request can forward it to
AgentCorrection.input_context. Phase 6 needs this for per-detector
threshold tuning (the detector_id is encoded as a `[detector_id]` prefix
in the summary), but the column is general-purpose — any agent that
wants a persistent natural-language breadcrumb on its proposals can use
it.

Existing rows null out — they didn't have it before either.

Revision ID: 4f33fd7976c0
Revises: 4450794421b9
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4f33fd7976c0"
down_revision: Union[str, None] = "4450794421b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_proposals",
        sa.Column("input_context", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_proposals", "input_context")
