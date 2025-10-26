# Migration Plan: SaaS Foundation Database Migrations

**Date:** 2025-10-26
**Status:** Ready for Execution
**Purpose:** Step-by-step guide for migrating database to multi-tenant SaaS architecture

---

## Executive Summary

This document provides the complete migration plan to transform RouteOptimizer from a single-tenant application to a multi-tenant SaaS platform.

**Critical Requirements:**
- ✅ Preserve ALL existing data (customers, drivers, routes, route_stops)
- ✅ Zero data loss
- ✅ Minimize downtime (< 5 minutes for production)
- ✅ Full rollback capability at each step
- ✅ Comprehensive testing before production

**Total Migrations:** 29 (see SAAS_FOUNDATION_TODO.md, Phase 1)

**Estimated Time:** 4-6 hours total (development database testing included)

---

## Table of Contents

1. [Pre-Migration Checklist](#pre-migration-checklist)
2. [Migration Sequence Overview](#migration-sequence-overview)
3. [Detailed Migration Steps](#detailed-migration-steps)
4. [Rollback Procedures](#rollback-procedures)
5. [Data Validation](#data-validation)
6. [Risk Assessment](#risk-assessment)
7. [Post-Migration Verification](#post-migration-verification)

---

## Pre-Migration Checklist

### Before Starting ANY Migrations

- [ ] **Backup database**
```bash
pg_dump -U routeoptimizer -d routeoptimizer -F c -b -v -f backup_pre_saas_$(date +%Y%m%d_%H%M%S).dump
```

- [ ] **Verify backup integrity**
```bash
pg_restore --list backup_pre_saas_*.dump | head -20
```

- [ ] **Test restore on separate database** (critical!)
```bash
createdb routeoptimizer_restore_test
pg_restore -U routeoptimizer -d routeoptimizer_restore_test -v backup_pre_saas_*.dump
psql -U routeoptimizer -d routeoptimizer_restore_test -c "SELECT COUNT(*) FROM customers;"
```

- [ ] **Stop application server** (production only)
```bash
sudo systemctl stop routeoptimizer
# OR
kill -TERM $(lsof -ti:7007)
```

- [ ] **Check Alembic migration history**
```bash
source venv/bin/activate
alembic current
alembic history
```

- [ ] **Document current migration version** (for rollback)
```bash
alembic current > migration_version_pre_saas.txt
```

- [ ] **Verify database connection**
```bash
psql -U routeoptimizer -d routeoptimizer -c "SELECT NOW();"
```

- [ ] **Check disk space** (migrations may temporarily increase DB size)
```bash
df -h /var/lib/postgresql
```

---

## Migration Sequence Overview

### Phase 1: Rollback Bad Migration (1 migration)

**Purpose:** Remove billing fields incorrectly added to customers table

1. **M001:** Rollback billing fields migration

### Phase 2: Create Core SaaS Tables (3 migrations)

**Purpose:** Add multi-tenancy foundation

2. **M002:** Create `organizations` table
3. **M003:** Create `users` table
4. **M004:** Create `organization_users` junction table

### Phase 3: Seed Default Organization (Data migration)

**Purpose:** Create default organization and assign existing data

5. **M005:** Seed default organization + admin user

### Phase 4: Add organization_id to Existing Tables (4 migrations)

**Purpose:** Add foreign keys for data isolation

6. **M006:** Add `organization_id` to `customers` table
7. **M007:** Add `organization_id` to `drivers` table
8. **M008:** Add `organization_id` to `routes` table
9. **M009:** Add `organization_id` to `route_stops` table

### Phase 5: Create Normalized Billing Tables (3 migrations)

**Purpose:** Proper billing architecture

10. **M010:** Create `service_plans` table
11. **M011:** Create `customer_service_agreements` table
12. **M012:** Create `payment_methods` table

### Phase 6: Create SaaS Subscription Tables (2 migrations)

**Purpose:** Subscription and usage tracking

13. **M013:** Create `organization_subscriptions` table
14. **M014:** Create `usage_tracking` table

### Phase 7: Add Map Provider Fields (2 migrations)

**Purpose:** Geocoding metadata tracking

15. **M015:** Add geocoding metadata to `customers` table
16. **M016:** Add geocoding metadata to `drivers` table

### Phase 8: Create Geocoding Cache (1 migration)

**Purpose:** Reduce API calls

17. **M017:** Create `geocoding_cache` table

---

## Detailed Migration Steps

### M001: Rollback Billing Fields Migration

**Purpose:** Remove billing fields from customers table (to be replaced with normalized tables)

**Risk Level:** 🟢 LOW (just added, easy to reverse)

**Commands:**

```bash
source venv/bin/activate
alembic downgrade -1
```

**Verification:**

```sql
-- Verify billing columns removed
\d customers;
-- Should NOT show: service_rate, billing_frequency, rate_notes, payment_method_type, etc.
```

**Rollback:** (if needed)

```bash
alembic upgrade +1
```

**Code Changes Required:**

```bash
# Revert model changes
git checkout HEAD -- app/models/customer.py
git checkout HEAD -- app/schemas/customer.py
```

---

### M002: Create Organizations Table

**Purpose:** Core tenant table for multi-tenancy

**Risk Level:** 🟢 LOW (new table, no dependencies)

**Migration File:** `migrations/versions/xxx_create_organizations_table.py`

```python
"""Create organizations table

Revision ID: xxx
Revises: xxx
Create Date: 2025-10-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = 'xxx'
down_revision = 'xxx'

def upgrade():
    op.create_table(
        'organizations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('slug', sa.String(100), nullable=False, unique=True),
        sa.Column('subdomain', sa.String(63), unique=True),

        # Subscription
        sa.Column('plan_tier', sa.String(50), nullable=False, server_default='starter'),
        sa.Column('subscription_status', sa.String(50), nullable=False, server_default='trial'),
        sa.Column('trial_ends_at', sa.DateTime),
        sa.Column('trial_days', sa.Integer, server_default='14'),

        # Billing
        sa.Column('billing_email', sa.String(255)),
        sa.Column('billing_address', sa.Text),
        sa.Column('stripe_customer_id', sa.String(100)),
        sa.Column('stripe_subscription_id', sa.String(100)),

        # Plan limits
        sa.Column('max_users', sa.Integer),
        sa.Column('max_customers', sa.Integer),
        sa.Column('max_techs', sa.Integer),
        sa.Column('max_routes_per_day', sa.Integer),

        # Features
        sa.Column('features_enabled', JSONB, server_default='{}'),

        # Map provider
        sa.Column('default_map_provider', sa.String(50), server_default='openstreetmap'),
        sa.Column('google_maps_api_key', sa.String(200)),

        # Customization
        sa.Column('logo_url', sa.String(500)),
        sa.Column('primary_color', sa.String(7)),
        sa.Column('timezone', sa.String(50), server_default='America/Los_Angeles'),

        # Metadata
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('onboarded_at', sa.DateTime),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()'))
    )

    # Indexes
    op.create_index('idx_orgs_subdomain', 'organizations', ['subdomain'])
    op.create_index('idx_orgs_slug', 'organizations', ['slug'])
    op.create_index('idx_orgs_subscription_status', 'organizations', ['subscription_status'])
    op.create_index('idx_orgs_stripe_customer', 'organizations', ['stripe_customer_id'])

def downgrade():
    op.drop_table('organizations')
```

**Commands:**

```bash
alembic revision --autogenerate -m "Create organizations table"
# Edit migration file to match above
alembic upgrade head
```

**Verification:**

```sql
SELECT * FROM organizations;
-- Should be empty table with correct schema
\d organizations;
```

**Rollback:**

```bash
alembic downgrade -1
```

---

### M003: Create Users Table

**Purpose:** Individual user accounts

**Risk Level:** 🟢 LOW (new table, no dependencies)

**Migration File:** `migrations/versions/xxx_create_users_table.py`

```python
def upgrade():
    op.create_table(
        'users',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('email', sa.String(255), unique=True, nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('first_name', sa.String(100)),
        sa.Column('last_name', sa.String(100)),

        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('email_verified_at', sa.DateTime),
        sa.Column('email_verification_token', sa.String(100)),
        sa.Column('password_reset_token', sa.String(100)),
        sa.Column('password_reset_expires_at', sa.DateTime),

        sa.Column('last_login_at', sa.DateTime),
        sa.Column('last_login_ip', sa.String(45)),
        sa.Column('login_count', sa.Integer, server_default='0'),

        sa.Column('timezone', sa.String(50)),
        sa.Column('locale', sa.String(10), server_default='en_US'),

        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()'))
    )

    # Indexes
    op.create_index('idx_users_email_lower', 'users', [sa.text('LOWER(email)')], unique=True)
    op.create_index('idx_users_email_verification_token', 'users', ['email_verification_token'])
    op.create_index('idx_users_password_reset_token', 'users', ['password_reset_token'])

def downgrade():
    op.drop_table('users')
```

**Commands:**

```bash
alembic revision --autogenerate -m "Create users table"
alembic upgrade head
```

**Verification:**

```sql
SELECT * FROM users;
\d users;
```

---

### M004: Create Organization Users Junction Table

**Purpose:** Many-to-many relationship between users and organizations

**Risk Level:** 🟢 LOW (new table, foreign keys to newly created tables)

**Migration File:** `migrations/versions/xxx_create_organization_users_table.py`

```python
def upgrade():
    op.create_table(
        'organization_users',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('organization_id', UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(50), nullable=False),
        sa.Column('is_primary_org', sa.Boolean, server_default='false'),
        sa.Column('invitation_token', sa.String(100)),
        sa.Column('invitation_accepted_at', sa.DateTime),
        sa.Column('invited_by', UUID(as_uuid=True), sa.ForeignKey('users.id')),

        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),

        sa.UniqueConstraint('organization_id', 'user_id', name='uq_org_user')
    )

    # Indexes
    op.create_index('idx_org_users_user', 'organization_users', ['user_id'])
    op.create_index('idx_org_users_org', 'organization_users', ['organization_id'])
    op.create_index('idx_org_users_role', 'organization_users', ['role'])
    op.create_index('idx_org_users_invitation_token', 'organization_users', ['invitation_token'])

def downgrade():
    op.drop_table('organization_users')
```

**Commands:**

```bash
alembic revision --autogenerate -m "Create organization_users table"
alembic upgrade head
```

---

### M005: Seed Default Organization

**Purpose:** Create "Demo Organization" for Brian's existing data

**Risk Level:** 🟡 MEDIUM (data creation, must preserve existing UUIDs)

**Migration File:** `migrations/versions/xxx_seed_default_organization.py`

**CRITICAL:** This is a **data migration**, not a schema migration. Must use `op.execute()`.

```python
"""Seed default organization and admin user

Revision ID: xxx
Revises: xxx
Create Date: 2025-10-26
"""
from alembic import op
import sqlalchemy as sa
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

revision = 'xxx'
down_revision = 'xxx'

def upgrade():
    # Create default organization
    op.execute("""
        INSERT INTO organizations (
            name, slug, subdomain,
            plan_tier, subscription_status,
            max_users, max_customers, max_techs,
            is_active, created_at, updated_at
        ) VALUES (
            'Demo Organization',
            'demo',
            'demo',
            'professional',
            'active',
            10,
            500,
            10,
            true,
            NOW(),
            NOW()
        )
    """)

    # Create admin user
    # IMPORTANT: Update password hash with actual hashed password
    password_hash = pwd_context.hash("CHANGE_ME_ON_FIRST_LOGIN")

    op.execute(f"""
        INSERT INTO users (
            email, password_hash, first_name, last_name,
            is_active, email_verified_at, created_at, updated_at
        ) VALUES (
            'brian@example.com',
            '{password_hash}',
            'Brian',
            '',
            true,
            NOW(),
            NOW(),
            NOW()
        )
    """)

    # Link user to organization as owner
    op.execute("""
        INSERT INTO organization_users (
            organization_id,
            user_id,
            role,
            is_primary_org,
            created_at, updated_at
        )
        SELECT
            (SELECT id FROM organizations WHERE slug = 'demo'),
            (SELECT id FROM users WHERE email = 'brian@example.com'),
            'owner',
            true,
            NOW(),
            NOW()
    """)

def downgrade():
    # Remove in reverse order (FK constraints)
    op.execute("DELETE FROM organization_users WHERE organization_id = (SELECT id FROM organizations WHERE slug = 'demo')")
    op.execute("DELETE FROM users WHERE email = 'brian@example.com'")
    op.execute("DELETE FROM organizations WHERE slug = 'demo'")
```

**Commands:**

```bash
alembic revision -m "Seed default organization"
# Edit migration file to match above
alembic upgrade head
```

**Verification:**

```sql
SELECT * FROM organizations WHERE slug = 'demo';
SELECT * FROM users WHERE email = 'brian@example.com';
SELECT * FROM organization_users;
```

---

### M006-M009: Add organization_id to Existing Tables

**Purpose:** Add foreign key to enable data isolation

**Risk Level:** 🟡 MEDIUM (altering production tables with data)

**Pattern (same for customers, drivers, routes, route_stops):**

```python
"""Add organization_id to customers

Revision ID: xxx
Revises: xxx
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'xxx'
down_revision = 'xxx'

def upgrade():
    # Add column (nullable first, to allow existing rows)
    op.add_column('customers',
        sa.Column('organization_id', UUID(as_uuid=True), nullable=True)
    )

    # Assign all existing customers to default organization
    op.execute("""
        UPDATE customers
        SET organization_id = (SELECT id FROM organizations WHERE slug = 'demo')
        WHERE organization_id IS NULL
    """)

    # Make NOT NULL after data migration
    op.alter_column('customers', 'organization_id', nullable=False)

    # Add foreign key
    op.create_foreign_key(
        'fk_customers_organization',
        'customers', 'organizations',
        ['organization_id'], ['id']
    )

    # Add index
    op.create_index('idx_customers_org', 'customers', ['organization_id'])

def downgrade():
    op.drop_index('idx_customers_org', 'customers')
    op.drop_constraint('fk_customers_organization', 'customers', type_='foreignkey')
    op.drop_column('customers', 'organization_id')
```

**Commands (repeat for each table):**

```bash
alembic revision --autogenerate -m "Add organization_id to customers"
# Manually edit to include UPDATE statement
alembic upgrade head

alembic revision --autogenerate -m "Add organization_id to drivers"
alembic upgrade head

alembic revision --autogenerate -m "Add organization_id to routes"
alembic upgrade head

alembic revision --autogenerate -m "Add organization_id to route_stops"
alembic upgrade head
```

**Verification After Each:**

```sql
-- Check all existing records assigned to demo org
SELECT organization_id, COUNT(*)
FROM customers
GROUP BY organization_id;

-- Should show all records with demo org_id, no NULLs
```

**Rollback (per table):**

```bash
alembic downgrade -1
```

---

### M010-M012: Create Normalized Billing Tables

**Purpose:** Replace billing fields on customers with proper architecture

**Risk Level:** 🟢 LOW (new tables)

See DESIGN_REVIEW.md for complete DDL.

**Commands:**

```bash
alembic revision --autogenerate -m "Create service_plans table"
alembic upgrade head

alembic revision --autogenerate -m "Create customer_service_agreements table"
alembic upgrade head

alembic revision --autogenerate -m "Create payment_methods table"
alembic upgrade head
```

---

### M013-M014: Create SaaS Subscription Tables

**Purpose:** Track subscriptions and usage

**Risk Level:** 🟢 LOW (new tables)

**Commands:**

```bash
alembic revision --autogenerate -m "Create organization_subscriptions table"
alembic upgrade head

alembic revision --autogenerate -m "Create usage_tracking table"
alembic upgrade head
```

---

### M015-M016: Add Geocoding Metadata

**Purpose:** Track which provider geocoded each address

**Risk Level:** 🟢 LOW (adding nullable columns)

**Pattern:**

```python
def upgrade():
    op.add_column('customers', sa.Column('geocoding_provider', sa.String(50)))
    op.add_column('customers', sa.Column('geocoded_by', UUID(as_uuid=True), sa.ForeignKey('users.id')))
    op.add_column('customers', sa.Column('geocoded_at', sa.DateTime))

    # Backfill existing geocoded customers
    op.execute("""
        UPDATE customers
        SET geocoding_provider = 'openstreetmap',
            geocoded_at = created_at
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
    """)

    op.create_index('idx_customers_geocoding_provider', 'customers', ['geocoding_provider'])

def downgrade():
    op.drop_index('idx_customers_geocoding_provider', 'customers')
    op.drop_column('customers', 'geocoded_at')
    op.drop_column('customers', 'geocoded_by')
    op.drop_column('customers', 'geocoding_provider')
```

**Commands:**

```bash
alembic revision --autogenerate -m "Add geocoding metadata to customers"
# Edit to include UPDATE statement
alembic upgrade head

alembic revision --autogenerate -m "Add geocoding metadata to drivers"
alembic upgrade head
```

---

### M017: Create Geocoding Cache

**Purpose:** Reduce API calls

**Risk Level:** 🟢 LOW (new table)

```python
def upgrade():
    op.create_table(
        'geocoding_cache',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('address_hash', sa.String(64), unique=True, nullable=False),
        sa.Column('normalized_address', sa.Text, nullable=False),
        sa.Column('latitude', sa.Float, nullable=False),
        sa.Column('longitude', sa.Float, nullable=False),
        sa.Column('formatted_address', sa.Text),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('confidence', sa.Float),
        sa.Column('metadata', JSONB),
        sa.Column('hit_count', sa.Integer, server_default='1'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
        sa.Column('last_used_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()'))
    )

    op.create_index('idx_geocoding_cache_hash', 'geocoding_cache', ['address_hash'])
    op.create_index('idx_geocoding_cache_provider', 'geocoding_cache', ['provider'])
    op.create_index('idx_geocoding_cache_last_used', 'geocoding_cache', ['last_used_at'])

def downgrade():
    op.drop_table('geocoding_cache')
```

**Commands:**

```bash
alembic revision --autogenerate -m "Create geocoding_cache table"
alembic upgrade head
```

---

## Rollback Procedures

### Complete Rollback (Undo All Migrations)

**When:** Something goes critically wrong, need to return to pre-migration state

**Steps:**

1. **Record current migration version**
```bash
alembic current > migration_version_rollback_from.txt
```

2. **Determine target version** (from pre-migration checklist)
```bash
cat migration_version_pre_saas.txt
```

3. **Rollback to target**
```bash
alembic downgrade <target_version>
```

4. **Verify rollback**
```sql
\dt  -- List tables (should match pre-migration state)
SELECT * FROM customers LIMIT 5;
SELECT * FROM drivers LIMIT 5;
```

5. **If rollback fails, restore from backup**
```bash
dropdb routeoptimizer
createdb routeoptimizer
pg_restore -U routeoptimizer -d routeoptimizer -v backup_pre_saas_*.dump
```

### Partial Rollback (Undo Last N Migrations)

**When:** Last few migrations failed, but earlier ones succeeded

```bash
# Undo last 3 migrations
alembic downgrade -3

# Undo to specific revision
alembic downgrade <revision_id>
```

---

## Data Validation

### After Each Migration

Run these queries to verify data integrity:

**1. Check row counts**
```sql
SELECT 'customers' AS table_name, COUNT(*) AS count FROM customers
UNION ALL
SELECT 'drivers', COUNT(*) FROM drivers
UNION ALL
SELECT 'routes', COUNT(*) FROM routes
UNION ALL
SELECT 'route_stops', COUNT(*) FROM route_stops;

-- Compare to pre-migration counts (should be identical)
```

**2. Check for NULLs in organization_id** (after M006-M009)
```sql
SELECT COUNT(*) FROM customers WHERE organization_id IS NULL;
SELECT COUNT(*) FROM drivers WHERE organization_id IS NULL;
SELECT COUNT(*) FROM routes WHERE organization_id IS NULL;
SELECT COUNT(*) FROM route_stops WHERE organization_id IS NULL;

-- All should return 0
```

**3. Check foreign key integrity**
```sql
-- Verify all customers belong to existing organization
SELECT c.id
FROM customers c
LEFT JOIN organizations o ON c.organization_id = o.id
WHERE o.id IS NULL;

-- Should return no rows
```

**4. Check demo organization assignment**
```sql
SELECT
    (SELECT COUNT(*) FROM customers WHERE organization_id = (SELECT id FROM organizations WHERE slug = 'demo')) AS customers,
    (SELECT COUNT(*) FROM drivers WHERE organization_id = (SELECT id FROM organizations WHERE slug = 'demo')) AS drivers,
    (SELECT COUNT(*) FROM routes WHERE organization_id = (SELECT id FROM organizations WHERE slug = 'demo')) AS routes,
    (SELECT COUNT(*) FROM route_stops WHERE organization_id = (SELECT id FROM organizations WHERE slug = 'demo')) AS route_stops;

-- All should match total table counts
```

---

## Risk Assessment

| Migration | Risk Level | Impact if Fails | Rollback Difficulty | Mitigation |
|-----------|------------|-----------------|---------------------|------------|
| M001 (Rollback billing) | 🟢 LOW | No impact | Easy | N/A |
| M002-M004 (New tables) | 🟢 LOW | App won't start | Easy (drop tables) | Test in dev first |
| M005 (Seed org) | 🟡 MEDIUM | No users, can't login | Easy (delete rows) | Verify INSERT statements |
| M006-M009 (Add org_id) | 🔴 HIGH | Data corruption if UPDATE fails | Medium | **CRITICAL: Test UPDATE on dev DB first** |
| M010-M014 (New tables) | 🟢 LOW | Features don't work | Easy | N/A |
| M015-M017 (Geocoding) | 🟢 LOW | Geocoding metadata missing | Easy | N/A |

**Highest Risk:** M006-M009 (adding organization_id and updating existing data)

**Mitigation:**
1. Test entire sequence on development database first
2. Verify UPDATE statements assign correct org_id
3. Take database snapshot before M006
4. Run on small table (route_stops) first, verify, then proceed

---

## Post-Migration Verification

### Full Application Test

After all migrations complete:

1. **Start application**
```bash
source venv/bin/activate
uvicorn app.main:app --reload --port 7007
```

2. **Test API endpoints**
```bash
# Health check
curl http://localhost:7007/health

# List customers (should return existing customers)
curl http://localhost:7007/api/customers | jq

# Get specific customer
curl http://localhost:7007/api/customers/<uuid> | jq
```

3. **Test frontend**
- Navigate to http://localhost:3000
- Verify customer list loads
- Verify customer detail page loads
- Verify routing works
- Verify no errors in browser console

4. **Check application logs**
```bash
tail -f /tmp/server.log
# Look for errors
```

5. **Verify database queries** (enable SQL logging)
```python
# app/database.py
engine = create_async_engine(
    DATABASE_URL,
    echo=True  # Enable SQL logging
)
```
- Run API request
- Verify queries include `WHERE organization_id = ...`

### Success Criteria

✅ All migrations applied successfully
✅ Zero data loss (row counts match pre-migration)
✅ All existing customers/drivers/routes assigned to demo organization
✅ Application starts without errors
✅ API endpoints return correct data
✅ Frontend loads and functions correctly
✅ Database queries include organization_id filter

---

## Execution Timeline

**Development Database:**
- Migrations: 1-2 hours
- Testing: 1-2 hours
- Fixes and iteration: 2-3 hours
- **Total: 4-7 hours**

**Production Database:** (after dev testing complete)
- Backup: 5 minutes
- Migrations: 10 minutes
- Verification: 5 minutes
- **Total Downtime: 20 minutes**

---

## Emergency Contacts

**If migration fails in production:**

1. **Immediately rollback** (see Rollback Procedures)
2. **Restore from backup** if rollback fails
3. **Document error** for debugging
4. **Do not attempt to fix forward** until root cause understood

**Post-mortem checklist:**
- What migration failed?
- What was the error message?
- What was database state when failed?
- Was rollback successful?
- What needs to change before retry?

---

## Summary

**Critical Path:**
1. Backup database ✅
2. Test complete migration sequence on dev database ✅
3. Fix any issues discovered ✅
4. Run on production with downtime window ✅
5. Verify success ✅
6. Celebrate ✅

**Next Steps After Migration:**
1. Update DATABASE_SCHEMA.md with final schema
2. Begin Phase 2: Code Structure Changes (auth, RBAC, API versioning)
3. Update application code to use organization_id in queries
4. Implement authentication endpoints
5. Test multi-organization isolation

---

**DO NOT PROCEED** to Phase 2 (code changes) until:
- ✅ All migrations successful
- ✅ Data validation complete
- ✅ Application functional
- ✅ Backups confirmed working
