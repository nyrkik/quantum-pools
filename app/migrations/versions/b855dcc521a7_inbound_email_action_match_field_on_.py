"""Inbound email: action+match_field on rules, org email config

Revision ID: b855dcc521a7
Revises: 8549932b3737
Create Date: 2026-03-27 07:09:15.564709

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b855dcc521a7'
down_revision: Union[str, None] = '8549932b3737'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Block rules to seed — migrated from hardcoded AUTO_SENDER_DOMAINS
_BLOCK_DOMAINS = [
    # Vendor notifications
    "scppool.com", "pool360.com",
    # Financial
    "americanexpress.com", "welcome.americanexpress.com",
    # Marketing / newsletters / SaaS
    "getskimmer.com", "mail.bubble.io", "send.zapier.com", "mail.zapier.com",
    "mailchimp.com", "sendgrid.net", "constantcontact.com",
    "hubspot.com", "mailgun.net",
    "mail.replit.com", "lovable.dev", "flutterflow.io", "signwell.com",
    "mail.anthropic.com", "email.anthropic.com", "email2.anthropic.com",
    "email.claude.com", "email.openai.com",
    "snyk.io", "notification.bubble.io", "bubble.io",
    "accounts.google.com", "google.com", "googlecloud.com",
    "devprospectscape.com", "teksystems.com", "link.com",
    "yardi.com",
]

_BLOCK_PREFIXES = [
    "notifications@", "alerts@", "updates@", "newsletter@", "events@",
    "noreply@", "no-reply@", "donotreply@", "mailer-daemon@",
]


def upgrade() -> None:
    # Add new columns with server defaults so existing rows get values
    op.add_column('inbox_routing_rules', sa.Column('action', sa.String(length=20), server_default='route', nullable=False))
    op.add_column('inbox_routing_rules', sa.Column('match_field', sa.String(length=10), server_default='to', nullable=False))

    # Organization inbound email config
    op.add_column('organizations', sa.Column('inbound_email_address', sa.String(length=255), nullable=True))
    op.add_column('organizations', sa.Column('inbound_email_provider', sa.String(length=50), nullable=True))
    op.add_column('organizations', sa.Column('imap_host', sa.String(length=255), nullable=True))
    op.add_column('organizations', sa.Column('imap_user', sa.String(length=255), nullable=True))
    op.add_column('organizations', sa.Column('imap_password_encrypted', sa.Text(), nullable=True))

    # Seed block rules for all active orgs
    conn = op.get_bind()
    orgs = conn.execute(sa.text("SELECT id FROM organizations WHERE is_active = true")).fetchall()

    for (org_id,) in orgs:
        priority = 0
        # Domain blocks (match_type=contains on sender domain)
        for domain in _BLOCK_DOMAINS:
            conn.execute(
                sa.text(
                    "INSERT INTO inbox_routing_rules "
                    "(id, organization_id, address_pattern, match_type, action, match_field, priority, is_active, created_at) "
                    "VALUES (:id, :org_id, :pattern, 'contains', 'block', 'from', :priority, true, NOW())"
                ),
                {"id": str(uuid.uuid4()), "org_id": org_id, "pattern": domain, "priority": priority},
            )
            priority += 1

        # Prefix blocks (match_type=contains on sender prefix)
        for prefix in _BLOCK_PREFIXES:
            conn.execute(
                sa.text(
                    "INSERT INTO inbox_routing_rules "
                    "(id, organization_id, address_pattern, match_type, action, match_field, priority, is_active, created_at) "
                    "VALUES (:id, :org_id, :pattern, 'contains', 'block', 'from', :priority, true, NOW())"
                ),
                {"id": str(uuid.uuid4()), "org_id": org_id, "pattern": prefix, "priority": priority},
            )
            priority += 1

        # Set existing org to provider='imap'
        conn.execute(
            sa.text("UPDATE organizations SET inbound_email_provider = 'imap' WHERE id = :org_id"),
            {"org_id": org_id},
        )

    # Set Sapphire's inbound_email_address (first org — framework only, not active yet)
    if orgs:
        conn.execute(
            sa.text(
                "UPDATE organizations SET inbound_email_address = :addr WHERE id = :org_id"
            ),
            {"addr": "inbox-sapphire@mail.quantumpoolspro.com", "org_id": orgs[0][0]},
        )


def downgrade() -> None:
    op.drop_column('organizations', 'imap_password_encrypted')
    op.drop_column('organizations', 'imap_user')
    op.drop_column('organizations', 'imap_host')
    op.drop_column('organizations', 'inbound_email_provider')
    op.drop_column('organizations', 'inbound_email_address')

    # Remove seeded block rules
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM inbox_routing_rules WHERE action = 'block' AND match_field = 'from'"))

    op.drop_column('inbox_routing_rules', 'match_field')
    op.drop_column('inbox_routing_rules', 'action')
