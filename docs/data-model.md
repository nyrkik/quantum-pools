# QuantumPools Data Model Reference

Last updated: 2026-04-07

## Overview

- **85 model classes** across 78 files (some files define multiple models)
- **3 additional models** defined outside `models/` (AgentLog, AgentEvalCase, AgentEvalResult in `services/agents/`)
- SQLAlchemy 2.0 async with `Mapped` / `mapped_column` throughout
- UUID string primary keys (`String(36)`, generated via `uuid.uuid4()`)
- Org-scoped multi-tenancy: nearly every model has `organization_id` FK to `organizations.id`
- All relationships default to `lazy="noload"` — explicit eager loading required
- Timestamps: `created_at` / `updated_at` (UTC) on most models
- 4 legacy alias files (`emd_*.py`) redirect to renamed `inspection_*` models

---

## Domain Groups

### Core

Platform identity, multi-tenancy, auth, and permissions.

| Model | Table | Purpose |
|-------|-------|---------|
| Organization | `organizations` | Tenant (pool service company) |
| User | `users` | Platform user account |
| OrganizationUser | `organization_users` | User-to-org membership with legacy role enum |
| UserSession | `user_sessions` | JWT refresh token tracking |
| Permission | `permissions` | 60-slug permission definitions |
| PermissionPreset | `permission_presets` | Named permission bundles (e.g. "Manager") |
| PresetPermission | `preset_permissions` | M2M: preset to permission |
| OrgRole | `org_roles` | Custom roles per org |
| OrgRolePermission | `org_role_permissions` | Permissions assigned to an org role |
| UserPermissionOverride | `user_permission_overrides` | Per-user permission grants/revokes |
| Feature | `features` | Subscribable product features |
| FeatureTier | `feature_tiers` | Tier levels within a feature (e.g. inspection tiers) |
| OrgSubscription | `org_subscriptions` | Org-to-feature subscription records |
| ServiceTier | `service_tiers` | Service level tiers (basic, premium, etc.) |
| RegionalDefault | `regional_defaults` | Region-specific default settings |
| GeocodeCache | `geocode_cache` | Address-to-coordinate cache (OSM/Google) |
| FeedbackItem | `feedback_items` | In-app user feedback/bug reports (FB-XXX) |

### Customers & Properties

Core business entities: who we serve and where.

| Model | Table | Purpose |
|-------|-------|---------|
| Customer | `customers` | Client record (commercial/residential) |
| CustomerContact | `customer_contacts` | Additional contacts per customer |
| Property | `properties` | Service location (address, coordinates, legacy pool fields) |
| WaterFeature | `water_features` | Body of water (pool, spa, fountain) per property — primary data entity for dimensions, equipment, service time |
| PropertyPhoto | `property_photos` | Photos of the property |
| PropertyAccessCode | `property_access_codes` | Gate codes, lock combos per property |
| PropertyDifficulty | `property_difficulties` | 12-factor difficulty scoring (shade, debris, access, etc.) |
| PropertyJurisdiction | `property_jurisdictions` | Links property/WF to bather load jurisdiction |
| BatherLoadJurisdiction | `bather_load_jurisdictions` | Jurisdiction-specific bather load calculation rules |

### Service Operations

Routing, visits, checklists, and technician management.

| Model | Table | Purpose |
|-------|-------|---------|
| Tech | `techs` | Field technician profile |
| Route | `routes` | Named route (day + tech) |
| RouteStop | `route_stops` | Ordered stop on a route (FK to property) |
| TempTechAssignment | `temp_tech_assignments` | Temporary tech reassignment for a property |
| Visit | `visits` | Single service visit to a property |
| VisitService | `visit_services` | M2M: services performed during a visit |
| VisitPhoto | `visit_photos` | Photos taken during a visit |
| VisitChecklistEntry | `visit_checklist_entries` | Completed checklist items for a visit |
| Service | `services` | Service type catalog (weekly clean, filter clean, etc.) |
| ServiceChecklistItem | `service_checklist_items` | Checklist template items per service type |
| ChemicalReading | `chemical_readings` | Water chemistry readings (pH, chlorine, etc.) |

### Financial

Invoicing, payments, estimates, and charges.

| Model | Table | Purpose |
|-------|-------|---------|
| Invoice | `invoices` | Customer invoice with status tracking |
| InvoiceLineItem | `invoice_line_items` | Individual line items on an invoice |
| InvoiceRevision | `invoice_revisions` | Audit trail of invoice changes |
| Payment | `payments` | Payment received against an invoice |
| ChargeTemplate | `charge_templates` | Reusable charge definitions (e.g. "Filter Clean $85") |
| VisitCharge | `visit_charges` | Ad-hoc charges from a visit |
| EstimateApproval | `estimate_approvals` | Customer estimate with approval/rejection tracking |
| JobInvoice | `job_invoices` | Links jobs (agent actions) to invoices |

### Email & Communication

