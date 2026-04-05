"""DeepBlue usage logging, quotas, and conversation management

Revision ID: a7f3c2e58d94
Revises: f6d2a9c48e31
Create Date: 2026-04-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7f3c2e58d94'
down_revision: str = 'f6d2a9c48e31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Per-user daily usage rollup
    op.create_table(
        'deepblue_user_usage',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('date', sa.Date(), nullable=False, index=True),
        sa.Column('message_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('input_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('output_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('tool_calls_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('off_topic_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'date', name='uq_deepblue_user_date'),
    )

    # Per-message logs
    op.create_table(
        'deepblue_message_logs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('conversation_id', sa.String(36), nullable=True, index=True),
        sa.Column('message_index', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('input_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('output_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('tool_calls_made', sa.Text(), nullable=True),
        sa.Column('tool_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('user_prompt_hash', sa.String(32), nullable=True, index=True),
        sa.Column('user_prompt_length', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('response_length', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('category', sa.String(30), nullable=False, server_default='unknown', index=True),
        sa.Column('off_topic_detected', sa.Boolean(), nullable=False, server_default='false', index=True),
        sa.Column('model_used', sa.String(20), nullable=False, server_default='fast'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), index=True),
    )

    # Monthly usage rollup (preserves cost data beyond conversation retention)
    op.create_table(
        'deepblue_usage_monthly',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('month', sa.Integer(), nullable=False),
        sa.Column('conversations_created', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('messages_sent', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_input_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_output_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_cost_usd_estimated', sa.Float(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('organization_id', 'user_id', 'year', 'month', name='uq_deepblue_monthly'),
    )

    # Org-level quota config
    op.add_column('organizations', sa.Column('deepblue_user_daily_input_tokens', sa.Integer(), nullable=False, server_default='500000'))
    op.add_column('organizations', sa.Column('deepblue_user_daily_output_tokens', sa.Integer(), nullable=False, server_default='100000'))
    op.add_column('organizations', sa.Column('deepblue_user_monthly_input_tokens', sa.Integer(), nullable=False, server_default='5000000'))
    op.add_column('organizations', sa.Column('deepblue_user_monthly_output_tokens', sa.Integer(), nullable=False, server_default='1000000'))
    op.add_column('organizations', sa.Column('deepblue_org_monthly_input_tokens', sa.BigInteger(), nullable=False, server_default='50000000'))
    op.add_column('organizations', sa.Column('deepblue_org_monthly_output_tokens', sa.BigInteger(), nullable=False, server_default='10000000'))
    op.add_column('organizations', sa.Column('deepblue_rate_limit_per_minute', sa.Integer(), nullable=False, server_default='30'))

    # Conversation management columns
    op.add_column('deepblue_conversations', sa.Column('visibility', sa.String(20), nullable=False, server_default='private'))
    op.add_column('deepblue_conversations', sa.Column('pinned', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('deepblue_conversations', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('deepblue_conversations', sa.Column('shared_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('deepblue_conversations', sa.Column('shared_by', sa.String(36), nullable=True))


def downgrade() -> None:
    op.drop_column('deepblue_conversations', 'shared_by')
    op.drop_column('deepblue_conversations', 'shared_at')
    op.drop_column('deepblue_conversations', 'deleted_at')
    op.drop_column('deepblue_conversations', 'pinned')
    op.drop_column('deepblue_conversations', 'visibility')
    op.drop_column('organizations', 'deepblue_rate_limit_per_minute')
    op.drop_column('organizations', 'deepblue_org_monthly_output_tokens')
    op.drop_column('organizations', 'deepblue_org_monthly_input_tokens')
    op.drop_column('organizations', 'deepblue_user_monthly_output_tokens')
    op.drop_column('organizations', 'deepblue_user_monthly_input_tokens')
    op.drop_column('organizations', 'deepblue_user_daily_output_tokens')
    op.drop_column('organizations', 'deepblue_user_daily_input_tokens')
    op.drop_table('deepblue_usage_monthly')
    op.drop_table('deepblue_message_logs')
    op.drop_table('deepblue_user_usage')
