"""Add case flags and ownership fields

Revision ID: c94c6edb812a
Revises: 10a92481d387
Create Date: 2026-04-08 14:54:08.020517

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c94c6edb812a'
down_revision: Union[str, None] = '10a92481d387'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('service_cases', sa.Column('manager_name', sa.String(length=100), nullable=True))
    op.add_column('service_cases', sa.Column('current_actor_name', sa.String(length=100), nullable=True))
    op.add_column('service_cases', sa.Column('flag_estimate_approved', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('service_cases', sa.Column('flag_estimate_rejected', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('service_cases', sa.Column('flag_payment_received', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('service_cases', sa.Column('flag_customer_replied', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('service_cases', sa.Column('flag_jobs_complete', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('service_cases', sa.Column('flag_invoice_overdue', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('service_cases', sa.Column('flag_stale', sa.Boolean(), server_default='false', nullable=False))

    # Backfill manager_name from created_by
    op.execute("UPDATE service_cases SET manager_name = created_by WHERE manager_name IS NULL AND created_by IS NOT NULL")


def downgrade() -> None:
    op.drop_column('service_cases', 'flag_stale')
    op.drop_column('service_cases', 'flag_invoice_overdue')
    op.drop_column('service_cases', 'flag_jobs_complete')
    op.drop_column('service_cases', 'flag_customer_replied')
    op.drop_column('service_cases', 'flag_payment_received')
    op.drop_column('service_cases', 'flag_estimate_rejected')
    op.drop_column('service_cases', 'flag_estimate_approved')
    op.drop_column('service_cases', 'current_actor_name')
    op.drop_column('service_cases', 'manager_name')
