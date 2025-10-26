# Database Schema Documentation

**Last Updated:** 2025-10-26
**Schema Version:** 3.0.0 (SaaS Multi-Tenant)
**Status:** SaaS Foundation Design

---

## Overview

This document describes the complete database schema for RouteOptimizer (Pool Scout Pro), a **multi-tenant SaaS application** for pool service management.

**Key Architectural Principle:** All tenant-specific data is isolated by `organization_id` foreign key.

---

## Table of Contents

1. [SaaS Foundation](#saas-foundation)
2. [Billing & Payments](#billing--payments)
3. [Core Routing Tables](#core-routing-tables)
4. [Water Features & Equipment](#water-features--equipment)
5. [Regulatory Compliance](#regulatory-compliance)
6. [Service Visit Tracking](#service-visit-tracking)
7. [Geocoding & Map Provider](#geocoding--map-provider)
8. [Data Isolation Strategy](#data-isolation-strategy)
9. [Entity Relationship Diagram](#entity-relationship-diagram)

---

## SaaS Foundation

Multi-tenancy architecture with organizations, users, and role-based access control.

### organizations

Represents a pool service company (tenant). Core isolation boundary for all data.

**Fields:**
- `id` (UUID, PK)
- `name` (VARCHAR(200), NOT NULL) - "Brian's Pool Service"
- `slug` (VARCHAR(100), UNIQUE, NOT NULL) - "brians-pool-service"
- `subdomain` (VARCHAR(63), UNIQUE) - "brians" → brians.poolscoutpro.com

**Subscription Management:**
- `plan_tier` (VARCHAR(50), NOT NULL, DEFAULT 'starter') - 'starter', 'professional', 'enterprise'
- `subscription_status` (VARCHAR(50), NOT NULL, DEFAULT 'trial') - 'trial', 'active', 'past_due', 'canceled'
- `trial_ends_at` (TIMESTAMP)
- `trial_days` (INTEGER, DEFAULT 14)

**Billing:**
- `billing_email` (VARCHAR(255))
- `billing_address` (TEXT)
- `stripe_customer_id` (VARCHAR(100))
- `stripe_subscription_id` (VARCHAR(100))

**Plan Limits:**
- `max_users` (INTEGER) - NULL = unlimited (enterprise)
- `max_customers` (INTEGER)
- `max_techs` (INTEGER)
- `max_routes_per_day` (INTEGER)

**Feature Flags:**
- `features_enabled` (JSONB, DEFAULT '{}')
  ```json
  {
    "ai_features": true,
    "advanced_routing": true,
    "multi_day_scheduling": true,
    "water_features": true,
    "api_access": false
  }
  ```

**Map Provider Configuration:**
- `default_map_provider` (VARCHAR(50), DEFAULT 'openstreetmap') - 'openstreetmap' or 'google_maps'
- `google_maps_api_key` (VARCHAR(200)) - Encrypted

**Customization:**
- `logo_url` (VARCHAR(500))
- `primary_color` (VARCHAR(7)) - Hex color code
- `timezone` (VARCHAR(50), DEFAULT 'America/Los_Angeles')

**Metadata:**
- `is_active` (BOOLEAN, NOT NULL, DEFAULT TRUE)
- `onboarded_at` (TIMESTAMP)
- `created_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())
- `updated_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())

**Indexes:**
- `idx_orgs_subdomain` ON subdomain
- `idx_orgs_slug` ON slug
- `idx_orgs_subscription_status` ON subscription_status
- `idx_orgs_stripe_customer` ON stripe_customer_id

**Business Rules:**
- `subdomain` must be unique and DNS-safe
- `slug` must be URL-safe (lowercase, hyphens only)
- Trial period default: 14 days
- `is_active = false` → Organization suspended

---

### users

Individual user accounts. Users can belong to multiple organizations.

**Fields:**
- `id` (UUID, PK)
- `email` (VARCHAR(255), UNIQUE, NOT NULL)
- `password_hash` (VARCHAR(255), NOT NULL) - bcrypt
- `first_name` (VARCHAR(100))
- `last_name` (VARCHAR(100))

**Account Status:**
- `is_active` (BOOLEAN, NOT NULL, DEFAULT TRUE)
- `email_verified_at` (TIMESTAMP)
- `email_verification_token` (VARCHAR(100))
- `password_reset_token` (VARCHAR(100))
- `password_reset_expires_at` (TIMESTAMP)

**Tracking:**
- `last_login_at` (TIMESTAMP)
- `last_login_ip` (VARCHAR(45)) - IPv6 support
- `login_count` (INTEGER, DEFAULT 0)

**Preferences:**
- `timezone` (VARCHAR(50))
- `locale` (VARCHAR(10), DEFAULT 'en_US')

**Metadata:**
- `created_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())
- `updated_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())

**Indexes:**
- `idx_users_email_lower` ON LOWER(email) (UNIQUE)
- `idx_users_email_verification_token` ON email_verification_token
- `idx_users_password_reset_token` ON password_reset_token

**Business Rules:**
- Email must be unique (case-insensitive)
- Password must be hashed with bcrypt (min 12 rounds)
- Email verification required before full access
- Password reset tokens expire after 1 hour

---

### organization_users

Junction table linking users to organizations with roles (many-to-many).

**Fields:**
- `id` (UUID, PK)
- `organization_id` (UUID, FK → organizations, ON DELETE CASCADE, NOT NULL)
- `user_id` (UUID, FK → users, ON DELETE CASCADE, NOT NULL)
- `role` (VARCHAR(50), NOT NULL) - 'owner', 'admin', 'manager', 'technician', 'readonly'
- `is_primary_org` (BOOLEAN, DEFAULT FALSE) - User's default org on login

**Invitation System:**
- `invitation_token` (VARCHAR(100))
- `invitation_accepted_at` (TIMESTAMP)
- `invited_by` (UUID, FK → users)

**Metadata:**
- `created_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())
- `updated_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())

**Constraints:**
- UNIQUE (organization_id, user_id)

**Indexes:**
- `idx_org_users_user` ON user_id
- `idx_org_users_org` ON organization_id
- `idx_org_users_role` ON role
- `idx_org_users_invitation_token` ON invitation_token

**Business Rules:**
- One user can belong to multiple organizations
- Only one role per user per organization
- Only one `is_primary_org = true` per user
- Role hierarchy: owner > admin > manager > technician > readonly

---

### organization_subscriptions

Tracks organization subscription details (linked to Stripe).

**Fields:**
- `id` (UUID, PK)
- `organization_id` (UUID, FK → organizations, ON DELETE CASCADE, NOT NULL)
- `stripe_subscription_id` (VARCHAR(100), UNIQUE)
- `plan_tier` (VARCHAR(50), NOT NULL) - 'starter', 'professional', 'enterprise'
- `status` (VARCHAR(50), NOT NULL) - 'active', 'past_due', 'canceled', 'trialing'
- `monthly_price` (NUMERIC(10,2))

**Billing Cycle:**
- `current_period_start` (TIMESTAMP, NOT NULL)
- `current_period_end` (TIMESTAMP, NOT NULL)
- `trial_start` (TIMESTAMP)
- `trial_end` (TIMESTAMP)

**Cancellation:**
- `cancel_at_period_end` (BOOLEAN, DEFAULT FALSE)
- `canceled_at` (TIMESTAMP)
- `cancellation_reason` (TEXT)

**Metadata:**
- `created_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())
- `updated_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())

**Indexes:**
- `idx_org_subs_org` ON organization_id
- `idx_org_subs_stripe` ON stripe_subscription_id
- `idx_org_subs_status` ON status

---

### usage_tracking

Tracks resource usage for billing and analytics.

**Fields:**
- `id` (UUID, PK)
- `organization_id` (UUID, FK → organizations, NOT NULL)
- `metric` (VARCHAR(100), NOT NULL) - 'customers_created', 'routes_optimized', 'api_calls', 'geocoding_requests', etc.
- `quantity` (INTEGER, DEFAULT 1)
- `metadata` (JSONB) - Additional context
- `recorded_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())

**Indexes:**
- `idx_usage_org` ON organization_id
- `idx_usage_metric` ON metric
- `idx_usage_recorded_at` ON recorded_at
- `idx_usage_org_metric_date` ON (organization_id, metric, recorded_at)

**Business Rules:**
- Immutable audit log (no updates/deletes)
- Used for billing calculations and analytics

---

## Billing & Payments

Normalized billing architecture replacing billing fields previously on customers table.

### service_plans

Reusable pricing templates for service offerings.

**Fields:**
- `id` (UUID, PK)
- `organization_id` (UUID, FK → organizations, NULL) - NULL = global template available to all orgs
- `name` (VARCHAR(100), NOT NULL) - "Standard Residential", "Premium Commercial"
- `description` (TEXT)
- `base_rate` (NUMERIC(10,2), NOT NULL)
- `billing_frequency` (VARCHAR(20), NOT NULL) - 'weekly', 'monthly', 'per-visit'
- `is_active` (BOOLEAN, NOT NULL, DEFAULT TRUE)
- `created_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())
- `updated_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())

**Indexes:**
- `idx_service_plans_org` ON organization_id
- `idx_service_plans_active` ON is_active WHERE is_active = TRUE

**Business Rules:**
- Global templates (organization_id = NULL) available to all organizations
- Organization-specific plans override globals

---

### customer_service_agreements

Links customers to service plans with effective dates (supports rate history).

**Fields:**
- `id` (UUID, PK)
- `organization_id` (UUID, FK → organizations, NOT NULL)
- `customer_id` (UUID, FK → customers, NOT NULL)
- `service_plan_id` (UUID, FK → service_plans, NULL) - NULL if custom pricing
- `feature_id` (UUID, FK → water_features, NULL) - For feature-based pricing
- `custom_rate` (NUMERIC(10,2)) - Override base_rate if negotiated
- `effective_date` (DATE, NOT NULL)
- `end_date` (DATE) - NULL = current agreement
- `rate_notes` (TEXT)
- `created_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())

**Indexes:**
- `idx_csa_org` ON organization_id
- `idx_csa_customer` ON customer_id
- `idx_csa_current` ON (customer_id, end_date) WHERE end_date IS NULL

**Business Rules:**
- Complete rate history (effective_date/end_date pattern)
- Supports scheduled rate changes (insert future agreement)
- Multiple agreements per customer for multi-feature pricing
- Audit trail for billing disputes

---

### payment_methods

Stores customer payment methods (PCI-compliant references only).

**Fields:**
- `id` (UUID, PK)
- `organization_id` (UUID, FK → organizations, NOT NULL)
- `customer_id` (UUID, FK → customers, NOT NULL)
- `payment_type` (VARCHAR(20), NOT NULL) - 'credit_card', 'ach', 'check', 'cash'
- `is_primary` (BOOLEAN, DEFAULT FALSE)
- `is_active` (BOOLEAN, DEFAULT TRUE)
- `stripe_payment_method_id` (VARCHAR(100)) - PCI-compliant reference
- `last_four` (VARCHAR(4))
- `brand` (VARCHAR(50)) - "Visa", "Chase Bank", etc.
- `created_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())
- `updated_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())

**Constraints:**
- UNIQUE INDEX `idx_one_primary_per_customer` ON (customer_id, is_primary) WHERE is_primary = TRUE AND is_active = TRUE

**Indexes:**
- `idx_payment_methods_org` ON organization_id
- `idx_payment_methods_customer` ON customer_id

**Business Rules:**
- Multiple payment methods per customer (primary + backups)
- Soft delete (is_active) preserves history
- **NEVER store raw card/ACH data** (PCI compliance)

---

## Core Routing Tables

### customers

Pool service customers. Core entity for routing and service management.

**Fields:**
- `id` (UUID, PK)
- **`organization_id` (UUID, FK → organizations, NOT NULL)** ← **SaaS Foundation**

**Identity:**
- `service_type` (VARCHAR(20), NOT NULL) - 'residential' or 'commercial'
- `display_name` (VARCHAR(200), NOT NULL, INDEXED)
- `first_name` (VARCHAR(100))
- `last_name` (VARCHAR(100))
- `name` (VARCHAR(200)) - Business name (for commercial)

**Location:**
- `address` (VARCHAR(500), NOT NULL)
- `city` (VARCHAR(100))
- `state` (VARCHAR(2))
- `zip_code` (VARCHAR(10))
- `latitude` (FLOAT)
- `longitude` (FLOAT)

**Geocoding Metadata:** (see Geocoding section)
- `geocoding_provider` (VARCHAR(50))
- `geocoded_by` (UUID, FK → users)
- `geocoded_at` (TIMESTAMP)

**Contact:**
- `email` (VARCHAR(255))
- `phone` (VARCHAR(20))
- `alt_email` (VARCHAR(255))
- `alt_phone` (VARCHAR(20))
- `invoice_email` (VARCHAR(255))

**Commercial Properties:**
- `management_company` (VARCHAR(200))

**Service Configuration:**
- `assigned_driver_id` (UUID, FK → drivers)
- `service_day` (VARCHAR(20), NOT NULL) - 'monday', 'tuesday', etc.
- `service_days_per_week` (INTEGER, DEFAULT 1)
- `service_schedule` (VARCHAR(50)) - e.g., "Mo/Th", "Mo/We/Fr"
- `visit_duration` (INTEGER, DEFAULT 15) - Minutes
- `difficulty` (INTEGER, DEFAULT 1) - 1-5 scale
- `locked` (BOOLEAN, DEFAULT FALSE) - If true, cannot be moved to different service day

**Time Windows:**
- `time_window_start` (TIME)
- `time_window_end` (TIME)

**Status:**
- `status` (VARCHAR(20), DEFAULT 'active') - 'pending', 'active', 'inactive'
- `is_active` (BOOLEAN, DEFAULT TRUE)
- `notes` (TEXT)

**Metadata:**
- `created_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())
- `updated_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())

**Indexes:**
- **`idx_customers_org` ON organization_id** ← **Critical for data isolation**
- `idx_customers_service_day` ON service_day
- `idx_customers_service_type` ON service_type
- `idx_customers_assigned_driver` ON assigned_driver_id
- `idx_customers_display_name` ON display_name
- `idx_customers_geocoding_provider` ON geocoding_provider

**Relationships:**
- 1:many → water_features
- 1:many → route_stops
- many:1 → assigned_driver (drivers table)

---

### drivers

Technicians who service customers and execute routes.

**Fields:**
- `id` (UUID, PK)
- **`organization_id` (UUID, FK → organizations, NOT NULL)** ← **SaaS Foundation**
- `name` (VARCHAR(200), NOT NULL)
- `email` (VARCHAR(255))
- `phone` (VARCHAR(20))
- `color` (VARCHAR(7), NOT NULL) - Hex color for route visualization
- `home_address` (VARCHAR(500))
- `home_latitude` (FLOAT)
- `home_longitude` (FLOAT)

**Geocoding Metadata:**
- `geocoding_provider` (VARCHAR(50))
- `geocoded_by` (UUID, FK → users)
- `geocoded_at` (TIMESTAMP)

**Status:**
- `is_active` (BOOLEAN, DEFAULT TRUE)
- `created_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())
- `updated_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())

