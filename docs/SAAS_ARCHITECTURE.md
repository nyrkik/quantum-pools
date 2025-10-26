# SaaS Architecture: Multi-Tenant Design Specification

**Date:** 2025-10-26
**Status:** Foundation Design
**Purpose:** Complete specification for enterprise multi-tenant SaaS architecture

---

## Executive Summary

This document defines the multi-tenant SaaS architecture for RouteOptimizer, transforming it from a personal tool into an enterprise platform capable of serving thousands of pool service companies.

**Core Principle:** Data isolation, security, and scalability from day one.

**Business Model:** Subscription-based SaaS with tiered pricing (Starter, Professional, Enterprise).

---

## Table of Contents

1. [Multi-Tenancy Model](#multi-tenancy-model)
2. [Data Isolation Strategy](#data-isolation-strategy)
3. [Authentication & Authorization](#authentication--authorization)
4. [Subdomain Routing](#subdomain-routing)
5. [Organization Context Middleware](#organization-context-middleware)
6. [Role-Based Access Control (RBAC)](#role-based-access-control-rbac)
7. [Subscription Tiers & Pricing](#subscription-tiers--pricing)
8. [Feature Flags](#feature-flags)
9. [Usage Tracking & Billing](#usage-tracking--billing)
10. [Security Considerations](#security-considerations)
11. [Scaling Strategy](#scaling-strategy)

---

## Multi-Tenancy Model

### Overview

**Definition:** Multi-tenancy = multiple independent organizations (tenants) share the same application and database infrastructure while maintaining complete data isolation.

**Benefits:**
- Cost efficiency: $0.10/org vs. $20/org (separate deployments)
- Simplified maintenance: One codebase, one database
- Shared infrastructure costs across all customers
- Easier feature rollout (deploy once, all orgs benefit)

### Core Tables

#### 1. organizations

**Purpose:** Represents a pool service company (tenant).

```sql
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,  -- "Brian's Pool Service"
    slug VARCHAR(100) UNIQUE NOT NULL,  -- "brians-pool-service"
    subdomain VARCHAR(63) UNIQUE,  -- "brians" (for brians.poolscoutpro.com)

    -- Subscription management
    plan_tier VARCHAR(50) NOT NULL DEFAULT 'starter',  -- starter, professional, enterprise
    subscription_status VARCHAR(50) NOT NULL DEFAULT 'trial',  -- trial, active, past_due, canceled
    trial_ends_at TIMESTAMP,
    trial_days INTEGER DEFAULT 14,

    -- Billing
    billing_email VARCHAR(255),
    billing_address TEXT,
    stripe_customer_id VARCHAR(100),  -- Stripe customer ID
    stripe_subscription_id VARCHAR(100),  -- Stripe subscription ID

    -- Plan limits (NULL = unlimited for enterprise)
    max_users INTEGER,  -- Max user accounts
    max_customers INTEGER,  -- Max customers they can serve
    max_techs INTEGER,  -- Max technicians
    max_routes_per_day INTEGER,  -- Route optimization limit

    -- Feature flags (JSONB for flexibility)
    features_enabled JSONB DEFAULT '{}',
    -- Example: {"ai_features": true, "advanced_routing": true, "multi_day_scheduling": true}

    -- Map provider configuration
    default_map_provider VARCHAR(50) DEFAULT 'openstreetmap',
    google_maps_api_key VARCHAR(200),  -- Encrypted at application layer

    -- Customization
    logo_url VARCHAR(500),
    primary_color VARCHAR(7),  -- Hex color code
    timezone VARCHAR(50) DEFAULT 'America/Los_Angeles',

    -- Metadata
    is_active BOOLEAN NOT NULL DEFAULT true,
    onboarded_at TIMESTAMP,  -- When they completed onboarding
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_orgs_subdomain ON organizations(subdomain);
CREATE INDEX idx_orgs_slug ON organizations(slug);
CREATE INDEX idx_orgs_subscription_status ON organizations(subscription_status);
CREATE INDEX idx_orgs_stripe_customer ON organizations(stripe_customer_id);
```

**Business Rules:**
- `subdomain` must be unique (used for routing)
- `slug` must be URL-safe (lowercase, hyphens only)
- Trial period default: 14 days
- `is_active = false` → Organization suspended (billing issue, cancellation)

#### 2. users

**Purpose:** Individual user accounts (can belong to multiple organizations).

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,  -- bcrypt
    first_name VARCHAR(100),
    last_name VARCHAR(100),

    -- Account status
    is_active BOOLEAN NOT NULL DEFAULT true,
    email_verified_at TIMESTAMP,
    email_verification_token VARCHAR(100),
    password_reset_token VARCHAR(100),
    password_reset_expires_at TIMESTAMP,

    -- Tracking
    last_login_at TIMESTAMP,
    last_login_ip VARCHAR(45),  -- IPv6 support
    login_count INTEGER DEFAULT 0,

    -- Preferences
    timezone VARCHAR(50),
    locale VARCHAR(10) DEFAULT 'en_US',

    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_users_email_lower ON users(LOWER(email));
CREATE INDEX idx_users_email_verification_token ON users(email_verification_token);
CREATE INDEX idx_users_password_reset_token ON users(password_reset_token);
```

**Business Rules:**
- Email must be unique (case-insensitive)
- Password must be hashed with bcrypt (min 12 rounds)
- Email verification required before full access
- Password reset tokens expire after 1 hour

#### 3. organization_users

**Purpose:** Junction table linking users to organizations with roles.

```sql
CREATE TABLE organization_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL,  -- owner, admin, manager, technician, readonly
    is_primary_org BOOLEAN DEFAULT false,  -- User's default org on login
    invitation_token VARCHAR(100),  -- For pending invitations
    invitation_accepted_at TIMESTAMP,
    invited_by UUID REFERENCES users(id),

    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    UNIQUE(organization_id, user_id)
);

CREATE INDEX idx_org_users_user ON organization_users(user_id);
CREATE INDEX idx_org_users_org ON organization_users(organization_id);
CREATE INDEX idx_org_users_role ON organization_users(role);
CREATE INDEX idx_org_users_invitation_token ON organization_users(invitation_token);
```

**Business Rules:**
- One user can belong to multiple organizations
- One organization can have multiple users
- Only one `role` per user per organization
- Only one `is_primary_org = true` per user
- Role hierarchy: owner > admin > manager > technician > readonly

---

## Data Isolation Strategy

### Organization ID Pattern

**Rule:** ALL tables that store tenant-specific data MUST have `organization_id` foreign key.

**Exception:** Global tables (users, system settings, task templates with organization_id=NULL)

### Implementation

#### Add organization_id to Existing Tables

```sql
-- Customers (pool service clients)
ALTER TABLE customers ADD COLUMN organization_id UUID NOT NULL REFERENCES organizations(id);
CREATE INDEX idx_customers_org ON customers(organization_id);

-- Drivers (technicians)
ALTER TABLE drivers ADD COLUMN organization_id UUID NOT NULL REFERENCES organizations(id);
CREATE INDEX idx_drivers_org ON drivers(organization_id);

-- Routes (optimized schedules)
ALTER TABLE routes ADD COLUMN organization_id UUID NOT NULL REFERENCES organizations(id);
CREATE INDEX idx_routes_org ON routes(organization_id);

-- Route Stops (individual customer visits)
ALTER TABLE route_stops ADD COLUMN organization_id UUID NOT NULL REFERENCES organizations(id);
CREATE INDEX idx_route_stops_org ON route_stops(organization_id);

-- Future tables (water features, service visits, etc.)
-- ALL must include organization_id from creation
```

#### Database Session Scoping

**Option 1: Application-Level Filtering** (Recommended)

```python
# app/database.py
from sqlalchemy import event
from sqlalchemy.orm import Session

@event.listens_for(Session, "after_attach")
def receive_after_attach(session, instance):
    """Auto-filter all queries by organization_id."""
    if hasattr(instance, 'organization_id'):
        # Verify organization_id matches current context
        org_id = getattr(request.state, 'organization_id', None)
        if org_id and instance.organization_id != org_id:
            raise SecurityError("Cross-tenant data access attempted")
```

**Option 2: PostgreSQL Row-Level Security (Future Enhancement)**

```sql
-- Enable RLS on customers table
ALTER TABLE customers ENABLE ROW LEVEL SECURITY;

-- Create policy: Users can only see their org's customers
CREATE POLICY customers_isolation_policy ON customers
    USING (organization_id = current_setting('app.current_org_id')::UUID);
```

#### Query Patterns

**Every query MUST filter by organization_id:**

```python
# ❌ BAD (returns all customers across all orgs)
customers = await session.execute(select(Customer))

# ✅ GOOD (filtered by current organization)
org_id = request.state.organization_id
customers = await session.execute(
    select(Customer).where(Customer.organization_id == org_id)
)
```

**Service layer encapsulation:**

```python
# app/services/customer.py
class CustomerService:
    def __init__(self, db: AsyncSession, organization_id: UUID):
        self.db = db
        self.organization_id = organization_id

    async def get_all(self) -> list[Customer]:
        """Get all customers for current organization."""
        result = await self.db.execute(
            select(Customer)
            .where(Customer.organization_id == self.organization_id)
            .order_by(Customer.display_name)
        )
        return result.scalars().all()

    async def get_by_id(self, customer_id: UUID) -> Optional[Customer]:
        """Get customer by ID (with org_id check for security)."""
        result = await self.db.execute(
            select(Customer)
            .where(
                Customer.id == customer_id,
                Customer.organization_id == self.organization_id  # CRITICAL
            )
        )
        return result.scalar_one_or_none()
```

---

## Authentication & Authorization

### JWT-Based Authentication

#### JWT Payload Structure

```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "brian@example.com",
  "org_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "role": "owner",
  "sub": "550e8400-e29b-41d4-a716-446655440000",
  "iat": 1698364800,
  "exp": 1698451200
}
```

**Token Lifetime:** 24 hours (configurable)

**Refresh Strategy:** Sliding window (issue new token 1 hour before expiration)

#### Auth Service Implementation

```python
# app/services/auth.py
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta
import os

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

def hash_password(password: str) -> str:
    """Hash password with bcrypt."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash."""
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(user_id: UUID, org_id: UUID, role: str, email: str) -> str:
    """Create JWT access token."""
    payload = {
        "user_id": str(user_id),
        "email": email,
        "org_id": str(org_id),
        "role": role,
        "sub": str(user_id),
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str) -> dict:
    """Verify and decode JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_session)
) -> User:
    """Extract current user from JWT token and attach org context to request."""
    payload = verify_token(token)

    # Get user
    user = await db.get(User, payload["user_id"])
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    # Get organization membership
    org_id = UUID(payload["org_id"])
    org_user = await db.execute(
        select(OrganizationUser).where(
            OrganizationUser.user_id == user.id,
            OrganizationUser.organization_id == org_id
        )
    )
    org_user = org_user.scalar_one_or_none()
    if not org_user:
        raise HTTPException(status_code=403, detail="User not member of organization")

    # Attach context to request
    request.state.organization_id = org_id
    request.state.user_id = user.id
    request.state.role = payload["role"]

    # Update last login
    user.last_login_at = datetime.utcnow()
    user.last_login_ip = request.client.host
    user.login_count += 1
    await db.commit()

    return user
```

#### Login Flow

**1. User Login Endpoint**

```python
# app/api/v1/auth.py
from app.schemas.auth import LoginRequest, TokenResponse

@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: LoginRequest,
    db: AsyncSession = Depends(get_session)
):
    """Authenticate user and return JWT token."""

    # Get user by email
    result = await db.execute(
        select(User).where(func.lower(User.email) == credentials.email.lower())
    )
    user = result.scalar_one_or_none()

    # Verify password
    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Check if email verified
    if not user.email_verified_at:
        raise HTTPException(status_code=403, detail="Email not verified")

    # Check if active
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    # Get user's primary organization (or first if no primary set)
    result = await db.execute(
        select(OrganizationUser)
        .where(OrganizationUser.user_id == user.id)
        .order_by(OrganizationUser.is_primary_org.desc(), OrganizationUser.created_at)
    )
    org_user = result.scalars().first()

    if not org_user:
        raise HTTPException(status_code=403, detail="User not assigned to any organization")

    # Check if organization is active
    org = await db.get(Organization, org_user.organization_id)
    if not org.is_active:
        raise HTTPException(status_code=403, detail="Organization suspended")

    # Generate JWT
    access_token = create_access_token(
        user_id=user.id,
        org_id=org_user.organization_id,
        role=org_user.role,
        email=user.email
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_HOURS * 3600,
        user={
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
        },
        organization={
            "id": org.id,
            "name": org.name,
            "subdomain": org.subdomain,
            "plan_tier": org.plan_tier,
        }
    )
```

**2. Protected Route Example**

```python
# app/api/v1/customers.py
@router.get("/customers", response_model=list[CustomerResponse])
async def list_customers(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    request: Request = None
):
    """List all customers for current organization."""

    # Organization ID automatically attached to request.state by get_current_user
    org_id = request.state.organization_id

    # Query with org_id filter
    result = await db.execute(
        select(Customer)
        .where(Customer.organization_id == org_id)
        .order_by(Customer.display_name)
    )
    return result.scalars().all()
```

---

## Subdomain Routing

### URL Structure

**Format:** `{subdomain}.poolscoutpro.com`

**Examples:**
- Brian's Pool Service → `brians.poolscoutpro.com`
- Joe's Pools → `joes.poolscoutpro.com`
- Main app (login) → `app.poolscoutpro.com`

### DNS Configuration

```
Type    Host              Value
CNAME   *.poolscoutpro.com   app.poolscoutpro.com
A       app.poolscoutpro.com   <server_ip>
```

### Middleware Implementation

```python
# app/middleware/subdomain.py
from fastapi import Request
from app.models.organization import Organization

async def subdomain_middleware(request: Request, call_next):
    """Extract organization from subdomain."""

    # Get host header
    host = request.headers.get("host", "")

    # Extract subdomain (e.g., "brians" from "brians.poolscoutpro.com")
    parts = host.split(".")
    if len(parts) >= 3:  # subdomain.poolscoutpro.com
        subdomain = parts[0]

        # Skip special subdomains
        if subdomain in ["www", "app", "api"]:
            return await call_next(request)

        # Look up organization by subdomain
        db = request.state.db  # Assume db attached earlier in middleware chain
        result = await db.execute(
            select(Organization).where(Organization.subdomain == subdomain)
        )
        org = result.scalar_one_or_none()

        if org:
            # Attach organization to request state
            request.state.subdomain_org_id = org.id
            request.state.subdomain_org = org
        else:
            # Unknown subdomain
            raise HTTPException(status_code=404, detail="Organization not found")

    return await call_next(request)
```

### Authentication with Subdomain

**Option 1: Subdomain + JWT** (Recommended)
- User logs in at `app.poolscoutpro.com` → Selects organization → Redirected to `{subdomain}.poolscoutpro.com`
- JWT contains org_id → Validates against subdomain org_id
- Security: Prevents user from accessing different org's subdomain

**Option 2: Subdomain-Only** (No org selection)
- User logs in at `brians.poolscoutpro.com` directly
- Organization determined by subdomain only
- Simpler UX but requires users to remember subdomain

---

## Organization Context Middleware

### Request Flow

```
1. HTTP Request arrives
   ↓
2. Subdomain Middleware extracts org from subdomain (optional)
   ↓
3. Auth Middleware extracts JWT → verifies token → gets user
   ↓
4. Organization Context Middleware
   - Extract org_id from JWT payload
   - Validate against subdomain (if present)
   - Attach org_id, user_id, role to request.state
   ↓
5. Route Handler
   - Access request.state.organization_id
   - Use for all database queries
   ↓
6. Response
```

### Implementation

```python
# app/middleware/organization_context.py
async def organization_context_middleware(request: Request, call_next):
    """
    Attach organization context to request state.
    This middleware runs AFTER auth middleware.
    """

    # Skip for public routes
    if request.url.path in ["/api/v1/auth/login", "/api/v1/auth/register", "/docs"]:
        return await call_next(request)

    # Extract from JWT (attached by auth middleware)
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        raise HTTPException(status_code=401, detail="No authentication token")

    payload = verify_token(token)
    org_id = UUID(payload["org_id"])

    # Validate against subdomain (if present)
    if hasattr(request.state, "subdomain_org_id"):
        if request.state.subdomain_org_id != org_id:
            raise HTTPException(
                status_code=403,
                detail="JWT organization does not match subdomain organization"
            )

    # Attach to request state (accessible in route handlers)
    request.state.organization_id = org_id
    request.state.user_id = UUID(payload["user_id"])
    request.state.role = payload["role"]

    return await call_next(request)
```

---

## Role-Based Access Control (RBAC)

### Role Hierarchy

```
owner (highest privileges)
  ↓
admin
  ↓
manager
  ↓
technician
  ↓
readonly (lowest privileges)
```

### Role Definitions

| Role | Description | Permissions |
|------|-------------|-------------|
| **owner** | Organization owner (billing, full admin) | All permissions + billing management + delete organization |
| **admin** | Administrator (manage users, settings) | All permissions except billing |
| **manager** | Operations manager (routes, scheduling) | Manage customers, routes, technicians, view reports |
| **technician** | Field technician (mobile app user) | View assigned routes, update service visits, upload photos |
| **readonly** | View-only access (reports, analytics) | Read-only access to all data |

### Permission Matrix

| Permission | owner | admin | manager | technician | readonly |
|------------|-------|-------|---------|------------|----------|
| Manage billing | ✅ | ❌ | ❌ | ❌ | ❌ |
| Manage users | ✅ | ✅ | ❌ | ❌ | ❌ |
| Manage organization settings | ✅ | ✅ | ❌ | ❌ | ❌ |
| Create/edit customers | ✅ | ✅ | ✅ | ❌ | ❌ |
| Delete customers | ✅ | ✅ | ❌ | ❌ | ❌ |
| Create/edit routes | ✅ | ✅ | ✅ | ❌ | ❌ |
| View routes | ✅ | ✅ | ✅ | ✅ (own only) | ✅ |
| Update service visits | ✅ | ✅ | ✅ | ✅ (own only) | ❌ |
| Upload photos | ✅ | ✅ | ✅ | ✅ | ❌ |
| View reports | ✅ | ✅ | ✅ | ❌ | ✅ |
| Export data | ✅ | ✅ | ✅ | ❌ | ❌ |

### RBAC Implementation

#### Decorator-Based Authorization

```python
# app/middleware/rbac.py
from functools import wraps
from fastapi import HTTPException, Request

def require_role(allowed_roles: list[str]):
    """Decorator to enforce role-based access control."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request from kwargs
            request = kwargs.get('request') or next((arg for arg in args if isinstance(arg, Request)), None)
            if not request:
                raise HTTPException(500, "Request not found in route handler")

            # Check role
            user_role = getattr(request.state, 'role', None)
            if user_role not in allowed_roles:
                raise HTTPException(
                    status_code=403,
                    detail=f"Insufficient permissions. Required roles: {', '.join(allowed_roles)}"
                )

            return await func(*args, **kwargs)
        return wrapper
    return decorator

def require_permission(permission: str):
    """Decorator to enforce specific permissions."""
    # Map permissions to roles
    permission_map = {
        "manage_billing": ["owner"],
        "manage_users": ["owner", "admin"],
        "manage_settings": ["owner", "admin"],
        "manage_customers": ["owner", "admin", "manager"],
        "delete_customers": ["owner", "admin"],
        "manage_routes": ["owner", "admin", "manager"],
        "update_service_visits": ["owner", "admin", "manager", "technician"],
        "view_reports": ["owner", "admin", "manager", "readonly"],
    }

    allowed_roles = permission_map.get(permission, [])
    return require_role(allowed_roles)
```

#### Usage in Routes

```python
# app/api/v1/customers.py
@router.delete("/customers/{customer_id}")
@require_permission("delete_customers")
async def delete_customer(
    customer_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Delete customer (owner/admin only)."""
    org_id = request.state.organization_id

    # Get customer (with org_id check)
    customer = await db.execute(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.organization_id == org_id
        )
    )
    customer = customer.scalar_one_or_none()
    if not customer:
        raise HTTPException(404, "Customer not found")

    # Delete
    await db.delete(customer)
    await db.commit()

    return {"message": "Customer deleted"}
```

---

## Subscription Tiers & Pricing

### Tier Definitions

| Feature | Starter | Professional | Enterprise |
|---------|---------|--------------|------------|
| **Price** | $49/month | $149/month | Custom |
| **Users** | 3 | 10 | Unlimited |
| **Customers** | 50 | 500 | Unlimited |
| **Technicians** | 2 | 10 | Unlimited |
| **Routes/Day** | 5 | Unlimited | Unlimited |
| **Map Provider** | OpenStreetMap | Google Maps | Google Maps |
| **AI Features** | ❌ | Limited | Full |
| **Advanced Routing** | ❌ | ✅ | ✅ |
| **Multi-Day Scheduling** | ❌ | ✅ | ✅ |
| **Water Features Module** | ❌ | ✅ | ✅ |
| **API Access** | ❌ | ❌ | ✅ |
| **Custom Branding** | ❌ | ❌ | ✅ |
| **SLA** | Best effort | 99.5% | 99.9% |
| **Support** | Email | Email + Chat | Phone + Dedicated |

### Subscription Management Tables

#### organization_subscriptions

```sql
CREATE TABLE organization_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    stripe_subscription_id VARCHAR(100) UNIQUE,
    plan_tier VARCHAR(50) NOT NULL,  -- starter, professional, enterprise
    status VARCHAR(50) NOT NULL,  -- active, past_due, canceled, trialing
    monthly_price NUMERIC(10, 2),  -- Actual price (may differ from base if discounted)

    -- Billing cycle
    current_period_start TIMESTAMP NOT NULL,
    current_period_end TIMESTAMP NOT NULL,
    trial_start TIMESTAMP,
    trial_end TIMESTAMP,

    -- Cancellation
    cancel_at_period_end BOOLEAN DEFAULT false,
    canceled_at TIMESTAMP,
    cancellation_reason TEXT,

    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_org_subs_org ON organization_subscriptions(organization_id);
CREATE INDEX idx_org_subs_stripe ON organization_subscriptions(stripe_subscription_id);
CREATE INDEX idx_org_subs_status ON organization_subscriptions(status);
```

### Plan Enforcement

```python
# app/services/plan_limits.py
class PlanLimits:
    """Enforce plan limits per organization."""

    LIMITS = {
        "starter": {
            "max_users": 3,
            "max_customers": 50,
            "max_techs": 2,
            "max_routes_per_day": 5,
            "features": ["basic_routing"]
        },
        "professional": {
            "max_users": 10,
            "max_customers": 500,
            "max_techs": 10,
            "max_routes_per_day": None,  # Unlimited
            "features": ["advanced_routing", "multi_day_scheduling", "water_features"]
        },
        "enterprise": {
            "max_users": None,
            "max_customers": None,
            "max_techs": None,
            "max_routes_per_day": None,
            "features": ["advanced_routing", "multi_day_scheduling", "water_features", "ai_features", "api_access", "custom_branding"]
        }
    }

    @staticmethod
    async def check_limit(org: Organization, resource: str, current_count: int):
        """Check if organization has reached plan limit."""
        limits = PlanLimits.LIMITS.get(org.plan_tier, {})
        max_allowed = limits.get(f"max_{resource}")

        if max_allowed is not None and current_count >= max_allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Plan limit reached: {resource} (max: {max_allowed}). Upgrade your plan."
            )

    @staticmethod
    def has_feature(org: Organization, feature: str) -> bool:
        """Check if organization's plan includes feature."""
        limits = PlanLimits.LIMITS.get(org.plan_tier, {})
        return feature in limits.get("features", [])
```

**Usage:**

```python
# Before creating new user
await PlanLimits.check_limit(org, "users", current_user_count)

# Before enabling AI features
if not PlanLimits.has_feature(org, "ai_features"):
    raise HTTPException(403, "AI features not available on your plan")
```

---

## Feature Flags

### Purpose
- Enable/disable features per organization
- A/B testing
- Gradual rollout
- Custom enterprise features

### Database Storage

```sql
-- organizations.features_enabled (JSONB)
{
  "ai_features": true,
  "advanced_routing": true,
  "multi_day_scheduling": true,
  "water_features": true,
  "api_access": false,
  "custom_branding": false,
  "beta_features": true
}
```

### Feature Flag Service

```python
# app/services/feature_flags.py
class FeatureFlags:
    """Manage feature flags per organization."""

    @staticmethod
    def is_enabled(org: Organization, feature: str) -> bool:
        """Check if feature is enabled for organization."""
        features = org.features_enabled or {}
        return features.get(feature, False)

    @staticmethod
    async def enable_feature(db: AsyncSession, org_id: UUID, feature: str):
        """Enable feature for organization."""
        org = await db.get(Organization, org_id)
        features = org.features_enabled or {}
        features[feature] = True
        org.features_enabled = features
        await db.commit()

    @staticmethod
    async def disable_feature(db: AsyncSession, org_id: UUID, feature: str):
        """Disable feature for organization."""
        org = await db.get(Organization, org_id)
        features = org.features_enabled or {}
        features[feature] = False
        org.features_enabled = features
        await db.commit()
```

**Usage in Routes:**

```python
@router.post("/routes/optimize-ai")
async def optimize_route_with_ai(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """AI-powered route optimization (enterprise feature)."""

    org = await db.get(Organization, request.state.organization_id)

    # Check feature flag
    if not FeatureFlags.is_enabled(org, "ai_features"):
        raise HTTPException(403, "AI features not enabled for your organization")

    # AI route optimization logic...
```

---

## Usage Tracking & Billing

### Purpose
- Track resource usage for billing
- Enforce plan limits
- Analytics and reporting

### usage_tracking Table

```sql
CREATE TABLE usage_tracking (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    metric VARCHAR(100) NOT NULL,  -- customers_created, routes_optimized, api_calls, etc.
    quantity INTEGER DEFAULT 1,
    metadata JSONB,  -- Additional context
    recorded_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_usage_org ON usage_tracking(organization_id);
CREATE INDEX idx_usage_metric ON usage_tracking(metric);
CREATE INDEX idx_usage_recorded_at ON usage_tracking(recorded_at);
CREATE INDEX idx_usage_org_metric_date ON usage_tracking(organization_id, metric, recorded_at);
```

### Tracked Metrics

| Metric | Description | Usage |
|--------|-------------|-------|
| `customers_created` | New customer added | Plan limit enforcement |
| `users_invited` | User invited to org | Plan limit enforcement |
| `routes_optimized` | Route optimization run | Plan limit + analytics |
| `api_calls` | API requests (enterprise) | Billing + rate limiting |
| `geocoding_requests` | Geocoding API calls | Cost tracking |
| `service_visits_logged` | Service visits recorded | Analytics |
| `photos_uploaded` | Photos uploaded | Storage billing |

### Usage Tracking Service

```python
# app/services/usage_tracking.py
class UsageTracker:
    """Track usage metrics for billing and analytics."""

    @staticmethod
    async def track(
        db: AsyncSession,
        org_id: UUID,
        metric: str,
        quantity: int = 1,
        metadata: dict = None
    ):
        """Record usage metric."""
        usage = UsageTracking(
            organization_id=org_id,
            metric=metric,
            quantity=quantity,
            metadata=metadata
        )
        db.add(usage)
        await db.commit()

    @staticmethod
    async def get_usage(
        db: AsyncSession,
        org_id: UUID,
        metric: str,
        start_date: datetime,
        end_date: datetime
    ) -> int:
        """Get total usage for metric in date range."""
        result = await db.execute(
            select(func.sum(UsageTracking.quantity))
            .where(
                UsageTracking.organization_id == org_id,
                UsageTracking.metric == metric,
                UsageTracking.recorded_at >= start_date,
                UsageTracking.recorded_at < end_date
            )
        )
        return result.scalar() or 0
```

**Usage:**

```python
# Track customer creation
await UsageTracker.track(db, org_id, "customers_created", metadata={"customer_id": str(customer.id)})

# Track route optimization
await UsageTracker.track(db, org_id, "routes_optimized", metadata={"route_id": str(route.id), "num_stops": 25})
```

---

## Security Considerations

### 1. Password Security
- Bcrypt hashing (min 12 rounds)
- Password strength requirements: min 8 chars, uppercase, lowercase, number
- Password reset with time-limited tokens (1 hour expiration)
- Rate limiting on login attempts (5 failures = 15 min lockout)

### 2. JWT Security
- Secret key stored in environment variable (never in code)
- HTTPS only (no tokens over HTTP)
- Short expiration (24 hours)
- Refresh token rotation

### 3. Data Isolation
- organization_id on ALL queries (never trust client input)
- Service layer enforces org_id filtering
- Database row-level security (future)
- Audit logging for cross-org access attempts

### 4. API Security
- CORS configuration (whitelist subdomains only)
- Rate limiting (100 req/min per org)
- API key authentication for public API (enterprise tier)
- Request size limits (10MB max)

### 5. Input Validation
- Pydantic schemas for all API inputs
- SQL injection prevention (parameterized queries only)
- XSS prevention (escape HTML in outputs)
- CSRF protection (for cookie-based auth, if used)

---

## Scaling Strategy

### Database Scaling

**Phase 1: Single PostgreSQL (0-1000 orgs)**
- Vertical scaling (increase RAM/CPU)
- Read replicas for reporting queries

**Phase 2: Sharding by Organization (1000-10,000 orgs)**
- Shard key: organization_id
- Large orgs get dedicated shard
- Small orgs share shards

**Phase 3: Multi-Region (10,000+ orgs)**
- Regional databases (US-West, US-East, EU)
- Geo-routing by organization location

### Application Scaling

**Horizontal Scaling:**
- Stateless API servers (no session storage)
- Load balancer distributes requests
- Auto-scaling based on CPU/memory

**Caching:**
- Redis for geocoding cache
- Redis for session storage
- CDN for static assets

**Background Jobs:**
- Celery + Redis for async tasks
- Separate worker pools for:
  - Route optimization (CPU-intensive)
  - Geocoding (I/O-intensive)
  - Email sending
  - EMD scraping

---

## Summary

**Multi-Tenancy Foundation:**
- organizations, users, organization_users tables
- organization_id on ALL tables
- JWT-based auth with org context
- Subdomain routing (optional)

**Security:**
- Bcrypt passwords, JWT tokens, data isolation
- RBAC with 5 role levels
- Plan limit enforcement

**Business Model:**
- 3 subscription tiers (Starter, Professional, Enterprise)
- Usage tracking for billing
- Feature flags for gradual rollout

**Next Steps:**
1. Review this architecture with team
2. Create MIGRATION_PLAN.md for step-by-step implementation
3. Begin Phase 1: Database Foundation (create SaaS tables)
