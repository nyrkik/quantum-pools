"""add_user_id_to_techs

Revision ID: abd3df5a3c9f
Revises: 4c5104289e2d
Create Date: 2025-11-04 05:41:35.979598

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'abd3df5a3c9f'
down_revision: Union[str, None] = '4c5104289e2d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add user_id column to techs table
    op.add_column('techs', sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(op.f('ix_techs_user_id'), 'techs', ['user_id'], unique=False)
    op.create_foreign_key('fk_techs_user_id', 'techs', 'users', ['user_id'], ['id'])
    op.create_unique_constraint('uq_techs_user_id', 'techs', ['user_id'])


def downgrade() -> None:
    # Remove user_id column from techs table
    op.drop_constraint('uq_techs_user_id', 'techs', type_='unique')
    op.drop_constraint('fk_techs_user_id', 'techs', type_='foreignkey')
    op.drop_index(op.f('ix_techs_user_id'), table_name='techs')
    op.drop_column('techs', 'user_id')