**Indexes:**
- **`idx_drivers_org` ON organization_id**
- `idx_drivers_active` ON is_active
- `idx_drivers_geocoding_provider` ON geocoding_provider

---

### routes

Optimized service routes generated by Google OR-Tools VRP solver.

**Fields:**
- `id` (UUID, PK)
- **`organization_id` (UUID, FK → organizations, NOT NULL)** ← **SaaS Foundation**
- `driver_id` (UUID, FK → drivers, NOT NULL)
- `service_day` (VARCHAR(20), NOT NULL)
- `route_date` (DATE, NOT NULL)
- `route_number` (INTEGER)
- `total_distance_km` (FLOAT)
- `total_duration_minutes` (INTEGER)
- `total_service_time_minutes` (INTEGER)
- `optimization_score` (FLOAT) - Quality metric (lower = better)
- `created_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())

**Indexes:**
- **`idx_routes_org` ON organization_id**
- `idx_routes_driver` ON driver_id
- `idx_routes_service_day` ON service_day
- `idx_routes_route_date` ON route_date

---

### route_stops

Individual customer visits within a route (ordered sequence).

**Fields:**
- `id` (UUID, PK)
- **`organization_id` (UUID, FK → organizations, NOT NULL)** ← **SaaS Foundation**
- `route_id` (UUID, FK → routes, ON DELETE CASCADE, NOT NULL)
- `customer_id` (UUID, FK → customers, NOT NULL)
- `stop_number` (INTEGER, NOT NULL) - Sequence in route
- `estimated_arrival_time` (TIMESTAMP)
- `estimated_service_duration_minutes` (INTEGER)
- `travel_time_from_previous_minutes` (INTEGER)
- `distance_from_previous_km` (FLOAT)
- `created_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())

