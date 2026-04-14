"""migrate inbox_routing_rules and suppressed_email_senders into inbox_rules

Data migration. Old tables are preserved for rollback; they are dropped
later in Phase E of docs/inbox-rules-unification-plan.md (~30 days post-
deploy).

Idempotency: skips entirely if inbox_rules already has any row. Safe to
re-run.

Mapping:

inbox_routing_rules (action=block) → inbox_rules with action route_to_spam.
  The old `block` silently dropped emails; patched 2026-04-13 to route to
  Spam. We preserve the Spam-routing semantic via the new explicit action.

inbox_routing_rules (action=route) → inbox_rules with assign_category +
  set_visibility actions.

suppressed_email_senders → inbox_rules at priority 200. Emits
  suppress_contact_prompt plus optional assign_tag / assign_folder.

Revision ID: f8f870f74d15
Revises: 42b365088c46
Create Date: 2026-04-14 03:56:22.251630

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'f8f870f74d15'
down_revision: Union[str, None] = '42b365088c46'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    existing = conn.exec_driver_sql("SELECT COUNT(*) FROM inbox_rules").scalar() or 0
    if existing > 0:
        # Already migrated — don't duplicate on re-run.
        return

    # inbox_routing_rules → inbox_rules
    conn.exec_driver_sql("""
        INSERT INTO inbox_rules (
            id, organization_id, name, priority, conditions, actions,
            is_active, created_by, created_at, updated_at
        )
        SELECT
            gen_random_uuid()::text,
            organization_id,
            'Migrated routing: ' || address_pattern,
            priority,
            jsonb_build_array(jsonb_build_object(
                'field', CASE match_field
                    WHEN 'from' THEN 'sender_email'
                    ELSE 'recipient_email'
                END,
                'operator', CASE match_type
                    WHEN 'exact' THEN 'equals'
                    ELSE 'contains'
                END,
                'value', address_pattern
            )),
            CASE action
                WHEN 'block' THEN jsonb_build_array(
                    jsonb_build_object('type', 'route_to_spam')
                )
                ELSE (
                    CASE WHEN category IS NOT NULL THEN
                        jsonb_build_array(jsonb_build_object(
                            'type', 'assign_category',
                            'params', jsonb_build_object('category', category)
                        ))
                    ELSE '[]'::jsonb END
                    ||
                    CASE WHEN required_permission IS NOT NULL THEN
                        jsonb_build_array(jsonb_build_object(
                            'type', 'set_visibility',
                            'params', jsonb_build_object('permission_slug', required_permission)
                        ))
                    ELSE '[]'::jsonb END
                )
            END,
            is_active,
            'migration',
            created_at,
            now()
        FROM inbox_routing_rules;
    """)

    # suppressed_email_senders → inbox_rules (priority 200, after routing)
    conn.exec_driver_sql("""
        INSERT INTO inbox_rules (
            id, organization_id, name, priority, conditions, actions,
            is_active, created_by, created_at, updated_at
        )
        SELECT
            gen_random_uuid()::text,
            organization_id,
            'Migrated tag: ' || email_pattern,
            200,
            jsonb_build_array(jsonb_build_object(
                'field', CASE
                    WHEN email_pattern LIKE '*@%%' THEN 'sender_domain'
                    ELSE 'sender_email'
                END,
                'operator', CASE
                    WHEN email_pattern LIKE '*@%%' THEN 'matches'
                    ELSE 'equals'
                END,
                'value', email_pattern
            )),
            jsonb_build_array(jsonb_build_object('type', 'suppress_contact_prompt'))
            ||
            CASE WHEN reason IS NOT NULL THEN
                jsonb_build_array(jsonb_build_object(
                    'type', 'assign_tag',
                    'params', jsonb_build_object('tag', reason)
                ))
            ELSE '[]'::jsonb END
            ||
            CASE WHEN folder_id IS NOT NULL THEN
                jsonb_build_array(jsonb_build_object(
                    'type', 'assign_folder',
                    'params', jsonb_build_object('folder_id', folder_id)
                ))
            ELSE '[]'::jsonb END,
            true,
            COALESCE(created_by, 'migration'),
            created_at,
            now()
        FROM suppressed_email_senders;
    """)


def downgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql("DELETE FROM inbox_rules WHERE created_by = 'migration'")
