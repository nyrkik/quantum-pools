"""Add billing and payment fields to customers

Revision ID: 9049f39ec8c1
Revises: d4d0f6a795c0
Create Date: 2025-10-26 12:31:37.456274

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9049f39ec8c1'
down_revision: Union[str, None] = 'd4d0f6a795c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add billing fields
    op.add_column('customers', sa.Column('service_rate', sa.Numeric(precision=10, scale=2), nullable=True, comment='Service rate amount (e.g., 125.00 for $125)'))
    op.add_column('customers', sa.Column('billing_frequency', sa.String(length=20), nullable=True, comment='Billing frequency: weekly, monthly, per-visit'))
    op.add_column('customers', sa.Column('rate_notes', sa.String(length=500), nullable=True, comment='Special pricing notes or agreements'))

    # Add payment method fields
    op.add_column('customers', sa.Column('payment_method_type', sa.String(length=20), nullable=True, comment='Payment method: credit_card, ach, check, cash'))
    op.add_column('customers', sa.Column('stripe_customer_id', sa.String(length=100), nullable=True, comment='Stripe customer ID for payment processing'))
    op.add_column('customers', sa.Column('stripe_payment_method_id', sa.String(length=100), nullable=True, comment='Stripe payment method ID'))
    op.add_column('customers', sa.Column('payment_last_four', sa.String(length=4), nullable=True, comment='Last 4 digits of card/account for display only'))
    op.add_column('customers', sa.Column('payment_brand', sa.String(length=50), nullable=True, comment='Card brand (Visa, Mastercard, etc.) or bank name'))


def downgrade() -> None:
    # Drop payment fields
    op.drop_column('customers', 'payment_brand')
    op.drop_column('customers', 'payment_last_four')
    op.drop_column('customers', 'stripe_payment_method_id')
    op.drop_column('customers', 'stripe_customer_id')
    op.drop_column('customers', 'payment_method_type')

    # Drop billing fields
    op.drop_column('customers', 'rate_notes')
    op.drop_column('customers', 'billing_frequency')
    op.drop_column('customers', 'service_rate')
