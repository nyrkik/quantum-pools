"""add salt cell and insurance chem fields

Revision ID: 188053029ea7
Revises: 3c069abbfde7
Create Date: 2026-03-16 05:31:10.730859

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '188053029ea7'
down_revision: Union[str, None] = '3c069abbfde7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('regional_defaults', sa.Column('salt_cell_replacement_cost', sa.Float, server_default='0', nullable=False))
    op.add_column('regional_defaults', sa.Column('insurance_chemicals_monthly', sa.Float, server_default='0', nullable=False))
    op.add_column('chemical_cost_profiles', sa.Column('cell_cost', sa.Float, server_default='0', nullable=False))
    op.add_column('chemical_cost_profiles', sa.Column('insurance_cost', sa.Float, server_default='0', nullable=False))

    # Fix CYA to 0 for established pools
    op.execute("UPDATE regional_defaults SET cya_usage_lb_per_month_per_10k = 0")

    # Update seed data with research-corrected values
    # Liquid: 0.5 gal/10k/visit = 64 oz, acid 12 oz (research says 8-16)
    op.execute("""UPDATE regional_defaults SET
        sanitizer_usage_oz = 64, acid_usage_oz = 12, insurance_chemicals_monthly = 7.5
        WHERE sanitizer_type = 'liquid'""")

    # Tabs: ~1.5 tabs/10k = 12 oz, acid 10 oz (slightly less acid than liquid)
    op.execute("""UPDATE regional_defaults SET
        sanitizer_usage_oz = 12, acid_usage_oz = 10, insurance_chemicals_monthly = 7.5
        WHERE sanitizer_type = 'tabs'""")

    # Salt: no sanitizer, high acid (2-3x liquid), cell amortization $15/mo
    op.execute("""UPDATE regional_defaults SET
        sanitizer_usage_oz = 0, acid_usage_oz = 32, salt_cell_replacement_cost = 15,
        salt_bags_per_year_per_10k = 2, insurance_chemicals_monthly = 7.5
        WHERE sanitizer_type = 'salt'""")

    # Cal-hypo: ~6 oz/10k, acid 12 oz
    op.execute("""UPDATE regional_defaults SET
        sanitizer_usage_oz = 6, acid_usage_oz = 12, insurance_chemicals_monthly = 7.5
        WHERE sanitizer_type = 'cal_hypo'""")

    # Dichlor: ~3 oz/10k, acid 10 oz
    op.execute("""UPDATE regional_defaults SET
        sanitizer_usage_oz = 3, acid_usage_oz = 10, insurance_chemicals_monthly = 7.5
        WHERE sanitizer_type = 'dichlor'""")

    # Bromine: ~6 oz/10k, acid 6 oz (bromine is less pH-impactful)
    op.execute("""UPDATE regional_defaults SET
        sanitizer_usage_oz = 6, acid_usage_oz = 6, insurance_chemicals_monthly = 7.5
        WHERE sanitizer_type = 'bromine'""")


def downgrade() -> None:
    op.drop_column('chemical_cost_profiles', 'insurance_cost')
    op.drop_column('chemical_cost_profiles', 'cell_cost')
    op.drop_column('regional_defaults', 'insurance_chemicals_monthly')
    op.drop_column('regional_defaults', 'salt_cell_replacement_cost')
