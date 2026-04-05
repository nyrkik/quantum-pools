"""Add contact learning settings to organizations and dismissed senders to org users

Revision ID: a1f3c8d92e47
Revises: 82baa272fc9c
Create Date: 2026-04-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1f3c8d92e47'
down_revision: str = '82baa272fc9c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('organizations', sa.Column(
        'email_contact_learning', sa.Boolean(), nullable=False, server_default='true',
    ))
    op.add_column('organization_users', sa.Column(
        'dismissed_sender_emails', sa.Text(), nullable=False, server_default='[]',
    ))


def downgrade() -> None:
    op.drop_column('organization_users', 'dismissed_sender_emails')
    op.drop_column('organizations', 'email_contact_learning')
