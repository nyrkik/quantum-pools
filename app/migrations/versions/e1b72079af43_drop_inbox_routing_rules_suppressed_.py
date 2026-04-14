"""drop inbox_routing_rules + suppressed_email_senders + routing_rule_id

Revision ID: e1b72079af43
Revises: 5442e2305513
Create Date: 2026-04-14 04:46:30.387539

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1b72079af43'
down_revision: Union[str, None] = '5442e2305513'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # agent_threads.routing_rule_id held a FK to inbox_routing_rules.id.
    # Drop the FK first, then the column, then the two legacy tables.
    with op.batch_alter_table('agent_threads') as batch_op:
        # The FK was created without an explicit name in the original
        # migration; fall back to Postgres's implicit name if needed.
        try:
            batch_op.drop_constraint(
                'agent_threads_routing_rule_id_fkey', type_='foreignkey',
            )
        except Exception:
            pass
        batch_op.drop_column('routing_rule_id')

    op.drop_table('suppressed_email_senders')
    op.drop_table('inbox_routing_rules')


def downgrade() -> None:
    # No-op — the old data has been migrated into inbox_rules and there's
    # no recovery path without the pre-migration backup. Use the backup.
    raise RuntimeError(
        "Downgrading past e1b72079af43 is not supported. "
        "Restore from the pre-migration backup if you need the old tables back."
    )
