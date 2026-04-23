"""rename All Mail system folder to Historical

After the 2026-04-22 historical Gmail ingest, 90%+ of threads in the
"All Mail" escape-hatch folder were historical (is_historical=True).
The "everything, including sent/spam/active" semantics confused users
looking for pre-cutover context. Narrow it to historical-only and
rename the folder + permission description accordingly.

Folder: `system_key='all'` → `system_key='historical'`, name "All Mail"
→ "Historical", icon `mailbox` → `archive`. Covers existing Sapphire
row plus any org that might have already seeded the folder.

Permission `inbox.see_all_mail` slug stays (identifier; no user-visible
drift), but description is updated to reflect the new scope.

Revision ID: 79d5b020691e
Revises: db5a5519b13e
"""
from typing import Sequence, Union

from alembic import op


revision: str = "79d5b020691e"
down_revision: Union[str, None] = "db5a5519b13e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE inbox_folders
        SET system_key = 'historical',
            name = 'Historical',
            icon = 'archive'
        WHERE system_key = 'all'
        """
    )
    op.execute(
        """
        UPDATE permissions
        SET description = 'See the Historical folder (pre-cutover mail imported from Gmail) and the auto-handled email count chip on Inbox.'
        WHERE slug = 'inbox.see_all_mail'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE inbox_folders
        SET system_key = 'all',
            name = 'All Mail',
            icon = 'mailbox'
        WHERE system_key = 'historical'
        """
    )
    op.execute(
        """
        UPDATE permissions
        SET description = 'See the All Mail folder + auto-handled email count chip on Inbox. Use when classifications might hide important email.'
        WHERE slug = 'inbox.see_all_mail'
        """
    )
