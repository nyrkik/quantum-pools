"""add inbox_folders and thread folder_id

Revision ID: cce1bb5776ed
Revises: c83747803796
Create Date: 2026-04-12 07:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'cce1bb5776ed'
down_revision: Union[str, None] = 'c83747803796'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create inbox_folders table
    op.create_table('inbox_folders',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('icon', sa.String(length=50), nullable=True),
        sa.Column('color', sa.String(length=20), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('system_key', sa.String(length=20), nullable=True),
        sa.Column('gmail_label_id', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'system_key', name='uq_inbox_folders_org_system_key'),
    )
    op.create_index('ix_inbox_folders_organization_id', 'inbox_folders', ['organization_id'])

    # Add folder columns to agent_threads
    op.add_column('agent_threads', sa.Column('folder_id', sa.String(length=36), nullable=True))
    op.add_column('agent_threads', sa.Column('folder_override', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.create_index('ix_agent_threads_folder_id', 'agent_threads', ['folder_id'])
    op.create_foreign_key('fk_agent_threads_folder_id', 'agent_threads', 'inbox_folders', ['folder_id'], ['id'], ondelete='SET NULL')

    # Seed system folders for each org
    op.execute("""
        INSERT INTO inbox_folders (id, organization_id, name, icon, sort_order, is_system, system_key, created_at, updated_at)
        SELECT
            gen_random_uuid()::text,
            o.id,
            f.name,
            f.icon,
            f.sort_order,
            true,
            f.system_key,
            now(),
            now()
        FROM organizations o
        CROSS JOIN (VALUES
            ('inbox', 'Inbox', 'inbox', 0),
            ('sent', 'Sent', 'send', 1),
            ('automated', 'Automated', 'bot', 2),
            ('spam', 'Spam', 'shield-alert', 3)
        ) AS f(system_key, name, icon, sort_order)
    """)

    # Backfill: assign existing threads to system folders
    # Spam/auto-reply → Spam folder
    op.execute("""
        UPDATE agent_threads t
        SET folder_id = f.id
        FROM inbox_folders f
        WHERE f.organization_id = t.organization_id
          AND f.system_key = 'spam'
          AND t.category IN ('spam', 'auto_reply')
          AND t.folder_id IS NULL
    """)

    # Outbound-only handled → Sent folder
    op.execute("""
        UPDATE agent_threads t
        SET folder_id = f.id
        FROM inbox_folders f
        WHERE f.organization_id = t.organization_id
          AND f.system_key = 'sent'
          AND t.last_direction = 'outbound'
          AND t.has_pending = false
          AND t.folder_id IS NULL
    """)

    # Auto-handled no_response/thank_you/general-handled → Automated folder
    op.execute("""
        UPDATE agent_threads t
        SET folder_id = f.id
        FROM inbox_folders f
        WHERE f.organization_id = t.organization_id
          AND f.system_key = 'automated'
          AND t.status IN ('handled', 'ignored')
          AND t.category IN ('no_response', 'thank_you')
          AND t.folder_id IS NULL
    """)

    # Everything else stays NULL = Inbox


def downgrade() -> None:
    op.drop_constraint('fk_agent_threads_folder_id', 'agent_threads', type_='foreignkey')
    op.drop_index('ix_agent_threads_folder_id', table_name='agent_threads')
    op.drop_column('agent_threads', 'folder_override')
    op.drop_column('agent_threads', 'folder_id')
    op.drop_index('ix_inbox_folders_organization_id', table_name='inbox_folders')
    op.drop_table('inbox_folders')
