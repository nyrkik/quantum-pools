"""add body_of_water_id to satellite_analyses

Revision ID: 75f82d5141d5
Revises: 2785866809e9
Create Date: 2026-03-14 17:57:46.313302

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '75f82d5141d5'
down_revision: Union[str, None] = '2785866809e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add body_of_water_id column
    op.add_column('satellite_analyses', sa.Column('body_of_water_id', sa.String(36), nullable=True))
    op.create_foreign_key(
        'fk_satellite_analyses_bow_id',
        'satellite_analyses', 'bodies_of_water',
        ['body_of_water_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_index('ix_satellite_analyses_body_of_water_id', 'satellite_analyses', ['body_of_water_id'], unique=True)

    # property_id index is already non-unique in the DB, no constraint to drop

    # Backfill: assign each existing analysis to the first pool BOW at its property
    op.execute("""
        UPDATE satellite_analyses sa
        SET body_of_water_id = sub.bow_id
        FROM (
            SELECT DISTINCT ON (bow.property_id) bow.property_id, bow.id AS bow_id
            FROM bodies_of_water bow
            WHERE bow.water_type = 'pool'
            ORDER BY bow.property_id, bow.created_at
        ) sub
        WHERE sa.property_id = sub.property_id
    """)


def downgrade() -> None:
    op.drop_index('ix_satellite_analyses_body_of_water_id', 'satellite_analyses')
    op.drop_constraint('fk_satellite_analyses_bow_id', 'satellite_analyses', type_='foreignkey')
    op.drop_column('satellite_analyses', 'body_of_water_id')
    pass
