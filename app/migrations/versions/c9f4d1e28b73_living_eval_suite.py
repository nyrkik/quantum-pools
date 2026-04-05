"""Living eval suite — eval prompts table + gap promotion column

Revision ID: c9f4d1e28b73
Revises: b8e3f1a72c05
Create Date: 2026-04-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9f4d1e28b73'
down_revision: str = 'b8e3f1a72c05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'deepblue_eval_prompts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('prompt_key', sa.String(100), nullable=False),
        sa.Column('prompt_text', sa.Text(), nullable=False),
        sa.Column('source', sa.String(30), nullable=False, server_default='manual'),
        sa.Column('max_turns', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('expected_tools', sa.Text(), nullable=True),
        sa.Column('expected_tools_any', sa.Text(), nullable=True),
        sa.Column('expected_off_topic', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('expected_no_tools_required', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('must_not_contain', sa.Text(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('consecutive_passes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_passed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reasoning', sa.Text(), nullable=True),
        sa.Column('source_id', sa.String(36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_eval_prompts_org_key', 'deepblue_eval_prompts', ['organization_id', 'prompt_key'], unique=True)

    op.add_column('deepblue_knowledge_gaps', sa.Column('promoted_to_eval', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('deepblue_knowledge_gaps', 'promoted_to_eval')
    op.drop_index('ix_eval_prompts_org_key', table_name='deepblue_eval_prompts')
    op.drop_table('deepblue_eval_prompts')