Inbound/outbound email, internal messaging, notifications.

| Model | Table | Purpose |
|-------|-------|---------|
| AgentThread | `agent_threads` | Email conversation thread (inbound via Postmark) |
| AgentMessage | `agent_messages` | Individual email message in a thread |
| MessageAttachment | `message_attachments` | File attachments on agent messages |
| ThreadRead | `thread_reads` | Per-user read tracking for threads |
| InboxRoutingRule | `inbox_routing_rules` | Rules for auto-routing inbound email |
| BroadcastEmail | `broadcast_emails` | Bulk email campaigns |
| EmailTemplate | `email_templates` | Reusable email templates |
| InternalThread | `internal_threads` | Internal team discussion thread |
| InternalMessage | `internal_messages` | Message within an internal thread |
| Notification | `notifications` | In-app notification for a user |

### Service Cases

Unified case entity linking threads, jobs, and invoices.

| Model | Table | Purpose |
|-------|-------|---------|
| ServiceCase | `service_cases` | Parent case tying together threads, jobs, invoices, and internal threads for a customer issue |

### AI Agents & Jobs

Agent actions (jobs), AI learning, and observability.

| Model | Table | Purpose |
|-------|-------|---------|
| AgentAction | `agent_actions` | Job/task created by or for an agent (self-referencing `parent_action_id`) |
| AgentActionComment | `agent_action_comments` | Comments on a job |
| AgentActionTask | `agent_action_tasks` | Sub-tasks within a job |
| AgentCorrection | `agent_corrections` | Human corrections to AI outputs (learning data) |
| AgentLog | `agent_logs` | Agent execution observability logs (defined in `services/agents/observability.py`) |
| AgentEvalCase | `agent_eval_cases` | Eval test cases for agents (defined in `services/agents/evals.py`) |
| AgentEvalResult | `agent_eval_results` | Eval run results (defined in `services/agents/evals.py`) |

### DeepBlue (Field AI)

AI assistant for field operations.

| Model | Table | Purpose |
|-------|-------|---------|
| DeepBlueConversation | `deepblue_conversations` | Chat session with DeepBlue |
| DeepBlueMessageLog | `deepblue_message_logs` | Individual messages in a conversation |
| DeepBlueKnowledgeGap | `deepblue_knowledge_gaps` | Questions DeepBlue could not answer (training signal) |
| DeepBlueEvalPrompt | `deepblue_eval_prompts` | Evaluation prompts for DeepBlue quality |
| DeepBlueEvalRun | `deepblue_eval_runs` | Results of evaluation runs |
| DeepBlueUsageMonthly | `deepblue_usage_monthly` | Monthly aggregate usage stats |
| DeepBlueUserUsage | `deepblue_user_usage` | Per-user usage tracking |

### Equipment & Parts

Equipment lifecycle, parts catalog, vendors.

| Model | Table | Purpose |
|-------|-------|---------|
| EquipmentCatalog | `equipment_catalog` | Canonical equipment database (114 entries) |
| EquipmentItem | `equipment_items` | Installed equipment instance on a water feature |
| EquipmentEvent | `equipment_events` | Lifecycle events (install, repair, replace) |
| PartsCatalog | `parts_catalog` | Parts database (434 entries, linked to equipment) |
| PartPurchase | `part_purchases` | Purchase records for parts |
| Vendor | `vendors` | Supplier/vendor records |

### Profitability & Chemical Costs

Cost analysis and pricing optimization.

| Model | Table | Purpose |
|-------|-------|---------|
| OrgCostSettings | `org_cost_settings` | Org-wide cost defaults (labor rate, truck cost, overhead) |
| OrgChemicalPrices | `org_chemical_prices` | Org-level chemical pricing |
| ChemicalCostProfile | `chemical_cost_profiles` | Per-WF chemical cost profile |
| DimensionEstimate | `dimension_estimates` | AI-estimated pool dimensions |

### Pool Analysis

Satellite imagery and measurement tools.

| Model | Table | Purpose |
|-------|-------|---------|
| SatelliteAnalysis | `satellite_analyses` | Per-WF satellite analysis (sqft, vegetation, obstructions). Unique FK to `water_features.id` |
| PoolMeasurement | `pool_measurements` | Ground-truth measurements from tech photos + Claude Vision |

### Inspections (Pool Scout Pro)

Health department inspection intelligence.

| Model | Table | Purpose |
|-------|-------|---------|
| InspectionFacility | `inspection_facilities` | Commercial pool facility from county records |
| Inspection | `inspections` | Individual inspection record |
| InspectionViolation | `inspection_violations` | Violations found during an inspection |
| InspectionEquipment | `inspection_equipment` | Equipment recorded during an inspection |
| InspectionLookup | `inspection_lookups` | Single-lookup purchase records (tier-gated) |
| ScraperRun | `scraper_runs` | Playwright scraper execution log |

---

## Key Relationships

