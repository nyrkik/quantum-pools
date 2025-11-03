"""add_tech_routes_table

Revision ID: 94a842852a05
Revises: f85398694f75
Create Date: 2025-11-02 09:19:07.744054

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '94a842852a05'
down_revision: Union[str, None] = 'f85398694f75'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('tech_routes',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('organization_id', sa.UUID(), nullable=False, comment='Organization this route belongs to'),
        sa.Column('tech_id', sa.UUID(), nullable=False, comment='Tech this route is for'),
        sa.Column('service_day', sa.String(length=20), nullable=False, comment='Day of week (monday, tuesday, etc.)'),
        sa.Column('route_date', sa.Date(), nullable=False, comment='Specific date this route is for'),
        sa.Column('stop_sequence', postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment='Ordered array of customer IDs'),
        sa.Column('total_distance', sa.Float(), nullable=True, comment='Total route distance in miles'),
        sa.Column('total_duration', sa.Integer(), nullable=True, comment='Total route duration in minutes'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
        sa.ForeignKeyConstraint(['tech_id'], ['techs.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_tech_routes_org_date', 'tech_routes', ['organization_id', 'route_date'], unique=False)
    op.create_index('ix_tech_routes_tech_day_date', 'tech_routes', ['tech_id', 'service_day', 'route_date'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_tech_routes_tech_day_date', table_name='tech_routes')
    op.drop_index('ix_tech_routes_org_date', table_name='tech_routes')
    op.drop_table('tech_routes')
