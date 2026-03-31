"""split_contact_name_to_first_last

Revision ID: 78fb11cef021
Revises: b26c6b673e36
Create Date: 2026-03-31 11:58:59.044469

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '78fb11cef021'
down_revision: Union[str, None] = 'b26c6b673e36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('customer_contacts', sa.Column('first_name', sa.String(length=100), nullable=True))
    op.add_column('customer_contacts', sa.Column('last_name', sa.String(length=100), nullable=True))

    # Split existing name into first/last
    op.execute("""
        UPDATE customer_contacts
        SET first_name = split_part(name, ' ', 1),
            last_name = CASE
                WHEN position(' ' in name) > 0
                THEN substring(name from position(' ' in name) + 1)
                ELSE NULL
            END
        WHERE name IS NOT NULL AND name != ''
    """)

    op.drop_column('customer_contacts', 'name')


def downgrade() -> None:
    op.add_column('customer_contacts', sa.Column('name', sa.VARCHAR(length=200), autoincrement=False, nullable=True))
    op.execute("""
        UPDATE customer_contacts
        SET name = COALESCE(first_name, '') || CASE WHEN last_name IS NOT NULL THEN ' ' || last_name ELSE '' END
    """)
    op.drop_column('customer_contacts', 'last_name')
    op.drop_column('customer_contacts', 'first_name')