**Indexes:**
- **`idx_route_stops_org` ON organization_id**
- `idx_route_stops_route` ON route_id
- `idx_route_stops_customer` ON customer_id
- `idx_route_stops_stop_number` ON (route_id, stop_number)

---

## Water Features & Equipment

### water_features

Physical water features at customer locations (pools, spas, fountains, etc.).

**Fields:**
- `id` (UUID, PK)
- **`organization_id` (UUID, FK → organizations, NOT NULL)** ← **SaaS Foundation**
- `customer_id` (UUID, FK → customers, NOT NULL)
- `feature_type` (VARCHAR(50), NOT NULL)
  - Enum: 'pool', 'spa', 'spillover_spa', 'wading_pool', 'fountain', 'deck_jet', 'sheer_descent', 'rain_curtain', 'laminar', 'bubbler'
- `name` (VARCHAR(100)) - e.g., "Main Pool", "Jacuzzi Spa"

**Specifications:** (normalized from JSONB for queryability)
- `gallons` (INTEGER)
- `surface_area` (FLOAT) - Square feet
- `depth_min` (FLOAT) - Feet
- `depth_max` (FLOAT) - Feet
- `finish_type` (VARCHAR(50)) - 'plaster', 'pebble', 'tile', 'vinyl'
- `shape` (VARCHAR(50)) - 'rectangular', 'kidney', 'freeform', etc.

**Equipment & Covers:**
- `has_cover` (BOOLEAN)
- `cover_type` (VARCHAR(50)) - 'manual', 'automatic', 'solar'
- `has_lighting` (BOOLEAN)
- `lighting_type` (VARCHAR(50)) - 'LED', 'incandescent', 'fiber_optic'

**Dates:**
- `installation_date` (DATE)
- `warranty_expiration` (DATE)

**Flexible Data:**
- `properties` (JSONB) - Additional flexible data not commonly queried

**Status:**
- `notes` (TEXT)
- `is_active` (BOOLEAN, DEFAULT TRUE)
- `created_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())
- `updated_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())

**Indexes:**
- **`idx_water_features_org` ON organization_id**
- `idx_water_features_customer` ON customer_id
- `idx_water_features_feature_type` ON feature_type

**Business Rules:**
- Customer can have multiple features
- `name` should be unique within customer's features

---

### equipment

Equipment associated with water features.

