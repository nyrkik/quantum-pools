"""add estimate and invoice terms to org_cost_settings

Revision ID: b101b746291e
Revises: d6cfc72493b3
Create Date: 2026-03-30 18:42:24.215196

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b101b746291e'
down_revision: Union[str, None] = 'd6cfc72493b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('org_cost_settings', sa.Column('payment_terms_days', sa.Integer(), nullable=False, server_default='30'))
    op.add_column('org_cost_settings', sa.Column('estimate_validity_days', sa.Integer(), nullable=False, server_default='30'))
    op.add_column('org_cost_settings', sa.Column('late_fee_pct', sa.Float(), nullable=False, server_default='1.5'))
    op.add_column('org_cost_settings', sa.Column('warranty_days', sa.Integer(), nullable=False, server_default='30'))
    op.add_column('org_cost_settings', sa.Column('estimate_terms', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('org_cost_settings', 'estimate_terms')
    op.drop_column('org_cost_settings', 'warranty_days')
    op.drop_column('org_cost_settings', 'late_fee_pct')
    op.drop_column('org_cost_settings', 'estimate_validity_days')
    op.drop_column('org_cost_settings', 'payment_terms_days')