```
Organization ─1──*─ OrganizationUser ─*──1─ User
Organization ─1──*─ Customer ─1──*─ Property ─1──*─ WaterFeature
Organization ─1──*─ Tech ─1──*─ Route ─1──*─ RouteStop ──1─ Property
Organization ─1──*─ OrgRole ─1──*─ OrgRolePermission ──1─ Permission

Customer ─1──*─ CustomerContact
Customer ─1──*─ Invoice ─1──*─ InvoiceLineItem
Customer ─1──*─ Payment ──1─ Invoice

Property ─1──*─ Visit ──1─ Tech
Property ─1──*─ ChemicalReading
Property ─1──1─ PropertyDifficulty
Property ─1──1─ PropertyJurisdiction ──1─ BatherLoadJurisdiction
Property ─1──*─ SatelliteAnalysis

WaterFeature ─1──*─ EquipmentItem ──?─ EquipmentCatalog
WaterFeature ─1──1─ SatelliteAnalysis  (pools only, unique FK)
WaterFeature ─1──1─ ChemicalCostProfile
WaterFeature ─1──*─ PoolMeasurement
WaterFeature ─1──*─ DimensionEstimate
WaterFeature ─1──1─ PropertyDifficulty
WaterFeature ─1──1─ PropertyJurisdiction

EquipmentCatalog ─1──*─ EquipmentItem ─1──*─ EquipmentEvent
EquipmentItem ──?─ PartsCatalog  (replacement part)
EquipmentItem ──?─ EquipmentItem  (replaced_by self-ref)

Visit ─*──*─ Service  (through VisitService)
Visit ─1──*─ ChemicalReading
Visit ─1──*─ VisitPhoto
Visit ─1──*─ VisitChecklistEntry ──1─ ServiceChecklistItem

ServiceCase ─1──*─ AgentThread ─1──*─ AgentMessage ─1──*─ MessageAttachment
ServiceCase ─1──*─ AgentAction (jobs) ─1──*─ AgentActionTask
ServiceCase ─1──*─ Invoice
ServiceCase ─1──*─ InternalThread ─1──*─ InternalMessage
AgentAction ──?─ AgentAction  (parent_action_id self-ref)

InspectionFacility ─1──*─ Inspection ─1──*─ InspectionViolation
InspectionFacility ─1──*─ Inspection ─1──1─ InspectionEquipment
InspectionFacility ──?─ Property  (matched via address)

DeepBlueConversation ──1─ User
DeepBlueConversation ──?─ ServiceCase
```

---

## Deprecated Fields

These fields exist for backward compatibility but should NOT be read for display or business logic.

### Property (legacy pool fields)
The following columns on `properties` are superseded by `WaterFeature`:
- `pool_type`, `pool_shape`, `pool_length`, `pool_width`, `pool_depth_shallow`, `pool_depth_deep`
- `pool_gallons`, `pool_sqft`, `pool_volume_method`
- `pump_type`, `filter_type`, `heater_type`, `chlorinator_type`, `automation_system`

Read pool dimensions from `water_features`. Read equipment from `equipment_items` via `water_features.id`.

### AgentThread / AgentAction (denormalized customer name)
- `customer_name` on `agent_threads` and `agent_actions` is a fallback for unmatched records only
- When `matched_customer_id` / `customer_id` exists, join to `customers` table for display

---

## Known Issues

- ~~Duplicate PaymentMethod enum~~ — **FIXED 2026-04-07**: centralized in `core/enums.py`, both models re-export
- ~~Missing Tech.routes relationship~~ — **FIXED 2026-04-07**: bidirectional `back_populates` added
- **OrgRole name collision**: `OrgRole` exists as both an enum in `organization_user.py` and a model class in `org_role.py`. The enum is the legacy role system; the model is the new granular permission system.
- **Deprecated Property columns still exist**: 16 pool/equipment columns on Property model. Schemas no longer accept writes (fixed 2026-04-07) but columns remain for backward-compat reads.

---

## Conventions

| Pattern | Detail |
|---------|--------|
| Primary keys | `String(36)` UUIDs, generated in Python (`uuid.uuid4()`), not DB-level |
| Org scoping | `organization_id: String(36) FK organizations.id` on nearly every model |
| Timestamps | `created_at` (server default `func.now()`), `updated_at` (nullable, set on update) |
| Relationships | `lazy="noload"` everywhere — must explicitly `selectinload()` / `joinedload()` |
| Soft delete | Not used — records are hard-deleted (except customers which use `status` enum) |
| Enums | Python `str, enum.Enum` subclasses stored as `String` columns (not PG enum type) |
| Defaults | Defined in SQLAlchemy model only — NOT at PostgreSQL column level. Raw SQL must provide all values. |
| Cascade | `ondelete="CASCADE"` on child FKs to org/parent; `ondelete="SET NULL"` on optional references |
| Table naming | Plural snake_case (e.g. `water_features`, `agent_threads`) |
