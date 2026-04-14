"""add internal_thread_count and deepblue_conversation_count to service_cases

Revision ID: 6ca65f3faef6
Revises: e1b72079af43
Create Date: 2026-04-14 09:13:11.786322

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '6ca65f3faef6'
down_revision: Union[str, None] = 'e1b72079af43'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "service_cases",
        sa.Column("internal_thread_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "service_cases",
        sa.Column("deepblue_conversation_count", sa.Integer(), server_default="0", nullable=False),
    )

    # Backfill counts from existing case_id FKs on child tables.
    op.execute("""
        UPDATE service_cases sc SET internal_thread_count = sub.c
        FROM (
            SELECT case_id, COUNT(*) AS c FROM internal_threads
            WHERE case_id IS NOT NULL GROUP BY case_id
        ) sub
        WHERE sc.id = sub.case_id
    """)
    op.execute("""
        UPDATE service_cases sc SET deepblue_conversation_count = sub.c
        FROM (
            SELECT case_id, COUNT(*) AS c FROM deepblue_conversations
            WHERE case_id IS NOT NULL GROUP BY case_id
        ) sub
        WHERE sc.id = sub.case_id
    """)


def downgrade() -> None:
    op.drop_column("service_cases", "deepblue_conversation_count")
    op.drop_column("service_cases", "internal_thread_count")
