"""Seed permissions, presets, and preset-permission mappings."""

import asyncio
import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from sqlalchemy import select, delete
from src.core.database import get_session_maker, get_engine
from src.models.permission import Permission
from src.models.permission_preset import PermissionPreset
from src.models.preset_permission import PresetPermission


# ── Permission definitions ──────────────────────────────────────────
# (resource, action, description)
PERMISSIONS = [
    # customers
    ("customers", "view", "View customer records"),
    ("customers", "create", "Create new customers"),
    ("customers", "edit", "Edit customer details"),
    ("customers", "delete", "Delete customers"),
    ("customers", "view_rates", "View customer service rates"),
    ("customers", "edit_rates", "Edit customer service rates"),
    ("customers", "view_balance", "View customer account balance"),
    # properties
    ("properties", "view", "View property records"),
    ("properties", "create", "Create new properties"),
    ("properties", "edit", "Edit property details"),
    ("properties", "delete", "Delete properties"),
    ("properties", "view_dimensions", "View pool dimensions"),
    ("properties", "view_difficulty", "View difficulty scoring"),
    # water_features
    ("water_features", "view", "View water features"),
    ("water_features", "create", "Create water features"),
    ("water_features", "edit", "Edit water features"),
    ("water_features", "delete", "Delete water features"),
    ("water_features", "measure", "Use pool measurement tool"),
    # routes
    ("routes", "view", "View route schedules"),
    ("routes", "manage", "Create and manage routes"),
    # visits
    ("visits", "view", "View service visits"),
    ("visits", "create", "Log new visits"),
    ("visits", "edit", "Edit visit records"),
    ("visits", "delete", "Delete visit records"),
    # chemicals
    ("chemicals", "view", "View chemical readings"),
    ("chemicals", "create", "Log chemical readings"),
    ("chemicals", "edit", "Edit chemical readings"),
    # invoices
    ("invoices", "view", "View invoices"),
    ("invoices", "create", "Create invoices"),
    ("invoices", "edit", "Edit invoices"),
    ("invoices", "delete", "Delete invoices"),
    # payments
    ("payments", "view", "View payment records"),
    ("payments", "create", "Record payments"),
    # techs
    ("techs", "view", "View technician list"),
    ("techs", "manage", "Add/edit/remove technicians"),
    # profitability
    ("profitability", "view", "View profitability dashboard"),
    ("profitability", "edit_settings", "Edit cost settings and difficulty"),
    # satellite
    ("satellite", "view", "View satellite analysis"),
    ("satellite", "analyze", "Run satellite analysis"),
    # emd
    ("emd", "view", "View EMD inspection data"),
    ("emd", "manage", "Manage EMD scraping and lookups"),
    # chemical_costs
    ("chemical_costs", "view", "View chemical cost profiles"),
    ("chemical_costs", "edit", "Edit chemical cost profiles"),
    # inbox
    ("inbox", "view", "View agent inbox"),
    ("inbox", "manage", "Manage inbox threads and actions"),
    # jobs
    ("jobs", "view", "View jobs"),
    ("jobs", "create", "Create jobs"),
    ("jobs", "edit", "Edit jobs"),
    ("jobs", "manage", "Manage all jobs and assignments"),
    # team
    ("team", "view", "View team members"),
    ("team", "manage", "Invite, edit, and remove team members"),
    # settings
    ("settings", "view", "View organization settings"),
    ("settings", "edit", "Edit organization settings"),
    # branding
    ("branding", "view", "View branding settings"),
    ("branding", "edit", "Edit branding settings"),
    # billing
    ("billing", "view", "View billing and subscriptions"),
    ("billing", "manage", "Manage billing and subscriptions"),
    # agent_ops
    ("agent_ops", "view", "View AI agent operations"),
    ("agent_ops", "manage", "Manage AI agent configuration"),
    # notifications
    ("notifications", "view", "View notifications"),
    # workflow (Phase 4)
    ("workflow", "manage_config", "Configure post-creation handlers for new jobs"),
]


# ── Preset definitions ──────────────────────────────────────────────
PRESETS = [
    ("owner", "Full Access", "Complete control over all features and settings", 0),
    ("admin", "Admin", "Full operational access; limited settings and billing", 1),
    ("manager", "Standard", "Day-to-day operations without financial access", 2),
    ("technician", "Limited", "Field tech access — own routes, visits, and readings", 3),
    ("readonly", "View Only", "Read-only access across the platform", 4),
]


# ── Preset-permission mappings ──────────────────────────────────────
# Format: {preset_slug: [(permission_slug, scope), ...]}

# Build all permission slugs for quick reference
_ALL_SLUGS = [f"{r}.{a}" for r, a, _ in PERMISSIONS]

PRESET_PERMISSIONS: dict[str, list[tuple[str, str]]] = {}

# owner — ALL at scope 'all'
PRESET_PERMISSIONS["owner"] = [(s, "all") for s in _ALL_SLUGS]

# admin — everything except settings.edit, agent_ops.manage, billing.manage
_admin_excluded = {"settings.edit", "agent_ops.manage", "billing.manage"}
PRESET_PERMISSIONS["admin"] = [(s, "all") for s in _ALL_SLUGS if s not in _admin_excluded]

