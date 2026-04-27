"""add observer_mutes and observer_thresholds to org_workflow_config

Phase 6 (workflow_observer agent) state:
- observer_mutes: per-org per-detector mute list. Presence of detector_id
  in the dict tells scan_org to skip that detector for the org.
- observer_thresholds: per-org per-detector self-tuned confidence thresholds.
  Symmetric snap-back from AgentLearningService corrections (>30% reject
  → bump +0.05; >70% accept → lower -0.05; range capped to [default, 0.99]).
  Absent detector_id key = use the detector's default threshold.

Revision ID: 4450794421b9
Revises: c41a82b53de7
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "4450794421b9"
down_revision: Union[str, None] = "c41a82b53de7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "org_workflow_config",
        sa.Column(
            "observer_mutes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "org_workflow_config",
        sa.Column(
            "observer_thresholds",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("org_workflow_config", "observer_thresholds")
    op.drop_column("org_workflow_config", "observer_mutes")
