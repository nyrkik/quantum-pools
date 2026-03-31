"""add_job_invoices_junction_table

Revision ID: f716b1f090ce
Revises: 02ff315a3abc
Create Date: 2026-03-31 14:49:02.203471

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f716b1f090ce'
down_revision: Union[str, None] = '02ff315a3abc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create junction table
    op.create_table('job_invoices',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('action_id', sa.String(length=36), nullable=False),
        sa.Column('invoice_id', sa.String(length=36), nullable=False),
        sa.Column('linked_by', sa.String(length=200), nullable=True),
        sa.Column('linked_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['action_id'], ['agent_actions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_job_invoices_action_id'), 'job_invoices', ['action_id'], unique=False)
    op.create_index(op.f('ix_job_invoices_invoice_id'), 'job_invoices', ['invoice_id'], unique=False)

    # Migrate existing agent_actions.invoice_id data to junction table
    op.execute("""
        INSERT INTO job_invoices (id, action_id, invoice_id, linked_at)
        SELECT gen_random_uuid()::text, id, invoice_id, COALESCE(created_at, NOW())
        FROM agent_actions
        WHERE invoice_id IS NOT NULL
    """)

    # Drop the old FK column
    op.drop_index('ix_agent_actions_invoice_id', table_name='agent_actions')
    op.drop_constraint('agent_actions_invoice_id_fkey', 'agent_actions', type_='foreignkey')
    op.drop_column('agent_actions', 'invoice_id')


def downgrade() -> None:
    # Restore invoice_id column
    op.add_column('agent_actions', sa.Column('invoice_id', sa.VARCHAR(length=36), nullable=True))
    op.create_foreign_key('agent_actions_invoice_id_fkey', 'agent_actions', 'invoices', ['invoice_id'], ['id'])
    op.create_index('ix_agent_actions_invoice_id', 'agent_actions', ['invoice_id'])

    # Migrate data back (first link only)
    op.execute("""
        UPDATE agent_actions aa
        SET invoice_id = ji.invoice_id
        FROM (SELECT DISTINCT ON (action_id) action_id, invoice_id FROM job_invoices ORDER BY action_id, linked_at) ji
        WHERE aa.id = ji.action_id
    """)

    op.drop_index(op.f('ix_job_invoices_invoice_id'), table_name='job_invoices')
    op.drop_index(op.f('ix_job_invoices_action_id'), table_name='job_invoices')
    op.drop_table('job_invoices')