# manager
PRESET_PERMISSIONS["manager"] = [
    # customers
    ("customers.view", "all"),
    ("customers.create", "all"),
    ("customers.edit", "all"),
    ("customers.delete", "all"),
    # properties
    ("properties.view", "all"),
    ("properties.create", "all"),
    ("properties.edit", "all"),
    ("properties.delete", "all"),
    ("properties.view_dimensions", "all"),
    ("properties.view_difficulty", "all"),
    # water_features
    ("water_features.view", "all"),
    ("water_features.create", "all"),
    ("water_features.edit", "all"),
    ("water_features.delete", "all"),
    ("water_features.measure", "all"),
    # routes
    ("routes.view", "all"),
    ("routes.manage", "all"),
    # visits
    ("visits.view", "all"),
    ("visits.create", "all"),
    ("visits.edit", "all"),
    ("visits.delete", "all"),
    # chemicals
    ("chemicals.view", "all"),
    ("chemicals.create", "all"),
    ("chemicals.edit", "all"),
    # techs
    ("techs.view", "all"),
    # profitability
    ("profitability.view", "all"),
    # satellite
    ("satellite.view", "all"),
    ("satellite.analyze", "all"),
    # inspections
    ("inspection.view", "all"),
    ("inspection.manage", "all"),
    # chemical_costs
    ("chemical_costs.view", "all"),
    # jobs
    ("jobs.view", "all"),
    ("jobs.create", "all"),
    ("jobs.edit", "all"),
    ("jobs.manage", "all"),
    # notifications
    ("notifications.view", "all"),
]

# technician
PRESET_PERMISSIONS["technician"] = [
    ("customers.view", "own"),
    ("properties.view", "own"),
    ("water_features.view", "own"),
    ("routes.view", "own"),
    ("visits.view", "own"),
    ("visits.create", "own"),
    ("visits.edit", "own"),
    ("chemicals.view", "own"),
    ("chemicals.create", "own"),
    ("chemicals.edit", "own"),
    ("techs.view", "all"),
    ("inspection.view", "all"),
    ("jobs.view", "own"),
    ("jobs.edit", "own"),
    ("notifications.view", "all"),
]

# readonly — *.view on most resources plus a few extras
_readonly_view_resources = [
    "customers", "properties", "water_features", "routes", "visits",
    "chemicals", "invoices", "payments", "techs", "profitability",
    "satellite", "emd", "chemical_costs", "jobs", "notifications",
]
PRESET_PERMISSIONS["readonly"] = [
    (f"{r}.view", "all") for r in _readonly_view_resources
] + [
    ("customers.view_rates", "all"),
    ("customers.view_balance", "all"),
    ("properties.view_dimensions", "all"),
    ("properties.view_difficulty", "all"),
]


async def seed():
    engine = get_engine()
    session_maker = get_session_maker()

    async with session_maker() as db:
        # ── 1. Upsert permissions ───────────────────────────────────
        existing_result = await db.execute(select(Permission))
        existing_perms = {p.slug: p for p in existing_result.scalars().all()}

        perm_by_slug: dict[str, str] = {}  # slug -> id
        sort_order = 0
        for resource, action, description in PERMISSIONS:
            slug = f"{resource}.{action}"
            sort_order += 10
            if slug in existing_perms:
                p = existing_perms[slug]
                p.description = description
                p.sort_order = sort_order
                perm_by_slug[slug] = p.id
            else:
                pid = str(uuid.uuid4())
                p = Permission(
                    id=pid, slug=slug, resource=resource, action=action,
                    description=description, sort_order=sort_order,
                )
                db.add(p)
                perm_by_slug[slug] = pid

        await db.flush()
        print(f"  Permissions: {len(perm_by_slug)} total")

        # ── 2. Upsert presets ───────────────────────────────────────
        existing_preset_result = await db.execute(select(PermissionPreset))
        existing_presets = {p.slug: p for p in existing_preset_result.scalars().all()}

        preset_by_slug: dict[str, str] = {}  # slug -> id
        for slug, name, description, order in PRESETS:
            if slug in existing_presets:
                p = existing_presets[slug]
                p.name = name
                p.description = description
                p.sort_order = order
                preset_by_slug[slug] = p.id
            else:
                pid = str(uuid.uuid4())
                p = PermissionPreset(
                    id=pid, slug=slug, name=name, description=description,
                    is_system=True, sort_order=order,
                )
                db.add(p)
                preset_by_slug[slug] = pid

        await db.flush()
        print(f"  Presets: {len(preset_by_slug)} total")

        # ── 3. Rebuild preset_permissions ───────────────────────────
        # Delete all existing and re-insert (idempotent)
        await db.execute(delete(PresetPermission))
        await db.flush()

        count = 0
        for preset_slug, perm_list in PRESET_PERMISSIONS.items():
            preset_id = preset_by_slug[preset_slug]
            for perm_slug, scope in perm_list:
                perm_id = perm_by_slug.get(perm_slug)
                if not perm_id:
                    print(f"  WARNING: permission '{perm_slug}' not found, skipping")
                    continue
                db.add(PresetPermission(
                    preset_id=preset_id, permission_id=perm_id, scope=scope,
                ))
                count += 1

        await db.commit()
        print(f"  Preset-permissions: {count} mappings")
        print("Done.")


if __name__ == "__main__":
    print("Seeding permissions...")
    asyncio.run(seed())
