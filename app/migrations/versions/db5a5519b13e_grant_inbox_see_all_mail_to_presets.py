"""grant inbox.see_all_mail to owner/admin/manager presets

The `inbox.see_all_mail` permission row exists in `permissions` but was
never wired into any preset, so the frontend `canSeeAllMail` check
returned false for every role — including owner. The All Mail folder
(a system folder created per org) was therefore invisible in the
inbox sidebar for all users.

Assign it to the same presets that already carry `inbox.manage` so
owner/admin/manager can see the escape-hatch folder and the
auto-handled-today count chip that depends on the same permission.
Idempotent — skips presets where the grant already exists.

Revision ID: db5a5519b13e
Revises: 69abccb08675
"""
from typing import Sequence, Union

from alembic import op


revision: str = "db5a5519b13e"
down_revision: Union[str, None] = "69abccb08675"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TARGET_PRESETS = ("owner", "admin", "manager")


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO preset_permissions (preset_id, permission_id, scope)
        SELECT pr.id, p.id, 'all'
        FROM permission_presets pr
        CROSS JOIN permissions p
        WHERE pr.slug IN {_TARGET_PRESETS!r}
          AND p.slug = 'inbox.see_all_mail'
        ON CONFLICT (preset_id, permission_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        DELETE FROM preset_permissions pp
        USING permission_presets pr, permissions p
        WHERE pp.preset_id = pr.id
          AND pp.permission_id = p.id
          AND pr.slug IN {_TARGET_PRESETS!r}
          AND p.slug = 'inbox.see_all_mail'
        """
    )
