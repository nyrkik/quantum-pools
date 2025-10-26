# Architecture Reference

**Last Updated:** 2025-10-26

**Note:** This document describes the SaaS multi-tenant architecture. See [SAAS_ARCHITECTURE.md](SAAS_ARCHITECTURE.md) for detailed multi-tenancy specifications.

## Tech Stack

- **Backend:** FastAPI (async), Python 3.11+
- **Database:** PostgreSQL (async SQLAlchemy 2.0)
- **Authentication:** JWT with bcrypt password hashing
- **Authorization:** Role-based access control (RBAC)
- **Optimization:** Google OR-Tools VRP solver
- **Geocoding:** Provider abstraction (OpenStreetMap, Google Maps)
- **Frontend:** Vanilla JS + Leaflet.js maps
- **PDF Export:** ReportLab
- **Payments:** Stripe (planned)
- **File Storage:** Digital Ocean Spaces (planned)

## Multi-Tenancy Architecture

**Tenant Isolation Pattern:** Organization-based with database-level isolation

### Core Concepts

**Organization = Tenant**
- Each organization is a separate customer account
- All tenant-specific data includes `organization_id` foreign key
- Data access is automatically scoped to current organization
- Complete logical isolation within shared database

**Subdomain Routing (Planned):**
```
brians.poolscoutpro.com → organization: "brians"
acme.poolscoutpro.com → organization: "acme"
```

**Current Implementation:** Single domain with organization context in JWT

### Data Isolation Strategy

**Automatic Organization Scoping:**
```python
# ❌ NEVER query without organization filter
SELECT * FROM customers;

# ✅ ALWAYS include organization_id
SELECT * FROM customers WHERE organization_id = '{current_org_id}';
```

**SQLAlchemy Pattern (Planned):**
```python
# Middleware injects organization_id into all queries
async def get_organization_context(request: Request) -> str:
    """Extract org_id from JWT token"""
    token = request.headers.get("Authorization")
    payload = decode_jwt(token)
    return payload["org_id"]

# Service layer automatically scopes queries
class CustomerService:
    async def get_customers(self, org_id: str):
        return await db.execute(
            select(Customer).where(Customer.organization_id == org_id)
        )
```

**Global vs Tenant-Specific Tables:**

**Global (No organization_id):**
- `service_plans` - Shared plan definitions
- `alembic_version` - Migration tracking

**Tenant-Specific (Has organization_id):**
- `organizations` - The tenant boundary
- `users`, `organization_users` - User accounts
- `customers`, `drivers`, `routes` - Core data
- `customer_service_agreements` - Billing
- `water_features`, `visit_features` - Service tracking
- `geocoding_requests`, `geocoding_cache` - Map provider usage

### Organization Structure

**Tables:**
- `organizations` - Tenant accounts
- `users` - User accounts (can belong to multiple orgs)
- `organization_users` - Many-to-many with role assignment

**Key Fields:**
```sql
organizations:
  - id (UUID, PK)
  - name (VARCHAR, unique slug)
  - display_name (VARCHAR)
  - subscription_tier (starter|professional|enterprise)
  - subscription_status (trial|active|suspended|cancelled)
  - geocoding_provider (openstreetmap|google)
  - feature_flags (JSONB)

organization_users:
  - organization_id (UUID, FK)
  - user_id (UUID, FK)
  - role (owner|admin|manager|technician|readonly)
  - is_active (BOOLEAN)
```

**See Also:**
- [SAAS_ARCHITECTURE.md](SAAS_ARCHITECTURE.md) - Complete multi-tenancy design
- [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) - Full schema with SaaS tables

## Authentication & Authorization

### Authentication Flow

**JWT-Based Authentication:**
```
1. POST /api/v1/auth/login (email, password)
2. Server validates credentials (bcrypt password check)
3. Server issues JWT token with payload:
   {
     "user_id": "uuid",
     "email": "user@example.com",
     "org_id": "uuid",
     "role": "admin",
     "exp": 1698451200
   }
4. Client includes token in Authorization header
5. Middleware validates token and extracts org_id
6. All queries automatically scoped to org_id
```

**Password Security:**
- bcrypt hashing with salt
- Minimum password requirements (planned)
- Password reset via email (planned)

### Authorization - Role-Based Access Control (RBAC)