**Fields:**
- `id` (UUID, PK)
- **`organization_id` (UUID, FK → organizations, NOT NULL)** ← **SaaS Foundation**
- `feature_id` (UUID, FK → water_features, NOT NULL)
- `equipment_type` (VARCHAR(50), NOT NULL)
  - Enum: 'pump', 'filter', 'sanitizer', 'heater', 'automation', 'cleaner', 'lighting', 'valve', 'timer'
- `category` (VARCHAR(50))
  - Filters: 'sand', 'cartridge', 'de'
  - Heaters: 'gas', 'electric', 'heat_pump', 'solar'
  - Sanitizers: 'chlorinator', 'salt_system', 'ozone', 'uv'
  - Pumps: 'single_speed', 'two_speed', 'variable_speed'
  - Cleaners: 'robotic', 'suction', 'pressure'
- `brand` (VARCHAR(100))
- `model` (VARCHAR(100))
- `serial_number` (VARCHAR(100))

**Specifications:** (normalized from JSONB for queryability)
- `horsepower` (NUMERIC(5,2)) - Pumps
- `voltage` (INTEGER) - Pumps, heaters
- `flow_rate_gpm` (INTEGER) - Pumps
- `filter_area_sqft` (NUMERIC(5,2)) - Filters
- `btu_rating` (INTEGER) - Heaters
- `fuel_type` (VARCHAR(50)) - Heaters

**Financial:**
- `installation_date` (DATE)
- `warranty_expiration` (DATE)
- `purchase_cost` (NUMERIC(10,2))
- `replacement_cost_estimate` (NUMERIC(10,2))

**Flexible Data:**
- `specs` (JSONB) - Additional specs not commonly queried (warranty info, serial numbers, etc.)
- `notes` (TEXT)

**Status:**
- `is_active` (BOOLEAN, DEFAULT TRUE) - FALSE if replaced/removed
- `created_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())
- `updated_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())

**Indexes:**
- **`idx_equipment_org` ON organization_id**
- `idx_equipment_feature` ON feature_id
- `idx_equipment_type` ON equipment_type
- `idx_equipment_serial` ON serial_number

**Business Rules:**
- Equipment always tied to water feature
- When replaced, old record marked `is_active = FALSE`, new record created

---

### equipment_maintenance_log

Maintenance, repairs, and replacements for equipment.

**Fields:**
- `id` (UUID, PK)
- **`organization_id` (UUID, FK → organizations, NOT NULL)** ← **SaaS Foundation**
- `equipment_id` (UUID, FK → equipment, NOT NULL)
- `service_date` (DATE, NOT NULL)
- `service_type` (VARCHAR(50), NOT NULL) - 'cleaning', 'repair', 'replacement', 'inspection', 'calibration'
- `technician_id` (UUID, FK → drivers)

**Costs:**
- `labor_hours` (NUMERIC(4,2))
- `labor_cost` (NUMERIC(10,2))
- `parts_cost` (NUMERIC(10,2))
- `total_cost` (NUMERIC(10,2))

**Parts (normalized from JSONB):**
- Consider separate `equipment_parts_used` table for queryability (future enhancement)
- `parts_replaced` (JSONB) - Array of parts for now
  ```json
  [
    {"part_name": "Impeller", "part_number": "PENT-IMP-1.5HP", "quantity": 1, "cost": 45.00}
  ]
  ```

**Scheduling:**
- `notes` (TEXT)
- `next_service_due` (DATE)
- `service_interval_days` (INTEGER)

**Metadata:**
- `created_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())
- `updated_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())

**Indexes:**
- **`idx_equipment_maint_org` ON organization_id**
- `idx_equipment_maint_equipment` ON equipment_id
- `idx_equipment_maint_service_date` ON service_date
- `idx_equipment_maint_tech` ON technician_id
- `idx_equipment_maint_next_due` ON next_service_due

**Business Rules:**
- Immutable audit trail (no updates/deletes)
- `next_service_due` auto-calculated

---

## Regulatory Compliance

### emd_inspections

Sacramento County EMD inspections for commercial/public pools.

**Fields:**
- `id` (UUID, PK)
- **`organization_id` (UUID, FK → organizations, NOT NULL)** ← **SaaS Foundation**
- `feature_id` (UUID, FK → water_features, NOT NULL)
- `inspection_date` (DATE, NOT NULL)
- `inspector_name` (VARCHAR(100))
- `inspector_id` (VARCHAR(50))
- `permit_number` (VARCHAR(50))
- `facility_type` (VARCHAR(50)) - 'public', 'semi_public', 'commercial'
- `compliance_status` (VARCHAR(50), NOT NULL) - 'passed', 'failed', 'conditional', 'pending_reinspection'
- `score` (INTEGER)

**Violations:** (normalized to separate table for queryability)
- See `emd_violations` table below
- `violations` (JSONB) - Deprecated, migrate to `emd_violations` table

**Future:**
- `corrective_actions` (JSONB)
- `next_inspection_due` (DATE)
- `report_url` (VARCHAR(500))
- `report_data` (JSONB)
- `notes` (TEXT)

**Metadata:**
- `created_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())
- `updated_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())

**Indexes:**
- **`idx_emd_inspections_org` ON organization_id**
- `idx_emd_inspections_feature` ON feature_id
- `idx_emd_inspections_date` ON inspection_date
- `idx_emd_inspections_status` ON compliance_status
- `idx_emd_inspections_next_due` ON next_inspection_due

---

### emd_violations

Normalized violations table (extracted from emd_inspections JSONB).

