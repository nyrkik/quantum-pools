"""add Outbox system folder and reorder siblings

Outbox replaces the "Failed" inbox filter chip. Outbound messages that
haven't completed (queued / failed / bounced / delivery_error) auto-route
here. Gmail-like mental model: "where did my email go? check Outbox."

Reorder: Inbox (0) → Outbox (1) → Sent (2) → Spam (3) → Historical (4).
Previous: Inbox (0) → Sent (1) → Spam (2) → Historical (3).

Idempotent — skips orgs that already have an Outbox row.

Revision ID: 113707d187f7
Revises: 79d5b020691e
"""
from typing import Sequence, Union

from alembic import op


revision: str = "113707d187f7"
down_revision: Union[str, None] = "79d5b020691e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Reorder existing system folders to make room at sort_order=1 for Outbox.
    op.execute("UPDATE inbox_folders SET sort_order = 2 WHERE system_key = 'sent'")
    op.execute("UPDATE inbox_folders SET sort_order = 3 WHERE system_key = 'spam'")
    op.execute("UPDATE inbox_folders SET sort_order = 4 WHERE system_key = 'historical'")

    # Seed Outbox for every org that has an Inbox but no Outbox yet.
    op.execute(
        """
        INSERT INTO inbox_folders
          (id, organization_id, name, icon, sort_order, is_system, system_key, created_at, updated_at)
        SELECT
          gen_random_uuid()::text,
          o.id,
          'Outbox',
          'clock',
          1,
          true,
          'outbox',
          now(),
          now()
        FROM organizations o
        WHERE NOT EXISTS (
          SELECT 1 FROM inbox_folders f
          WHERE f.organization_id = o.id AND f.system_key = 'outbox'
        )
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM inbox_folders WHERE system_key = 'outbox'")
    op.execute("UPDATE inbox_folders SET sort_order = 1 WHERE system_key = 'sent'")
    op.execute("UPDATE inbox_folders SET sort_order = 2 WHERE system_key = 'spam'")
    op.execute("UPDATE inbox_folders SET sort_order = 3 WHERE system_key = 'historical'")
