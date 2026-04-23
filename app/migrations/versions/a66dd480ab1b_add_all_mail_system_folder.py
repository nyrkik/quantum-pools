"""add All Mail system folder — live-mail escape hatch

Brings back the "All Mail" folder name but with a current-mail-only scope
(is_historical=false). Acts as the failsafe view when QP's AI auto-handles
a thread into status=ignored without a folder assignment, making it
invisible in every other view. Separate from Historical.

Sort order 4 — between Spam (3) and Historical (5).
Icon: mailbox. Gated by the same inbox.see_all_mail permission as
Historical (already granted to owner/admin/manager).

Revision ID: a66dd480ab1b
Revises: b63a079c1ade
"""
from typing import Sequence, Union

from alembic import op


revision: str = "a66dd480ab1b"
down_revision: Union[str, None] = "b63a079c1ade"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE inbox_folders SET sort_order = 5 WHERE system_key = 'historical'")
    op.execute(
        """
        INSERT INTO inbox_folders
          (id, organization_id, name, icon, sort_order, is_system, system_key, created_at, updated_at)
        SELECT
          gen_random_uuid()::text,
          o.id,
          'All Mail',
          'mailbox',
          4,
          true,
          'all_mail',
          now(),
          now()
        FROM organizations o
        WHERE NOT EXISTS (
          SELECT 1 FROM inbox_folders f
          WHERE f.organization_id = o.id AND f.system_key = 'all_mail'
        )
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM inbox_folders WHERE system_key = 'all_mail'")
    op.execute("UPDATE inbox_folders SET sort_order = 4 WHERE system_key = 'historical'")