**Fields:**
- `id` (UUID, PK)
- **`organization_id` (UUID, FK → organizations, NOT NULL)** ← **SaaS Foundation**
- `inspection_id` (UUID, FK → emd_inspections, ON DELETE CASCADE, NOT NULL)
- `violation_code` (VARCHAR(20), NOT NULL) - e.g., "65529(b)"
- `description` (TEXT, NOT NULL)
- `severity` (VARCHAR(20)) - 'critical', 'major', 'minor'
- `remediated` (BOOLEAN, DEFAULT FALSE)
- `remediation_date` (DATE)
- `remediation_notes` (TEXT)
- `created_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())

**Indexes:**
- **`idx_emd_violations_org` ON organization_id**
- `idx_emd_violations_inspection` ON inspection_id
- `idx_emd_violations_code` ON violation_code
- `idx_emd_violations_unremediated` ON remediated WHERE remediated = FALSE

**Benefits:**
- Query "all pools with violation code 22-C"
- Track remediation status
- Trend violations over time

---

### chemical_logs

Water chemistry testing (CA Title 22 compliance).

**Fields:**
- `id` (UUID, PK)
- **`organization_id` (UUID, FK → organizations, NOT NULL)** ← **SaaS Foundation**
- `feature_id` (UUID, FK → water_features, NOT NULL)
- `test_date` (TIMESTAMP, NOT NULL)
- `tested_by_id` (UUID, FK → users) - **Changed from drivers to users for SaaS**

**Readings:**
- `chlorine_ppm` (NUMERIC(4,2))
- `combined_chlorine_ppm` (NUMERIC(4,2))
- `ph` (NUMERIC(3,2))
- `total_alkalinity_ppm` (INTEGER)
- `calcium_hardness_ppm` (INTEGER)
- `cyanuric_acid_ppm` (INTEGER)
- `salt_ppm` (INTEGER)
- `phosphates_ppb` (INTEGER)
- `temperature_f` (NUMERIC(4,1))

**Test Info:**
- `test_method` (VARCHAR(20)) - 'strips', 'drops', 'digital', 'lab'
- `readings_within_range` (BOOLEAN)

**Chemicals Added:** (consider normalizing to separate table for inventory tracking)
- See `chemical_additions` table below
- `chemicals_added` (JSONB) - Deprecated, migrate to `chemical_additions`

**Photos:**
- `photo_ids` (UUID[]) - Array of visit_photos.id (multiple test result photos)

**Metadata:**
- `notes` (TEXT)
- `created_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())

**Indexes:**
- **`idx_chemical_logs_org` ON organization_id**
- `idx_chemical_logs_feature` ON feature_id
- `idx_chemical_logs_test_date` ON test_date
- `idx_chemical_logs_tested_by` ON tested_by_id
- `idx_chemical_logs_within_range` ON readings_within_range

---

### chemical_additions

Normalized chemicals added during visits (extracted from chemical_logs JSONB).

**Fields:**
- `id` (UUID, PK)
- **`organization_id` (UUID, FK → organizations, NOT NULL)** ← **SaaS Foundation**
- `chemical_log_id` (UUID, FK → chemical_logs, ON DELETE CASCADE, NOT NULL)
- `chemical_type` (VARCHAR(50), NOT NULL) - 'chlorine', 'acid', 'alkalinity_increaser', etc.
- `amount` (NUMERIC(10,2), NOT NULL)
- `unit` (VARCHAR(20), NOT NULL) - 'oz', 'lbs', 'gallons', 'tablets'
- `created_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())

**Indexes:**
- **`idx_chemical_additions_org` ON organization_id**
- `idx_chemical_additions_log` ON chemical_log_id
- `idx_chemical_additions_type` ON chemical_type

**Benefits:**
- Query total chemical usage per type
- Inventory depletion tracking
- Cost analysis per chemical

---

## Service Visit Tracking

### service_visits

Technician visits to customer locations.

**Fields:**
- `id` (UUID, PK)
- **`organization_id` (UUID, FK → organizations, NOT NULL)** ← **SaaS Foundation**
- `customer_id` (UUID, FK → customers, NOT NULL)
- **NOTE:** `feature_id` REMOVED, replaced with `visit_features` junction table (many-to-many)
- `technician_id` (UUID, FK → users, NOT NULL) - **Changed from drivers to users**

**Schedule:**
- `scheduled_date` (DATE, NOT NULL)
- `scheduled_start_time` (TIME)
- `scheduled_duration_minutes` (INTEGER)

**Actual Times:**
- `arrival_time` (TIMESTAMP) - GPS check-in
- `departure_time` (TIMESTAMP) - GPS check-out
- `actual_duration_minutes` (INTEGER) - Auto-calculated

**Visit Info:**
- `visit_type` (VARCHAR(50), NOT NULL) - 'routine_service', 'repair', 'inspection', 'warranty', 'installation', 'consultation'
- `status` (VARCHAR(50), NOT NULL) - 'scheduled', 'en_route', 'in_progress', 'completed', 'cancelled', 'rescheduled'
- `completion_notes` (TEXT)

**Issues:** (consider normalizing to separate table)
- `issues_found` (JSONB)

**Customer Interaction:**
- `customer_present` (BOOLEAN)
- `customer_signature` (TEXT) - Base64 encoded signature

**Integration:**
- `invoice_id` (UUID, FK → invoices) - Future
- `weather_conditions` (VARCHAR(50))

**Metadata:**
- `created_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())
- `updated_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())

**Indexes:**
- **`idx_service_visits_org` ON organization_id**
- `idx_service_visits_customer` ON customer_id
- `idx_service_visits_tech` ON technician_id
- `idx_service_visits_scheduled_date` ON scheduled_date
- `idx_service_visits_status` ON status

---

### visit_features

Junction table for multi-feature visits (many-to-many).

**Purpose:** Replaces `feature_id` on service_visits. Allows one visit to service multiple features (e.g., pool + spa in one visit).

**Fields:**
- `id` (UUID, PK)
- **`organization_id` (UUID, FK → organizations, NOT NULL)** ← **SaaS Foundation**
- `visit_id` (UUID, FK → service_visits, ON DELETE CASCADE, NOT NULL)
- `feature_id` (UUID, FK → water_features, NOT NULL)
- `duration_minutes` (INTEGER) - Time spent on this specific feature
- `created_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())

**Constraints:**
- UNIQUE (visit_id, feature_id)

**Indexes:**
- **`idx_visit_features_org` ON organization_id**
- `idx_visit_features_visit` ON visit_id
- `idx_visit_features_feature` ON feature_id

**Benefits:**
- Track time per feature within visit
- Query "all visits for pool #123"
- Accurate duration tracking for multi-feature properties

---

### visit_photos

Photos captured during service visits.

**Fields:**
- `id` (UUID, PK)
- **`organization_id` (UUID, FK → organizations, NOT NULL)** ← **SaaS Foundation**
- `visit_id` (UUID, FK → service_visits, NOT NULL)
- `photo_type` (VARCHAR(50), NOT NULL) - 'before', 'after', 'issue', 'equipment', 'chemical_reading', 'customer_request', 'general'
- `equipment_id` (UUID, FK → equipment)

**Storage:**
- `file_path` (VARCHAR(500), NOT NULL) - `photos/{customer_id}/{visit_id}/{photo_id}.jpg`
- `thumbnail_path` (VARCHAR(500))
- `file_size_bytes` (INTEGER)
- `mime_type` (VARCHAR(50))
- `width_px` (INTEGER)
- `height_px` (INTEGER)