**Roles (Hierarchical):**
1. **owner** - Full access, billing, delete organization
2. **admin** - Manage users, all data operations
3. **manager** - Create/edit routes, customers, drivers
4. **technician** - View routes, mark visits complete
5. **readonly** - View-only access

**Permission Matrix:**

| Action | owner | admin | manager | technician | readonly |
|--------|-------|-------|---------|------------|----------|
| Manage billing | ✅ | ❌ | ❌ | ❌ | ❌ |
| Manage users | ✅ | ✅ | ❌ | ❌ | ❌ |
| Delete organization | ✅ | ❌ | ❌ | ❌ | ❌ |
| Create/edit routes | ✅ | ✅ | ✅ | ❌ | ❌ |
| Create/edit customers | ✅ | ✅ | ✅ | ❌ | ❌ |
| View routes | ✅ | ✅ | ✅ | ✅ | ✅ |
| Mark visits complete | ✅ | ✅ | ✅ | ✅ | ❌ |

**Implementation (Planned):**
```python
from fastapi import Depends, HTTPException

async def require_role(required_role: str):
    def dependency(current_user: User = Depends(get_current_user)):
        if not has_permission(current_user.role, required_role):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return dependency

@router.post("/api/v1/customers")
async def create_customer(
    data: CustomerCreate,
    user: User = Depends(require_role("manager"))
):
    # Only manager+ can create customers
    pass
```

**See Also:**
- [SAAS_ARCHITECTURE.md](SAAS_ARCHITECTURE.md) - Complete RBAC specification

## Database Schema

**See [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) for complete schema with all SaaS tables, relationships, and constraints.**

### SaaS Foundation Tables

**organizations** (Tenant boundary)
- `id` UUID (PK)
- `name` VARCHAR(100) unique - URL-safe slug
- `display_name` VARCHAR(200) - Friendly name
- `subscription_tier` VARCHAR(50) - starter|professional|enterprise
- `subscription_status` VARCHAR(50) - trial|active|suspended|cancelled
- `trial_end_date` DATE - When trial expires
- `geocoding_provider` VARCHAR(50) - openstreetmap|google
- `feature_flags` JSONB - {ai_recommendations: true, advanced_reporting: false}
- `settings` JSONB - Organization-specific configuration
- `is_active` BOOLEAN
- timestamps

**users** (Authentication)
- `id` UUID (PK)
- `email` VARCHAR(255) unique - Login identifier
- `password_hash` VARCHAR(255) - bcrypt hashed password
- `full_name` VARCHAR(200)
- `is_active` BOOLEAN
- `last_login_at` TIMESTAMP
- timestamps

**organization_users** (Authorization - Many-to-many junction)
- `id` UUID (PK)
- `organization_id` UUID (FK to organizations)
- `user_id` UUID (FK to users)
- `role` VARCHAR(50) - owner|admin|manager|technician|readonly
- `is_active` BOOLEAN - User active in THIS organization
- `invited_at` TIMESTAMP
- `joined_at` TIMESTAMP
- timestamps
- **UNIQUE(organization_id, user_id)** - User can only have one role per org

### Core Business Tables (All have organization_id)

**customers**
- `id` UUID (PK)
- `organization_id` UUID (FK to organizations) - **Tenant isolation**
- `name`, `address` (strings)
- `latitude`, `longitude` (float, nullable)
- `assigned_driver_id` UUID (FK to drivers, nullable)
- `service_type` (residential | commercial)
- `difficulty` (1-5 scale)
- `service_day` (monday-sunday, primary day)
- `service_days_per_week` (1, 2, or 3)
- `service_schedule` (e.g., "Mo/Th", "Mo/We/Fr", nullable for 1x/week)
- `locked` (boolean - prevents day reassignment)
- `time_window_start`, `time_window_end` (time, nullable)
- `notes`, `is_active`, timestamps

**drivers**
- `id` UUID (PK)
- `organization_id` UUID (FK to organizations) - **Tenant isolation**
- `name`, `email`, `phone`
- `color` (hex code for route visualization)
- `start_location_address`, `start_latitude`, `start_longitude`
- `end_location_address`, `end_latitude`, `end_longitude`
- `working_hours_start`, `working_hours_end` (time)
- `max_customers_per_day` (integer, default 20)
- `is_active`, `notes`, timestamps

