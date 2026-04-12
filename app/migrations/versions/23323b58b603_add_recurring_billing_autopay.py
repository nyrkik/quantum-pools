"""add_recurring_billing_autopay

Revision ID: 23323b58b603
Revises: c94c6edb812a
Create Date: 2026-04-08 18:12:12.208244

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '23323b58b603'
down_revision: Union[str, None] = 'c94c6edb812a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New table: autopay_attempts
    op.create_table('autopay_attempts',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('customer_id', sa.String(length=36), nullable=False),
        sa.Column('invoice_id', sa.String(length=36), nullable=False),
        sa.Column('stripe_payment_intent_id', sa.String(length=255), nullable=True),
        sa.Column('attempt_number', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('failure_code', sa.String(length=50), nullable=True),
        sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_autopay_attempts_customer_id', 'autopay_attempts', ['customer_id'])
    op.create_index('ix_autopay_attempts_invoice_id', 'autopay_attempts', ['invoice_id'])
    op.create_index('ix_autopay_attempts_organization_id', 'autopay_attempts', ['organization_id'])

    # Customer: billing cycle + saved card + dunning
    op.add_column('customers', sa.Column('billing_day_of_month', sa.Integer(), server_default='1', nullable=False))
    op.add_column('customers', sa.Column('next_billing_date', sa.Date(), nullable=True))
    op.add_column('customers', sa.Column('last_billed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('customers', sa.Column('stripe_payment_method_id', sa.String(length=255), nullable=True))
    op.add_column('customers', sa.Column('stripe_card_last4', sa.String(length=4), nullable=True))
    op.add_column('customers', sa.Column('stripe_card_brand', sa.String(length=20), nullable=True))
    op.add_column('customers', sa.Column('stripe_card_exp_month', sa.Integer(), nullable=True))
    op.add_column('customers', sa.Column('stripe_card_exp_year', sa.Integer(), nullable=True))
    op.add_column('customers', sa.Column('card_setup_token', sa.String(length=64), nullable=True))
    op.add_column('customers', sa.Column('autopay_failure_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('customers', sa.Column('autopay_last_failed_at', sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint('uq_customers_card_setup_token', 'customers', ['card_setup_token'])

    # Invoice: recurring billing provenance
    op.add_column('invoices', sa.Column('generation_source', sa.String(length=20), nullable=True))
    op.add_column('invoices', sa.Column('billing_period_start', sa.Date(), nullable=True))
    op.add_column('invoices', sa.Column('billing_period_end', sa.Date(), nullable=True))

    # Payment: autopay flag
    op.add_column('payments', sa.Column('is_autopay', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    op.drop_column('payments', 'is_autopay')
    op.drop_column('invoices', 'billing_period_end')
    op.drop_column('invoices', 'billing_period_start')
    op.drop_column('invoices', 'generation_source')
    op.drop_constraint('uq_customers_card_setup_token', 'customers', type_='unique')
    op.drop_column('customers', 'autopay_last_failed_at')
    op.drop_column('customers', 'autopay_failure_count')
    op.drop_column('customers', 'card_setup_token')
    op.drop_column('customers', 'stripe_card_exp_year')
    op.drop_column('customers', 'stripe_card_exp_month')
    op.drop_column('customers', 'stripe_card_brand')
    op.drop_column('customers', 'stripe_card_last4')
    op.drop_column('customers', 'stripe_payment_method_id')
    op.drop_column('customers', 'last_billed_at')
    op.drop_column('customers', 'next_billing_date')
    op.drop_column('customers', 'billing_day_of_month')
    op.drop_index('ix_autopay_attempts_organization_id', table_name='autopay_attempts')
    op.drop_index('ix_autopay_attempts_invoice_id', table_name='autopay_attempts')
    op.drop_index('ix_autopay_attempts_customer_id', table_name='autopay_attempts')
    op.drop_table('autopay_attempts')