**Metadata:**
- `caption` (TEXT)
- `gps_latitude` (NUMERIC(10,8))
- `gps_longitude` (NUMERIC(11,8))
- `taken_at` (TIMESTAMP, NOT NULL)
- `uploaded_at` (TIMESTAMP, NOT NULL)
- `uploaded_by_id` (UUID, FK → users)
- `is_customer_visible` (BOOLEAN, DEFAULT TRUE)
- `created_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())

**Indexes:**
- **`idx_visit_photos_org` ON organization_id**
- `idx_visit_photos_visit` ON visit_id
- `idx_visit_photos_type` ON photo_type
- `idx_visit_photos_equipment` ON equipment_id
- `idx_visit_photos_taken_at` ON taken_at

**Business Rules:**
- Auto-upload to Digital Ocean Spaces
- Thumbnails generated on upload (320x240)
- GPS from mobile device
- Customer-visible photos in customer portal

---

### visit_tasks

Pre-defined checklist tasks for service visits.

**Fields:**
- `id` (UUID, PK)
- **`organization_id` (UUID, FK → organizations, NOT NULL)** ← **SaaS Foundation**
- `visit_id` (UUID, FK → service_visits, NOT NULL)
- `template_id` (UUID, FK → task_templates) - Link to reusable template
- `task_type` (VARCHAR(50), NOT NULL) - 'skim_surface', 'vacuum_floor', 'brush_walls', etc.
- `task_name` (VARCHAR(100))
- `completed` (BOOLEAN, DEFAULT FALSE)
- `completed_at` (TIMESTAMP)
- `skipped` (BOOLEAN, DEFAULT FALSE)
- `skip_reason` (TEXT)
- `notes` (TEXT)
- `time_spent_minutes` (INTEGER)
- `sort_order` (INTEGER)
- `created_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())
- `updated_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())

**Indexes:**
- **`idx_visit_tasks_org` ON organization_id**
- `idx_visit_tasks_visit` ON visit_id
- `idx_visit_tasks_template` ON template_id
- `idx_visit_tasks_completed` ON completed

---

### task_templates

Reusable task checklists for service visits.

**Fields:**
- `id` (UUID, PK)
- `organization_id` (UUID, FK → organizations, NULL) - NULL = global template
- `name` (VARCHAR(100), NOT NULL) - "Standard Pool Service", "Green Pool Cleanup"
- `description` (TEXT)
- `feature_type` (VARCHAR(50)) - 'pool', 'spa', etc. (NULL = all types)
- `tasks` (JSONB, NOT NULL) - Array of task definitions
  ```json
  [
    {"order": 1, "task_type": "skim_surface", "task_name": "Skim surface debris"},
    {"order": 2, "task_type": "test_water", "task_name": "Test water chemistry"}
  ]
  ```
- `is_active` (BOOLEAN, DEFAULT TRUE)
- `created_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())
- `updated_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())

**Indexes:**
- `idx_task_templates_org` ON organization_id
- `idx_task_templates_feature_type` ON feature_type

**Benefits:**
- Consistent service quality
- Global templates for all organizations
- Organization-specific custom checklists

---

## Geocoding & Map Provider

### geocoding_cache

Caches geocoding results to reduce API calls.

**Fields:**
- `id` (UUID, PK)
- `address_hash` (VARCHAR(64), UNIQUE, NOT NULL) - SHA256(normalized_address)
- `normalized_address` (TEXT, NOT NULL) - Lowercase, trimmed
- `latitude` (FLOAT, NOT NULL)
- `longitude` (FLOAT, NOT NULL)
- `formatted_address` (TEXT)
- `provider` (VARCHAR(50), NOT NULL) - 'openstreetmap' or 'google_maps'
- `confidence` (FLOAT) - 0.0-1.0
- `metadata` (JSONB)

**Cache Management:**
- `hit_count` (INTEGER, DEFAULT 1)
- `created_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())
- `last_used_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())

**Indexes:**
- `idx_geocoding_cache_hash` ON address_hash
- `idx_geocoding_cache_provider` ON provider
- `idx_geocoding_cache_last_used` ON last_used_at

**Business Rules:**
- Cache invalidation: 90 days since last use
- Hit count tracks usage for analytics

---

## Lead Generation & Scouting (Core Differentiator #1) 🎯

**Strategic Value:** Automated EMD inspection report scraping identifies unserviced pools and management companies. This transforms the platform from a cost center (management tool) into a profit center (revenue generator). NO other pool service software does this.

**Tables:** 4 tables supporting the complete scouting workflow

---

### scraped_reports

Stores raw EMD inspection reports scraped from California county websites.

**Schema:**
```sql
CREATE TABLE scraped_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    -- Source Information
    source_county VARCHAR(100) NOT NULL,
    source_url TEXT NOT NULL,
    scraping_job_id UUID REFERENCES scraping_jobs(id),
    scraped_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Facility Information (from EMD report)
    facility_name VARCHAR(500),
    facility_address TEXT NOT NULL,
    facility_latitude DECIMAL(10, 8),
    facility_longitude DECIMAL(11, 8),
    geocoded_at TIMESTAMP WITH TIME ZONE,

    -- Pool/Spa Details
    pool_type VARCHAR(100),  -- 'public', 'commercial', 'semi-public', etc.
    pool_size_gallons INTEGER,
    spa_present BOOLEAN DEFAULT FALSE,
    number_of_pools INTEGER DEFAULT 1,

    -- Inspection Data
    last_inspection_date DATE,
    inspection_result VARCHAR(50),  -- 'pass', 'fail', 'conditional', etc.
    violations_found INTEGER DEFAULT 0,
    violation_details JSONB,  -- Array of violations with severity

    -- Management Company (extracted from report)
    management_company_name VARCHAR(500),
    operator_name VARCHAR(255),
    operator_phone VARCHAR(20),

    -- Processing Status
    is_processed BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMP WITH TIME ZONE,
    lead_id UUID REFERENCES leads(id),  -- If converted to lead

    -- Raw Data
    raw_html TEXT,  -- Full HTML for reprocessing if needed
    metadata JSONB,  -- Additional extracted data

    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