**routes**
- `id` UUID (PK)
- `organization_id` UUID (FK to organizations) - **Tenant isolation**
- `driver_id` UUID (FK to drivers, cascade delete)
- `service_day` (monday-sunday)
- `total_duration_minutes`, `total_distance_miles`, `total_customers`
- `optimization_algorithm` (default: google-or-tools)
- `optimization_score` (float, nullable)
- timestamps

**route_stops**
- `id` UUID (PK)
- `route_id` UUID (FK to routes, cascade delete)
- `customer_id` UUID (FK to customers, cascade delete)
- `sequence` (integer, 1-based order)
- `estimated_arrival_time`, `estimated_service_duration`
- `estimated_drive_time_from_previous`, `estimated_distance_from_previous`
- `created_at`

### Billing Tables (Normalized schema)

**service_plans** (Global - no organization_id)
- `id` UUID (PK)
- `name` VARCHAR(100) - "Weekly Standard", "Bi-weekly Premium"
- `base_rate` NUMERIC(10,2) - Default price
- `billing_frequency` VARCHAR(20) - weekly|biweekly|monthly
- `is_active` BOOLEAN
- timestamps

**customer_service_agreements** (Tenant-specific)
- `id` UUID (PK)
- `organization_id` UUID (FK to organizations) - **Tenant isolation**
- `customer_id` UUID (FK to customers)
- `service_plan_id` UUID (FK to service_plans, nullable) - NULL for custom pricing
- `custom_rate` NUMERIC(10,2) - Overrides service_plan.base_rate
- `effective_date` DATE - When agreement starts
- `end_date` DATE - NULL = current active agreement
- timestamps
- **Pattern:** Query `WHERE end_date IS NULL` for current agreement

**payment_methods** (Tenant-specific)
- `id` UUID (PK)
- `organization_id` UUID (FK to organizations) - **Tenant isolation**
- `customer_id` UUID (FK to customers)
- `type` VARCHAR(50) - card|bank_account|check
- `stripe_payment_method_id` VARCHAR(255) - Stripe reference
- `last_four` VARCHAR(4) - Card/account last 4 digits
- `is_default` BOOLEAN
- `is_active` BOOLEAN
- timestamps

### Map Provider Tables

**geocoding_requests** (Usage tracking per org)
- `id` UUID (PK)
- `organization_id` UUID (FK to organizations) - **Tenant isolation**
- `address` TEXT - Raw address geocoded
- `provider` VARCHAR(50) - openstreetmap|google
- `latitude`, `longitude` FLOAT - Result
- `success` BOOLEAN
- `response_time_ms` INTEGER
- timestamps

**geocoding_cache** (Shared cache for all orgs)
- `id` UUID (PK)
- `address_normalized` VARCHAR(500) UNIQUE - Normalized address key
- `provider` VARCHAR(50)
- `latitude`, `longitude` FLOAT
- `confidence_score` FLOAT - Provider's confidence (0.0-1.0)
- `last_used_at` TIMESTAMP - For cache eviction
- timestamps

### Relationships

**Multi-Tenant Boundary:**
- Organization → Organization_Users (one-to-many)
- Organization → Customers, Drivers, Routes (one-to-many, tenant isolation)
- User → Organization_Users (one-to-many, user can belong to multiple orgs)

**Core Business:**
- Driver → Routes (one-to-many, cascade delete)
- Route → Stops (one-to-many, cascade delete)
- Customer → Stops (one-to-many, cascade delete)
- Customer → Driver (many-to-one via assigned_driver_id, nullable)
- Customer → Service Agreements (one-to-many, audit trail)
- Customer → Payment Methods (one-to-many)

## API Endpoints

**API Version:** `/api/v1/` prefix for all endpoints

**Authentication:** All endpoints (except `/health`, `/api/v1/auth/*`) require JWT token in `Authorization: Bearer {token}` header.

**Organization Scoping:** All data access automatically filtered by `organization_id` from JWT token.

### Authentication `/api/v1/auth`
- `POST /register` - Create new user account
- `POST /login` - Login with email/password, returns JWT token
- `POST /logout` - Invalidate JWT token (planned)
- `POST /refresh` - Refresh expired JWT token (planned)
- `POST /forgot-password` - Send password reset email (planned)
- `POST /reset-password` - Reset password with token (planned)

