"""rename unassigned_pool handler to hold_for_dispatch

Phase 4 shipped a `unassigned_pool` handler whose name collided with
pool-service domain vocabulary ("pool" means water body, not labor
queue). Renamed to `hold_for_dispatch` 2026-04-21 while the feature
was 1 day old and only one org (Sapphire dogfood) had a row.

Data-only: updates any `org_workflow_config.post_creation_handlers`
rows that reference the old name. Schema is unchanged (JSONB column).
Immutable `platform_events` rows are left alone — they're audit
history and queries that consume them should handle both names (see
docs/event-taxonomy.md note).

Revision ID: e7a4c5f91d03
Revises: d5e8a7c14f22
"""
from typing import Sequence, Union

from alembic import op


revision: str = "e7a4c5f91d03"
down_revision: Union[str, None] = "d5e8a7c14f22"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE org_workflow_config
        SET post_creation_handlers = jsonb_set(
            post_creation_handlers::jsonb,
            '{job}',
            '"hold_for_dispatch"'::jsonb
        )
        WHERE post_creation_handlers::jsonb->>'job' = 'unassigned_pool'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE org_workflow_config
        SET post_creation_handlers = jsonb_set(
            post_creation_handlers::jsonb,
            '{job}',
            '"unassigned_pool"'::jsonb
        )
        WHERE post_creation_handlers::jsonb->>'job' = 'hold_for_dispatch'
        """
    )