```

**Indexes:**
- `idx_scraped_reports_org` ON organization_id
- `idx_scraped_reports_county` ON source_county
- `idx_scraped_reports_address` ON facility_address (GIN for text search)
- `idx_scraped_reports_processed` ON is_processed, organization_id
- `idx_scraped_reports_inspection_date` ON last_inspection_date
- `idx_scraped_reports_coordinates` ON facility_latitude, facility_longitude

**Business Rules:**
- Each organization only sees reports scraped for their configured counties
- Reports are deduplicated by (organization_id, facility_address, last_inspection_date)
- Unprocessed reports older than 180 days are archived

---

### leads

Stores identified unserviced pools (facilities NOT currently serviced by the organization).

**Schema:**
```sql
CREATE TABLE leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    -- Lead Source
    scraped_report_id UUID REFERENCES scraped_reports(id),
    source_type VARCHAR(50) NOT NULL DEFAULT 'emd_scraping',  -- Future: 'referral', 'manual', 'web_form'
    identified_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Facility Information
    facility_name VARCHAR(500),
    facility_address TEXT NOT NULL,
    facility_latitude DECIMAL(10, 8),
    facility_longitude DECIMAL(11, 8),
    pool_type VARCHAR(100),
    estimated_pool_size_gallons INTEGER,

    -- Lead Scoring (calculated by algorithm)
    score INTEGER DEFAULT 0 CHECK (score >= 0 AND score <= 100),
    score_breakdown JSONB,  -- Details of scoring factors
    priority VARCHAR(20) DEFAULT 'medium',  -- 'hot', 'warm', 'cold'

    -- Scoring Factors
    violation_severity_score INTEGER DEFAULT 0,  -- Higher = more urgent repairs needed
    last_inspection_days_ago INTEGER,  -- Urgency for compliance
    distance_to_nearest_route_miles DECIMAL(10, 2),  -- Proximity advantage
    estimated_monthly_revenue_cents INTEGER,  -- Revenue potential

    -- Management Company
    management_company_name VARCHAR(500),
    research_data_id UUID REFERENCES research_data(id),  -- Enrichment data

    -- Lead Status & Workflow
    status VARCHAR(50) NOT NULL DEFAULT 'new',  -- 'new', 'contacted', 'qualified', 'proposal_sent', 'won', 'lost', 'archived'
    assigned_to_user_id UUID REFERENCES users(id),  -- Sales team member
    assigned_at TIMESTAMP WITH TIME ZONE,

    contacted_at TIMESTAMP WITH TIME ZONE,
    qualified_at TIMESTAMP WITH TIME ZONE,
    converted_at TIMESTAMP WITH TIME ZONE,
    converted_to_customer_id UUID REFERENCES customers(id),  -- If won

    -- Communication History
    contact_attempts INTEGER DEFAULT 0,
    last_contact_at TIMESTAMP WITH TIME ZONE,
    notes TEXT,

    -- Loss Tracking
    lost_reason VARCHAR(255),  -- If status = 'lost'
    competitor_name VARCHAR(255),  -- If lost to competitor

    -- Deduplication
    is_duplicate BOOLEAN DEFAULT FALSE,
    duplicate_of_lead_id UUID REFERENCES leads(id),

    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