### Organizations `/api/v1/organizations`
- `GET /current` - Get current organization details
- `PATCH /current` - Update organization settings (owner only)
- `GET /current/usage` - Get usage statistics (billing, geocoding, customers)

### Users `/api/v1/users`
- `GET /me` - Get current user profile
- `PATCH /me` - Update current user profile
- `GET /` - List users in current organization (admin+)
- `POST /invite` - Invite user to organization (admin+)
- `PATCH /{user_id}/role` - Change user role (admin+)
- `DELETE /{user_id}` - Remove user from organization (admin+)

### Customers `/api/v1/customers`
- `POST /` - Create customer (auto-geocodes address) (manager+)
- `GET /` - List with pagination/filters (service_day, service_type, is_active)
- `GET /{id}` - Get single customer
- `PUT /{id}` - Update customer (full) (manager+)
- `PATCH /{id}` - Update customer (partial) (manager+)
- `DELETE /{id}` - Delete customer (manager+)
- `GET /service-day/{day}` - Get customers for specific day

### Drivers `/api/v1/drivers`
- `POST /` - Create driver (auto-geocodes locations) (manager+)
- `GET /` - List with pagination/filters (is_active)
- `GET /active` - Get all active drivers
- `GET /{id}` - Get single driver
- `PUT /{id}` - Update driver (manager+)
- `DELETE /{id}` - Delete driver (manager+)

