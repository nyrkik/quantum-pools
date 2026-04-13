"""add folder_id to suppressed_email_senders

Revision ID: 544070485a96
Revises: cce1bb5776ed
Create Date: 2026-04-12

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '544070485a96'
down_revision: Union[str, None] = 'cce1bb5776ed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('suppressed_email_senders', sa.Column('folder_id', sa.String(length=36), nullable=True))
    op.create_foreign_key('fk_suppressed_senders_folder', 'suppressed_email_senders', 'inbox_folders', ['folder_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint('fk_suppressed_senders_folder', 'suppressed_email_senders', type_='foreignkey')
    op.drop_column('suppressed_email_senders', 'folder_id')