```

**Indexes:**
- `idx_leads_org` ON organization_id
- `idx_leads_status` ON status, organization_id
- `idx_leads_score` ON score DESC, organization_id
- `idx_leads_assigned` ON assigned_to_user_id
- `idx_leads_company` ON management_company_name (GIN for text search)
- `idx_leads_coordinates` ON facility_latitude, facility_longitude
- `idx_leads_created` ON created_at DESC

**Business Rules:**
- Leads automatically identified by cross-referencing scraped_reports against customers table
- Score recalculated daily based on aging and new data
- Contacted leads without follow-up for 30 days flagged for review
- Won leads create customer records and link via converted_to_customer_id

---

### research_data

Stores enrichment data about management companies (contact info, properties managed, etc.).

**Schema:**
```sql
CREATE TABLE research_data (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    -- Company Identification
    company_name VARCHAR(500) NOT NULL,
    normalized_company_name VARCHAR(500) NOT NULL,  -- For matching
    company_type VARCHAR(100),  -- 'property_management', 'hoa', 'hotel', 'apartment_complex', etc.

    -- Contact Information (scraped or researched)
    website_url TEXT,
    primary_phone VARCHAR(20),
    secondary_phone VARCHAR(20),
    primary_email VARCHAR(255),
    office_address TEXT,
    office_latitude DECIMAL(10, 8),
    office_longitude DECIMAL(11, 8),

    -- Company Details
    properties_managed_count INTEGER,  -- Estimated or known
    service_area_counties TEXT[],  -- Array of counties they operate in
    company_size VARCHAR(50),  -- 'small' (<10 properties), 'medium' (10-50), 'large' (50+)

    -- Research Sources
    data_sources JSONB,  -- Array of {source: 'web_scrape', url: '...', scraped_at: '...'}
    last_verified_at TIMESTAMP WITH TIME ZONE,

    -- Relationship History
    total_leads_identified INTEGER DEFAULT 0,
    total_leads_contacted INTEGER DEFAULT 0,
    total_leads_won INTEGER DEFAULT 0,

    -- Engagement Tracking
    first_contact_attempt_at TIMESTAMP WITH TIME ZONE,
    last_contact_attempt_at TIMESTAMP WITH TIME ZONE,
    relationship_status VARCHAR(50) DEFAULT 'prospect',  -- 'prospect', 'engaged', 'client', 'declined'

    -- Decision Maker Info (if known)
    decision_maker_name VARCHAR(255),
    decision_maker_title VARCHAR(100),
    decision_maker_email VARCHAR(255),
    decision_maker_phone VARCHAR(20),

    -- Notes
    notes TEXT,

    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
```

**Indexes:**
- `idx_research_org` ON organization_id
- `idx_research_company_name` ON normalized_company_name (GIN for text search)
- `idx_research_relationship` ON relationship_status, organization_id
- `idx_research_verified` ON last_verified_at

**Business Rules:**
- Normalized company names use lowercase, remove punctuation, trim whitespace for matching
- Contact information enriched through web scraping + optional paid API services
- Data staleness flagged if last_verified_at > 180 days

---

### scraping_jobs

Job queue and status tracking for EMD scraping operations.

**Schema:**
```sql
CREATE TABLE scraping_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    -- Job Configuration
    job_type VARCHAR(50) NOT NULL DEFAULT 'emd_scraping',  -- 'emd_scraping', 'enrichment', 'verification'
    target_county VARCHAR(100) NOT NULL,
    target_url TEXT,

    -- Scheduling
    scheduled_for TIMESTAMP WITH TIME ZONE NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,

    -- Status
    status VARCHAR(50) NOT NULL DEFAULT 'pending',  -- 'pending', 'running', 'completed', 'failed', 'cancelled'
    progress_percentage INTEGER DEFAULT 0 CHECK (progress_percentage >= 0 AND progress_percentage <= 100),

    -- Results
    reports_scraped INTEGER DEFAULT 0,
    leads_identified INTEGER DEFAULT 0,
    errors_encountered INTEGER DEFAULT 0,
    error_details JSONB,  -- Array of error messages

    -- Performance
    duration_seconds INTEGER,
    requests_made INTEGER DEFAULT 0,

    -- Retry Logic
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    next_retry_at TIMESTAMP WITH TIME ZONE,

    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
```

**Indexes:**
- `idx_scraping_jobs_org` ON organization_id
- `idx_scraping_jobs_status` ON status, organization_id
- `idx_scraping_jobs_scheduled` ON scheduled_for
- `idx_scraping_jobs_county` ON target_county, organization_id

**Business Rules:**
- Jobs scheduled based on organization's subscription tier quotas
- Failed jobs automatically retry with exponential backoff
- Completed jobs archived after 90 days

---

**Relationships:**
- scraped_reports → leads (one-to-one when report identifies unserviced pool)
- leads → research_data (many-to-one for management company enrichment)
- leads → customers (one-to-one when lead converts to customer)
- scraping_jobs → scraped_reports (one-to-many)

**Subscription Tier Integration:**
- Starter: 50 leads/month → soft limit warning at 45
- Professional: 200 leads/month → soft limit warning at 180
- Enterprise: Unlimited leads
- Usage tracked in organizations.feature_usage_limits JSONB field

---

## Data Isolation Strategy

### Organization ID Pattern

**Rule:** ALL tables with tenant-specific data MUST include `organization_id` foreign key.

**Exceptions:**
- Global tables: users (users belong to multiple orgs)
- System tables: Alembic migrations, etc.
- Global templates: service_plans, task_templates with organization_id = NULL

### Query Filtering

**Every query MUST filter by organization_id:**

```sql
-- ❌ BAD
SELECT * FROM customers;

-- ✅ GOOD
SELECT * FROM customers WHERE organization_id = '{current_org_id}';
```

**Service layer encapsulation enforces this automatically.**

### Foreign Key Cascade Rules

**Standard Pattern:**
- `organization_id` FK: ON DELETE RESTRICT (protect from accidental org deletion)
- Child records: ON DELETE CASCADE (deleting parent deletes children)

**Example:**
```sql
ALTER TABLE customers
ADD CONSTRAINT fk_customers_organization
FOREIGN KEY (organization_id) REFERENCES organizations(id);

ALTER TABLE route_stops
ADD CONSTRAINT fk_route_stops_route
FOREIGN KEY (route_id) REFERENCES routes(id) ON DELETE CASCADE;
```

---

## Entity Relationship Diagram

```
organizations (tenant boundary)
    |
    ├── users (many-to-many via organization_users)
    ├── organization_subscriptions (1:1 or 1:many)
    ├── usage_tracking (1:many)
    ├── service_plans (1:many, or NULL for global)
    |
    ├── customers (1:many)
    |       |
    |       ├── customer_service_agreements (1:many)
    |       ├── payment_methods (1:many)
    |       ├── water_features (1:many)
    |       |       |
    |       |       ├── equipment (1:many)
    |       |       |       └── equipment_maintenance_log (1:many)
    |       |       |
    |       |       ├── emd_inspections (1:many)
    |       |       |       └── emd_violations (1:many)
    |       |       |
    |       |       ├── chemical_logs (1:many)
    |       |       |       └── chemical_additions (1:many)
    |       |       |
    |       |       └── visit_features (many-to-many with service_visits)
    |       |
    |       └── service_visits (1:many)
    |               ├── visit_features (many-to-many with water_features)
    |               ├── visit_photos (1:many)
    |               └── visit_tasks (1:many)
    |                       └── task_templates (many:1)
    |
    ├── drivers (1:many)
    |
    ├── routes (1:many)
    |       └── route_stops (1:many)
    |
    └── task_templates (1:many, or NULL for global)

geocoding_cache (global, not org-specific)
```

---

## Migration Strategy

See **MIGRATION_PLAN.md** for complete step-by-step migration guide.

**Summary:**
1. Rollback billing fields from customers
2. Create SaaS foundation tables (organizations, users, organization_users)
3. Seed default organization
4. Add organization_id to all existing tables
5. Create normalized billing tables
6. Create SaaS subscription/usage tables
7. Add geocoding metadata
8. Create geocoding_cache
9. Create water features tables (with organization_id from start)
10. Normalize JSONB fields to separate tables

**Total Migrations:** 29
**Estimated Time:** 4-6 hours (dev testing)
**Production Downtime:** < 20 minutes

---

## Data Validation Rules

**All Tables:**
- UUIDs for all primary keys
- NOT NULL on foreign keys (except where NULL is meaningful)
- Timestamps with timezone awareness
- Soft deletes via is_active flag (where appropriate)

**Enums:**
- Validated at Pydantic schema level
- Database CHECK constraints for data integrity

**JSONB Fields:**
- Schema validation in Pydantic
- Extract frequently-queried fields to separate columns
- Index JSONB for query performance where needed

**Indexes:**
- organization_id on ALL tenant-specific tables (critical for isolation)
- Foreign keys (improves join performance)
- Frequently queried fields (service_day, status, etc.)
- Unique constraints (email, subdomain, etc.)

---

## Future Enhancements

### Planned Tables

1. **invoices** - Billing and invoicing (Phase 4)
2. **payments** - Payment tracking (Phase 4)
3. **estimates** - Service estimates and proposals (Phase 5)
4. **parts_inventory** - Parts and supplies tracking (Phase 6)
5. **vendor_contacts** - Equipment vendors (Phase 6)
6. **training_certifications** - Technician certifications (Phase 6)

### Performance Optimizations

- PostgreSQL partitioning on large tables (chemical_logs, usage_tracking)
- Read replicas for reporting queries
- Connection pooling (PgBouncer)
- Query result caching (Redis)

---

**Last Updated:** 2025-10-26
**Schema Version:** 3.0.0 (SaaS Multi-Tenant)
**Status:** SaaS Foundation Design Complete

**See Also:**
- SAAS_ARCHITECTURE.md - Complete multi-tenancy design
- MIGRATION_PLAN.md - Step-by-step migration guide
- MAP_PROVIDER_STRATEGY.md - Geocoding abstraction
- DESIGN_REVIEW.md - Design flaws and solutions
