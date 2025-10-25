"""add visit_duration to customers

Revision ID: 21ea4292c605
Revises: af195a4682fd
Create Date: 2025-10-25 06:34:03.016142

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '21ea4292c605'
down_revision: Union[str, None] = 'af195a4682fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add visit_duration column with default value of 15 minutes
    op.add_column('customers', sa.Column('visit_duration', sa.Integer(), nullable=False, server_default='15'))

    # Update existing rows based on service_type
    # residential = 15 min, commercial = 25 min
    op.execute("""
        UPDATE customers
        SET visit_duration = CASE
            WHEN service_type = 'commercial' THEN 25
            ELSE 15
        END
    """)


def downgrade() -> None:
    op.drop_column('customers', 'visit_duration')
