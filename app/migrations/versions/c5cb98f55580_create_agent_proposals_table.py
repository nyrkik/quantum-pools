"""create agent_proposals table

Phase 2 Step 1 — the staged-actions primitive. Every AI output (drafted
email, proposed job, org config recommendation, DeepBlue tool confirmation)
becomes a row in this table. `ProposalService` manages state transitions;
a resolve atomically writes a learning record via `AgentLearningService`.

Schema per `docs/ai-platform-phase-2.md` §4.1.

Revision ID: c5cb98f55580
Revises: 815df59a7fa7
Create Date: 2026-04-19 08:41:18.414722
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5cb98f55580'
down_revision: Union[str, None] = '815df59a7fa7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_proposals",
        # Identity & ownership
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organization_id", sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Provenance — who proposed what, for which source record.
        # agent_type mirrors AgentLearningService constants.
        sa.Column("agent_type", sa.String(length=50), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_id", sa.String(length=36)),
        # The draft itself — fields that would commit to the target entity.
        sa.Column("proposed_payload", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("confidence", sa.Float()),
        # State machine
        # staged | accepted | edited | rejected | expired | superseded
        sa.Column("status", sa.String(length=20), nullable=False, server_default="staged"),
        sa.Column(
            "rejected_permanently", sa.Boolean(),
            nullable=False, server_default=sa.text("false"),
        ),
        sa.Column(
            "superseded_by_id", sa.String(length=36),
            sa.ForeignKey("agent_proposals.id"),
            nullable=True,
        ),
        # Outcome — filled on accept/edit. Polymorphic pair (type, id)
        # since target table varies by entity_type.
        sa.Column("outcome_entity_type", sa.String(length=50)),
        sa.Column("outcome_entity_id", sa.String(length=36)),
        # RFC 6902 JSON patch when user edited before accepting. Learning
        # signal consumes this to know what the human changed.
        sa.Column("user_delta", sa.dialects.postgresql.JSONB()),
        # Resolution audit
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column(
            "resolved_by_user_id", sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("resolution_note", sa.Text()),
        # Lifecycle
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("NOW()"),
        ),
    )

    # Indexes per §4.1 — three access patterns:
    # 1. "Show me the open proposals for org X, newest first."
    op.create_index(
        "ix_agent_proposals_org_status_created",
        "agent_proposals",
        ["organization_id", "status", sa.text("created_at DESC")],
    )
    # 2. "Show me all proposals staged from this source entity."
    #    (e.g., every proposal derived from agent_thread 'abc').
    op.create_index(
        "ix_agent_proposals_source",
        "agent_proposals",
        ["source_type", "source_id"],
    )
    # 3. "Show me all staged proposals this agent has produced."
    op.create_index(
        "ix_agent_proposals_agent_status",
        "agent_proposals",
        ["agent_type", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_proposals_agent_status", table_name="agent_proposals")
    op.drop_index("ix_agent_proposals_source", table_name="agent_proposals")
    op.drop_index("ix_agent_proposals_org_status_created", table_name="agent_proposals")
    op.drop_table("agent_proposals")
