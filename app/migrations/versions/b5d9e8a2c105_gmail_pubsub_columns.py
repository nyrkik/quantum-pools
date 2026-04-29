"""gmail pub/sub push columns on email_integrations

Revision ID: b5d9e8a2c105
Revises: a3c5e7f8d904
Create Date: 2026-04-29

Adds the per-integration columns needed for Gmail's push-notification
mode (`users.watch` → Cloud Pub/Sub topic → our webhook). Polling stays
as a fallback during the initial cutover window and gets ripped once
push is confirmed reliable.

- pubsub_topic_name: full path "projects/{proj}/topics/{topic}" we
  passed to users.watch. NULL = polling-only integration.
- pubsub_subscription_name: full path of the push subscription. Stored
  for visibility / future stop-watch + recreate flows.
- watch_expires_at: Google returns a hard expiry (max 7 days). The
  daily refresh job uses this to schedule the next call.
- last_pubsub_push_at: heartbeat — alert if absent for >6h during
  business hours, signals push silently broke.
- last_watch_refresh_at: when we last called users.watch successfully.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b5d9e8a2c105"
down_revision: Union[str, None] = "a3c5e7f8d904"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "email_integrations",
        sa.Column("pubsub_topic_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "email_integrations",
        sa.Column("pubsub_subscription_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "email_integrations",
        sa.Column("watch_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "email_integrations",
        sa.Column("last_pubsub_push_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "email_integrations",
        sa.Column("last_watch_refresh_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("email_integrations", "last_watch_refresh_at")
    op.drop_column("email_integrations", "last_pubsub_push_at")
    op.drop_column("email_integrations", "watch_expires_at")
    op.drop_column("email_integrations", "pubsub_subscription_name")
    op.drop_column("email_integrations", "pubsub_topic_name")
