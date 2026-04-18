"""platform_events_phase1

Creates the instrumentation layer tables:
  - platform_events (partitioned by month on created_at)
  - data_deletion_requests (CCPA audit trail)
  - organizations.event_retention_days column

See docs/ai-platform-phase-1.md §4 for the full design rationale,
docs/event-taxonomy.md for the schema/retention/privacy contract.

Revision ID: 7cc81fcba9da
Revises: 45d4533c47b9
Create Date: 2026-04-18 07:23:20.142955

"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7cc81fcba9da'
down_revision: Union[str, None] = '45d4533c47b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # ---------------------------------------------------------------------
    # 1. organizations.event_retention_days
    # ---------------------------------------------------------------------
    # Default 3 years (1095 days) per DNA rule #1 (build for 1000th customer).
    # Dogfood orgs (Sapphire) get 10 years via a targeted UPDATE below —
    # Brian confirmed 2026-04-18.
    op.add_column(
        "organizations",
        sa.Column(
            "event_retention_days",
            sa.Integer(),
            nullable=False,
            server_default="1095",
        ),
    )
    # Sapphire dogfood retention = 10 years
    bind.execute(
        sa.text(
            "UPDATE organizations SET event_retention_days = 3650 "
            "WHERE slug = 'sapphire'"
        )
    )

    # ---------------------------------------------------------------------
    # 2. platform_events — partitioned parent table
    # ---------------------------------------------------------------------
    # Partitioning requires that the partition key be part of the primary
    # key; hence composite PK (id, created_at).
    bind.execute(sa.text("""
        CREATE TABLE platform_events (
            id VARCHAR(36) NOT NULL,
            organization_id VARCHAR(36),
            actor_user_id VARCHAR(36),
            acting_as_user_id VARCHAR(36),
            view_as_role VARCHAR(30),
            actor_type VARCHAR(10) NOT NULL,
            actor_agent_type VARCHAR(50),
            event_type VARCHAR(100) NOT NULL,
            level VARCHAR(20) NOT NULL,
            entity_refs JSONB NOT NULL DEFAULT '{}'::jsonb,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            request_id VARCHAR(36),
            session_id VARCHAR(36),
            job_run_id VARCHAR(36),
            client_emit_id VARCHAR(36),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT platform_events_pkey PRIMARY KEY (id, created_at),
            CONSTRAINT platform_events_actor_type_chk
                CHECK (actor_type IN ('user', 'system', 'agent')),
            CONSTRAINT platform_events_level_chk
                CHECK (level IN ('user_action', 'system_action', 'agent_action', 'error'))
        ) PARTITION BY RANGE (created_at)
    """))

    # ---------------------------------------------------------------------
    # 3. Indexes on the parent — propagate to all partitions automatically
    # ---------------------------------------------------------------------
    bind.execute(sa.text("""
        CREATE INDEX idx_platform_events_org_created
            ON platform_events (organization_id, created_at DESC)
    """))
    bind.execute(sa.text("""
        CREATE INDEX idx_platform_events_type_created
            ON platform_events (event_type, created_at DESC)
    """))
    bind.execute(sa.text("""
        CREATE INDEX idx_platform_events_entity_refs
            ON platform_events USING GIN (entity_refs)
    """))
    # NOTE: Postgres partitioned tables require unique indexes to include the
    # partition key (created_at). A composite unique index on
    # (organization_id, client_emit_id, created_at) doesn't give us the
    # idempotency semantics we want — retries have different created_at.
    #
    # Solution: plain (non-unique) index for lookup, and the emit helper
    # does app-level dedup (SELECT-then-INSERT). Small race window is
    # acceptable per our "rare duplicates OK" philosophy in the spec.
    bind.execute(sa.text("""
        CREATE INDEX idx_platform_events_client_emit_id
            ON platform_events (organization_id, client_emit_id)
            WHERE client_emit_id IS NOT NULL
    """))
    bind.execute(sa.text("""
        CREATE INDEX idx_platform_events_error_created
            ON platform_events (created_at DESC)
            WHERE level = 'error'
    """))

    # ---------------------------------------------------------------------
    # 4. Initial partitions — current month + 3 future months
    #    Subsequent months are created by the APScheduler partition_manager
    #    job (see src/services/events/partition_manager.py).
    # ---------------------------------------------------------------------
    bind.execute(sa.text("""
        DO $$
        DECLARE
            start_date DATE := DATE_TRUNC('month', NOW())::DATE;
            partition_date DATE;
            partition_name TEXT;
            i INT;
        BEGIN
            FOR i IN 0..3 LOOP
                partition_date := start_date + (i || ' months')::INTERVAL;
                partition_name := 'platform_events_' || TO_CHAR(partition_date, 'YYYY_MM');
                EXECUTE FORMAT(
                    'CREATE TABLE IF NOT EXISTS %I PARTITION OF platform_events
                     FOR VALUES FROM (%L) TO (%L)',
                    partition_name,
                    partition_date,
                    partition_date + INTERVAL '1 month'
                );
            END LOOP;
        END $$
    """))

    # ---------------------------------------------------------------------
    # 5. data_deletion_requests — CCPA audit trail
    #    Intentionally NOT in platform_events. Putting purge-request records
    #    into the same table whose rows we're purging defeats the contract.
    # ---------------------------------------------------------------------
    op.create_table(
        "data_deletion_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("requested_by_user_id", sa.String(36), nullable=True),
        sa.Column("target_user_id", sa.String(36), nullable=False),
        sa.Column("target_type", sa.String(30), nullable=False),
        sa.Column("scope", sa.dialects.postgresql.JSONB, nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_rows_affected", sa.Integer, nullable=True),
        sa.Column("note", sa.Text, nullable=True),
    )
    op.create_index(
        "idx_ddr_target",
        "data_deletion_requests",
        ["target_user_id", sa.text("requested_at DESC")],
    )


def downgrade() -> None:
    # Partitions are dropped implicitly when the parent is dropped.
    op.drop_index("idx_ddr_target", table_name="data_deletion_requests")
    op.drop_table("data_deletion_requests")

    op.execute("DROP TABLE IF EXISTS platform_events CASCADE")

    op.drop_column("organizations", "event_retention_days")
