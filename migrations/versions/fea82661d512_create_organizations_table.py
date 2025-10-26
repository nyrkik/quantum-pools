"""Create organizations table

Revision ID: fea82661d512
Revises: 705115ad5228
Create Date: 2025-10-26 11:24:13.200846

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision: str = 'fea82661d512'
down_revision: Union[str, None] = '705115ad5228'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'organizations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('slug', sa.String(100), nullable=False, unique=True),
        sa.Column('subdomain', sa.String(63), unique=True),

        # Subscription
        sa.Column('plan_tier', sa.String(50), nullable=False, server_default='starter'),
        sa.Column('subscription_status', sa.String(50), nullable=False, server_default='trial'),
        sa.Column('trial_ends_at', sa.DateTime),
        sa.Column('trial_days', sa.Integer, server_default='14'),

        # Billing
        sa.Column('billing_email', sa.String(255)),
        sa.Column('billing_address', sa.Text),
        sa.Column('stripe_customer_id', sa.String(100)),
        sa.Column('stripe_subscription_id', sa.String(100)),

        # Plan limits
        sa.Column('max_users', sa.Integer),
        sa.Column('max_customers', sa.Integer),
        sa.Column('max_techs', sa.Integer),
        sa.Column('max_routes_per_day', sa.Integer),

        # Features
        sa.Column('features_enabled', JSONB, server_default='{}'),

        # Map provider
        sa.Column('default_map_provider', sa.String(50), server_default='openstreetmap'),
        sa.Column('google_maps_api_key', sa.String(200)),

        # Customization
        sa.Column('logo_url', sa.String(500)),
        sa.Column('primary_color', sa.String(7)),
        sa.Column('timezone', sa.String(50), server_default='America/Los_Angeles'),

        # Metadata
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('onboarded_at', sa.DateTime),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()'))
    )

    # Indexes
    op.create_index('idx_orgs_subdomain', 'organizations', ['subdomain'])
    op.create_index('idx_orgs_slug', 'organizations', ['slug'])
    op.create_index('idx_orgs_subscription_status', 'organizations', ['subscription_status'])
    op.create_index('idx_orgs_stripe_customer', 'organizations', ['stripe_customer_id'])


def downgrade() -> None:
    op.drop_table('organizations')