### Routes `/api/v1/routes`
- `POST /optimize` - Generate optimized routes (doesn't save to DB) (manager+)
- `POST /save` - Save optimized routes to database (manager+)
- `GET /day/{service_day}` - Get saved routes for day
- `DELETE /day/{service_day}` - Delete all routes for day (manager+)
- `GET /{route_id}` - Get route details with stops
- `GET /{route_id}/pdf` - Download PDF route sheet
- `GET /day/{service_day}/pdf` - Download PDF for all routes on day
- `PATCH /{route_id}/stops` - Update stop sequence (manager+)
- `POST /{route_id}/stops/{stop_id}/move` - Move stop to different route (manager+)

### Imports `/api/v1/imports`
- `POST /customers/csv` - Bulk import customers from CSV (manager+)
- `GET /customers/template` - Download CSV template

### Billing `/api/v1/billing` (Planned)
- `GET /plans` - List available service plans
- `POST /customers/{id}/agreements` - Create service agreement for customer (manager+)
- `GET /customers/{id}/agreements` - Get customer's service agreements
- `POST /customers/{id}/payment-methods` - Add payment method (manager+)
- `GET /customers/{id}/payment-methods` - List payment methods
- `DELETE /payment-methods/{id}` - Remove payment method (manager+)

### Subscription `/api/v1/subscription` (Planned)
- `GET /` - Get current subscription details (owner+)
- `POST /upgrade` - Upgrade subscription tier (owner)
- `POST /cancel` - Cancel subscription (owner)
- `GET /invoices` - List invoices (owner+)

### Geocoding `/api/v1/geocoding`
- `GET /geocode?address=...` - Geocode single address
- `GET /validate-coordinates` - Validate all customer coordinates (manager+)
- `GET /usage` - Get geocoding usage statistics (admin+)

### Other
- `GET /api/v1/config` - Get frontend config (maps provider, feature flags)
- `GET /health` - Health check (no auth required)

## Optimization Service

**Location:** `app/services/optimization.py`

**Key Method:** `optimize_routes(customers, drivers, service_day, allow_day_reassignment, optimization_mode)`

**Modes:**
- `full` - Optimize all customers, can reassign drivers
- `refine` - Only customers with assigned_driver_id, keeps driver assignments

**Flow:**
1. Filter customers by day (if specified)
2. Build distance matrix (lat/lon → miles)
3. Calculate service durations (type + difficulty)
4. Configure OR-Tools VRP solver with constraints
5. Run optimization (120 second limit)
6. Parse solution into route data

**Constraints:**
- Driver working hours
- Max customers per driver
- Service time windows (if specified)
- Distance + service time limits

**Special Handling:**
- "All Days" without reassignment → optimize each day separately
- "All Days" with reassignment → not yet implemented (returns message)

## Geocoding Service

**Location:** `app/services/geocoding.py`

**Provider Abstraction Pattern:**
- `GeocodingProvider` interface (ABC) for provider implementations
- Factory pattern selects provider based on organization configuration
- Supports multiple providers: OpenStreetMap (Nominatim), Google Maps
- Per-organization provider configuration via `organizations.geocoding_provider`

**Implementation:**
```python
from abc import ABC, abstractmethod

class GeocodingProvider(ABC):
    @abstractmethod
    async def geocode(self, address: str) -> Optional[GeocodingResult]:
        """Convert address to lat/lon coordinates"""
        pass

    @abstractmethod
    async def reverse_geocode(self, lat: float, lon: float) -> Optional[str]:
        """Convert lat/lon to address"""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return provider identifier"""
        pass

class GeocodingFactory:
    @staticmethod
    def get_provider(org_id: str, provider_name: str) -> GeocodingProvider:
        if provider_name == "openstreetmap":
            return OpenStreetMapProvider()
        elif provider_name == "google":
            return GoogleMapsProvider()
        else:
            raise ValueError(f"Unknown provider: {provider_name}")
```

**Features:**
- Rate limiting for batch operations (`geocode_with_rate_limit`)
- Automatically geocodes on customer/driver create/update
- Usage tracking per organization (`geocoding_requests` table)
- Shared cache for all organizations (`geocoding_cache` table)
- Normalized address matching for cache hits

**See Also:**
- [MAP_PROVIDER_STRATEGY.md](MAP_PROVIDER_STRATEGY.md) - Complete provider abstraction design

## PDF Export Service

**Location:** `app/services/pdf_export.py`

- Single route sheets
- Multi-route daily packets
- Uses ReportLab for PDF generation
- Automatically includes organization branding (planned)
- Per-organization PDF templates (planned)

## Security

### Authentication Security

**JWT Token:**
- HS256 algorithm (HMAC with SHA-256)
- Secret key from environment variable
- Token expiration: 24 hours (configurable)
- Refresh tokens for extended sessions (planned)

**Password Security:**
- bcrypt hashing with automatic salt generation
- Minimum password requirements (planned):
  - 8+ characters
  - At least one uppercase, lowercase, number
  - No common passwords (dictionary check)

**Session Management:**
- Stateless JWT tokens (no server-side session storage)
- Token invalidation on logout via blacklist (planned)
- Automatic token refresh before expiration (planned)

### Authorization Security

**Organization Isolation:**
- Middleware extracts `org_id` from JWT token
- All database queries automatically filtered by `org_id`
- Cross-organization access prevented at middleware level
- No way to access data outside current organization

**Role-Based Access:**
- Role stored in JWT token and `organization_users` table
- Permission checks at endpoint level using dependencies
- Hierarchical permissions (owner > admin > manager > technician > readonly)

**Example Middleware (Planned):**
```python
@app.middleware("http")
async def organization_context_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/v1/"):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        try:
            payload = decode_jwt(token)
            request.state.org_id = payload["org_id"]
            request.state.user_id = payload["user_id"]
            request.state.role = payload["role"]
        except InvalidTokenError:
            return JSONResponse(status_code=401, content={"detail": "Invalid token"})

    response = await call_next(request)
    return response
```

### API Security

**CORS (Cross-Origin Resource Sharing):**
- Configured via `allowed_origins` in config
- Restricts API access to authorized domains
- Credentials support for cookie-based auth (if needed)

**Rate Limiting (Planned):**
- Per-IP rate limiting for authentication endpoints
- Per-organization rate limiting for API calls
- Geocoding rate limiting per provider terms

**Security Headers (Planned):**
```python
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response
```

**Input Validation:**
- Pydantic schemas for all request bodies
- Type validation and coercion
- Length limits on string fields
- SQL injection prevention via parameterized queries (SQLAlchemy ORM)

## Error Handling

### Error Response Format

**Standardized Error Response:**
```json
{
  "detail": "Human-readable error message",
  "error_code": "INVALID_CREDENTIALS",
  "status_code": 401,
  "timestamp": "2025-10-26T12:34:56Z"
}
```

### HTTP Status Codes

**Success (2xx):**
- `200 OK` - Successful GET, PUT, PATCH
- `201 Created` - Successful POST (resource created)
- `204 No Content` - Successful DELETE

**Client Errors (4xx):**
- `400 Bad Request` - Invalid input data (Pydantic validation)
- `401 Unauthorized` - Missing or invalid JWT token
- `403 Forbidden` - Valid token but insufficient permissions
- `404 Not Found` - Resource doesn't exist or not in organization
- `409 Conflict` - Duplicate resource (e.g., email already exists)
- `422 Unprocessable Entity` - Semantic validation error

**Server Errors (5xx):**
- `500 Internal Server Error` - Unexpected server error
- `503 Service Unavailable` - Database connection error, external service down

### Exception Handling (Planned)

**Custom Exceptions:**
```python
class OrganizationError(Exception):
    """Base exception for organization-related errors"""
    pass

class InsufficientPermissionsError(OrganizationError):
    """User lacks required role for action"""
    pass

class ResourceNotFoundError(OrganizationError):
    """Resource not found in organization"""
    pass

class OrganizationQuotaExceededError(OrganizationError):
    """Organization exceeded subscription limits"""
    pass
```

**Exception Handlers:**
```python
@app.exception_handler(InsufficientPermissionsError)
async def handle_permission_error(request: Request, exc: InsufficientPermissionsError):
    return JSONResponse(
        status_code=403,
        content={
            "detail": str(exc),
            "error_code": "INSUFFICIENT_PERMISSIONS",
            "status_code": 403,
            "timestamp": datetime.utcnow().isoformat()
        }
    )
```

### Logging

**Log Levels:**
- `DEBUG` - Development debugging (SQL queries, internal state)
- `INFO` - Normal operations (requests, responses)
- `WARNING` - Unexpected but handled (rate limits, validation errors)
- `ERROR` - Errors requiring attention (DB errors, external API failures)
- `CRITICAL` - System failures (startup errors, security breaches)

**Structured Logging (Planned):**
```python
import structlog

logger = structlog.get_logger()

logger.info(
    "customer_created",
    org_id=org_id,
    customer_id=customer.id,
    user_id=current_user.id,
    geocoded=True
)
```

## Caching Strategy

### Geocoding Cache

**Purpose:** Reduce geocoding API costs and improve response times

**Implementation:**
- `geocoding_cache` table with normalized address as key
- Shared cache across all organizations
- Address normalization: lowercase, strip whitespace, standardize abbreviations
- Cache hit before making external API call
- TTL: 90 days (update `last_used_at` on hit)

**Cache Eviction:**
- LRU (Least Recently Used) based on `last_used_at`
- Automatic cleanup job (daily) removes entries > 90 days old
- Manual cache clear for specific addresses (admin only)

**Example:**
```python
async def geocode_with_cache(address: str, provider: GeocodingProvider) -> GeocodingResult:
    # Normalize address for cache key
    normalized = normalize_address(address)

    # Check cache
    cached = await db.execute(
        select(GeocodingCache).where(GeocodingCache.address_normalized == normalized)
    )
    if cached:
        await db.execute(
            update(GeocodingCache)
            .where(GeocodingCache.id == cached.id)
            .values(last_used_at=datetime.utcnow())
        )
        return GeocodingResult(lat=cached.latitude, lon=cached.longitude)

    # Cache miss - call provider
    result = await provider.geocode(address)

    # Store in cache
    await db.execute(
        insert(GeocodingCache).values(
            address_normalized=normalized,
            provider=provider.get_provider_name(),
            latitude=result.lat,
            longitude=result.lon,
            last_used_at=datetime.utcnow()
        )
    )

    return result
```

### Application-Level Caching (Planned)

**Redis Integration:**
- Cache frequently accessed data (organization settings, service plans)
- Session storage for rate limiting
- Pub/sub for real-time updates

**Cache Keys:**
- `org:{org_id}:settings` - Organization settings (TTL: 5 minutes)
- `user:{user_id}:profile` - User profile (TTL: 10 minutes)
- `route:{route_id}` - Computed routes (TTL: 1 hour)

**Cache Invalidation:**
- Write-through: Update cache on data modification
- TTL-based: Automatic expiration
- Manual: API endpoint to clear specific keys

## Configuration

**File:** `app/config.py`

**Environment Variables:**

**Required:**
- `DATABASE_URL` - PostgreSQL connection string
  - Example: `postgresql+asyncpg://user:pass@localhost:5432/routeoptimizer`
- `SECRET_KEY` - JWT signing secret (generate with `openssl rand -hex 32`)
- `API_VERSION` - API version prefix (default: "v1")

**Authentication:**
- `JWT_SECRET_KEY` - JWT signing key (can reuse SECRET_KEY)
- `JWT_ALGORITHM` - JWT algorithm (default: "HS256")
- `JWT_EXPIRATION_HOURS` - Token expiration (default: 24)
- `BCRYPT_ROUNDS` - Password hashing rounds (default: 12)

**Geocoding:**
- `DEFAULT_GEOCODING_PROVIDER` - openstreetmap|google (default: openstreetmap)
- `GOOGLE_MAPS_API_KEY` - Optional, required for Google Maps provider
- `GEOCODING_CACHE_TTL_DAYS` - Cache TTL (default: 90)
- `NOMINATIM_USER_AGENT` - User agent for OpenStreetMap (default: "RouteOptimizer")

**Optimization:**
- `OPTIMIZATION_TIME_LIMIT_SECONDS` - OR-Tools timeout (default: 120)
- `MAX_CUSTOMERS_PER_ROUTE` - Route size limit (default: 50)

**API & Security:**
- `ALLOWED_ORIGINS` - CORS allowed origins (comma-separated)
  - Example: `http://localhost:3000,https://app.example.com`
- `RATE_LIMIT_PER_MINUTE` - API rate limit (default: 60)
- `ENABLE_RATE_LIMITING` - Enable rate limiting (default: true in production)

**Subscription & Billing (Planned):**
- `STRIPE_SECRET_KEY` - Stripe API secret key
- `STRIPE_PUBLISHABLE_KEY` - Stripe publishable key
- `STRIPE_WEBHOOK_SECRET` - Stripe webhook signing secret

**File Storage (Planned):**
- `DO_SPACES_KEY` - Digital Ocean Spaces access key
- `DO_SPACES_SECRET` - Digital Ocean Spaces secret key
- `DO_SPACES_REGION` - Region (e.g., nyc3)
- `DO_SPACES_BUCKET` - Bucket name

**Logging:**
- `LOG_LEVEL` - DEBUG|INFO|WARNING|ERROR|CRITICAL (default: INFO)
- `LOG_FORMAT` - text|json (default: text)

**Feature Flags (Planned):**
- `ENABLE_AI_RECOMMENDATIONS` - Enable AI features (default: false)
- `ENABLE_ADVANCED_REPORTING` - Enable advanced reports (default: false)
- `ENABLE_SUBDOMAIN_ROUTING` - Enable subdomain-based tenant routing (default: false)

## Frontend Structure

**Main File:** `static/index.html` + `static/js/app.js`

**Key Components:**
- Leaflet.js map with customer/route visualization
- Day selector tabs
- Driver/tech selector (sidebar, needs redesign)
- Optimization controls (mode, day reassignment)
- Customer management (CRUD, CSV import, coordinate validation)
- Driver management (CRUD)

**Map Features:**
- Color-coded routes by driver
- Numbered stop markers
- Polyline route paths
- Click for customer details

**SaaS Updates (Planned):**
- Login/registration pages
- Organization settings dashboard
- User management interface
- Subscription billing page
- Role-based UI (show/hide features based on role)
- Multi-organization switcher (if user belongs to multiple orgs)

---

## See Also - SaaS Foundation Documentation

**Design & Planning:**
- [DESIGN_REVIEW.md](DESIGN_REVIEW.md) - Current design flaws and migration strategy
- [SAAS_ARCHITECTURE.md](SAAS_ARCHITECTURE.md) - Complete multi-tenancy specification
- [SAAS_FOUNDATION_TODO.md](SAAS_FOUNDATION_TODO.md) - Master implementation plan and context

**Database:**
- [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) - Complete schema with all SaaS tables
- [MIGRATION_PLAN.md](MIGRATION_PLAN.md) - Step-by-step migration guide

**Services:**
- [MAP_PROVIDER_STRATEGY.md](MAP_PROVIDER_STRATEGY.md) - Geocoding provider abstraction

**Implementation Status:**
- [ROADMAP.md](ROADMAP.md) - Development phases and timeline
- [PROJECT_STATUS.md](PROJECT_STATUS.md) - Current progress tracking
- [FEATURES.md](FEATURES.md) - Feature tracking with SaaS foundation
- [EXPANSION_PLAN.md](EXPANSION_PLAN.md) - Business model and future features
