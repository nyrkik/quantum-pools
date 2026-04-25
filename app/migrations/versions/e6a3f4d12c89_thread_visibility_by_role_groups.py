"""switch thread visibility from a permission slug to a list of role slugs

Pre-migration `agent_threads.visibility_permission` held a single
`Permission.slug` (e.g. `inbox.see_billing`). Anyone holding that
permission saw the thread. The rule-editor UI exposed the raw slug
catalog, which is engineer vocabulary — Brian flagged it as confusing
and wanted role-group checkboxes instead.

New shape: `agent_threads.visibility_role_slugs JSONB` — an array of
role slugs (built-in: owner/admin/manager/technician/readonly; custom:
whatever the org named it). A user is in the audience iff their
effective role slug appears in the list (NULL = everyone, like before).

Backfill rules:
  * threads with non-null visibility_permission → snapshot into
    visibility_role_slugs as the UNION of role slugs that grant that
    permission AT MIGRATION TIME (frozen, so future permission grants
    don't silently widen the audience of a historical thread).
  * inbox_rules with set_visibility actions → same translation in the
    JSONB actions blob.

The old `visibility_permission` column is dropped in the same
migration. Code switches over in the same deploy. No backward-compat
shim — set_visibility actions now require a role_slugs param.

Revision ID: e6a3f4d12c89
Revises: d4f12b8e09a7
"""
from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "e6a3f4d12c89"
down_revision: Union[str, None] = "d4f12b8e09a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _roles_granting_permission(conn, org_id: str, perm_slug: str) -> list[str]:
    """Return the union of role slugs (built-in + custom) that grant the
    given permission for this org, snapshotted at this moment.
    """
    # Built-in roles via PermissionPreset → PresetPermission → Permission.
    # Preset.slug aligns with built-in OrgRole values: owner, admin, etc.
    builtin_rows = conn.execute(sa.text("""
        SELECT DISTINCT pp.slug
        FROM permission_presets pp
        JOIN preset_permissions ppm ON ppm.preset_id = pp.id
        JOIN permissions p ON p.id = ppm.permission_id
        WHERE p.slug = :slug
    """), {"slug": perm_slug}).fetchall()

    custom_rows = conn.execute(sa.text("""
        SELECT DISTINCT r.slug
        FROM org_roles r
        JOIN org_role_permissions orp ON orp.org_role_id = r.id
        JOIN permissions p ON p.id = orp.permission_id
        WHERE r.organization_id = :org_id AND p.slug = :slug AND r.is_active = TRUE
    """), {"org_id": org_id, "slug": perm_slug}).fetchall()

    slugs: set[str] = {r[0] for r in builtin_rows}
    slugs.update(r[0] for r in custom_rows)
    return sorted(slugs)


def upgrade() -> None:
    op.add_column(
        "agent_threads",
        sa.Column("visibility_role_slugs", JSONB, nullable=True),
    )

    conn = op.get_bind()

    # Backfill threads.
    thread_rows = conn.execute(sa.text("""
        SELECT id, organization_id, visibility_permission
        FROM agent_threads
        WHERE visibility_permission IS NOT NULL
    """)).fetchall()

    for tid, org_id, perm in thread_rows:
        slugs = _roles_granting_permission(conn, org_id, perm)
        if not slugs:
            # No role grants this permission today — leave the column null
            # (= everyone sees it) rather than locking the thread out from
            # everyone. Better failure mode for a stale rule than silent
            # invisibility.
            continue
        conn.execute(sa.text("""
            UPDATE agent_threads SET visibility_role_slugs = CAST(:s AS JSONB)
            WHERE id = :id
        """), {"s": json.dumps(slugs), "id": tid})

    # Backfill inbox_rules: any set_visibility action with permission_slug
    # gets translated to role_slugs (snapshot of which roles grant it now).
    rule_rows = conn.execute(sa.text("""
        SELECT id, organization_id, actions FROM inbox_rules
        WHERE actions::text LIKE '%set_visibility%'
    """)).fetchall()

    for rid, org_id, actions_jsonb in rule_rows:
        actions = actions_jsonb if isinstance(actions_jsonb, list) else json.loads(actions_jsonb)
        changed = False
        new_actions = []
        for a in actions:
            if a.get("type") == "set_visibility" and isinstance(a.get("params"), dict):
                params = dict(a["params"])
                slug = params.pop("permission_slug", None) or params.pop("slug", None)
                if slug:
                    role_slugs = _roles_granting_permission(conn, org_id, slug)
                    params["role_slugs"] = role_slugs
                    a = {**a, "params": params}
                    changed = True
            new_actions.append(a)
        if changed:
            conn.execute(sa.text("""
                UPDATE inbox_rules SET actions = CAST(:a AS JSONB) WHERE id = :id
            """), {"a": json.dumps(new_actions), "id": rid})

    # Drop the legacy column. Code is switching to visibility_role_slugs in
    # the same deploy.
    op.drop_column("agent_threads", "visibility_permission")


def downgrade() -> None:
    op.add_column(
        "agent_threads",
        sa.Column("visibility_permission", sa.String(80), nullable=True),
    )
    op.drop_column("agent_threads", "visibility_role_slugs")
