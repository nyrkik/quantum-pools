# Architecture Reference

**Complete system design for Quantum Pool Solutions SaaS platform.**

## Market Position

### Our Differentiation

Quantum Pool Solutions is positioned as the **AI-powered pool service operating system** - not just another scheduling tool. While competitors like Skimmer, ServiceTitan, and Pool Brain focus on digitizing existing workflows, we're transforming them with automation and intelligence.

**Key Differentiators:**
- **AI-powered inspection processing** - Automated data extraction from inspection reports
- **Predictive maintenance** - ML models predict issues before they occur
- **Intelligent routing** - Weather-aware, traffic-optimized route planning
- **Computer vision** - Analyze pool photos for condition assessment
- **Business intelligence** - True analytics, not just reporting

### Competitive Landscape

**Market Leaders:**
- **Skimmer** - Market leader, strong route optimization, manual data entry
- **ServiceTitan** - Enterprise-grade but generic field service (not pool-specific)
- **Pool Brain** - Excellent custom workflows, limited AI/automation
- **Pool Office Manager** - Seasonal focus, basic chemistry calculators

**Market Gap We Fill:**
- Competitors digitize paper → We automate intelligence
- They're reactive → We're predictive
- They track data → We generate insights
- Manual chemical calculations → AI-powered recommendations

**Target Market:** Small to mid-market pool service companies (5-50 technicians) who want competitive advantage through technology, not just digital forms.

---

## Tech Stack

- **Backend:** FastAPI (async), Python 3.11+
- **Database:** PostgreSQL with async SQLAlchemy 2.0
- **Authentication:** JWT with bcrypt password hashing
- **Authorization:** Role-based access control (RBAC)
- **Optimization:** Google OR-Tools VRP solver
- **Geocoding:** Provider abstraction (OpenStreetMap/Google Maps)
- **Frontend:** Vanilla JavaScript + Leaflet.js maps
- **PDF Export:** ReportLab
- **Payments:** Stripe (planned)
- **File Storage:** Digital Ocean Spaces (planned)

## Multi-Tenancy Architecture

**Pattern:** Organization-based with database-level isolation

### Core Concepts

**Organization = Tenant**
- Each organization is a separate customer account
- All tenant data includes `organization_id` foreign key
- Data access automatically scoped to current organization
- Complete logical isolation within shared database

**Subdomain Routing (Planned):**
```
brians.poolscoutpro.com → organization: "brians"
acme.poolscoutpro.com → organization: "acme"
```

**Current:** Single domain with organization context in JWT

### Data Isolation

**Critical Rule:** NEVER query without organization filter

```python
# ❌ WRONG - No organization filter
SELECT * FROM customers;

# ✅ CORRECT - Always filter by organization_id
SELECT * FROM customers WHERE organization_id = '{current_org_id}';
```

**SQLAlchemy Pattern:**
```python
# Middleware extracts org_id from JWT
async def get_organization_context(request: Request) -> str:
    token = request.headers.get("Authorization")
    payload = decode_jwt(token)
    return payload["org_id"]

# Service layer auto-scopes queries
class CustomerService:
    async def get_customers(self, org_id: str):
        return await db.execute(
            select(Customer).where(Customer.organization_id == org_id)
        )
```

**Table Categories:**

**Global (No organization_id):**
- `service_plans` - Shared subscription tiers
- `alembic_version` - Migration tracking

**Tenant-Specific (Has organization_id):**
- `organizations`, `users`, `organization_users`
- `customers`, `drivers`, `routes`, `route_stops`
- `customer_service_agreements`
- `water_features`, `visit_features`
- `geocoding_requests`, `geocoding_cache`

## Authentication & Authorization

### Authentication Flow

**JWT-Based:**
```
1. POST /api/v1/auth/login (email, password)
2. Server validates credentials (bcrypt)
3. Server issues JWT with payload:
   {
     "user_id": "uuid",
     "email": "user@example.com",
     "org_id": "uuid",
     "role": "admin",
     "exp": 1698451200
   }
4. Client includes token in Authorization header
5. Middleware validates token, extracts org_id
6. All queries auto-scoped to org_id
```

**Password Security:**
- bcrypt hashing with salt
- Minimum requirements enforced
- Password reset via email (planned)

### Role-Based Access Control (RBAC)

**Roles (Hierarchical):**
1. **owner** - Full access, billing, delete organization
2. **admin** - Manage users, all data operations
3. **manager** - Create/edit routes, customers, drivers
4. **technician** - View routes, mark visits complete
5. **readonly** - View-only access

**Permission Matrix:**

| Action | owner | admin | manager | tech | readonly |
|--------|-------|-------|---------|------|----------|
| Manage billing | ✅ | ❌ | ❌ | ❌ | ❌ |
| Manage users | ✅ | ✅ | ❌ | ❌ | ❌ |
| Delete org | ✅ | ❌ | ❌ | ❌ | ❌ |
| Create/edit routes | ✅ | ✅ | ✅ | ❌ | ❌ |
| Create/edit customers | ✅ | ✅ | ✅ | ❌ | ❌ |
| View routes | ✅ | ✅ | ✅ | ✅ | ✅ |
| Mark visits complete | ✅ | ✅ | ✅ | ✅ | ❌ |

**Implementation Pattern:**
```python
from fastapi import Depends, HTTPException

async def require_role(required_role: str):
    def dependency(current_user: User = Depends(get_current_user)):
        if not has_permission(current_user.role, required_role):
            raise HTTPException(403, "Insufficient permissions")
        return current_user
    return dependency

@router.post("/customers")
async def create_customer(
    data: CustomerCreate,
    user: User = Depends(require_role("manager"))
):
    # Only manager+ can create
    pass
```

## Database Schema

### SaaS Foundation

**organizations** (Tenant boundary)
```sql
id                    UUID PRIMARY KEY
name                  VARCHAR(100) UNIQUE  -- URL-safe slug
display_name          VARCHAR(200)
subscription_tier     VARCHAR(50)  -- starter|professional|enterprise
subscription_status   VARCHAR(50)  -- trial|active|suspended|cancelled
trial_end_date        DATE
geocoding_provider    VARCHAR(50)  -- openstreetmap|google
feature_flags         JSONB
settings              JSONB
is_active             BOOLEAN
created_at            TIMESTAMP
updated_at            TIMESTAMP
```

**users** (Authentication)
```sql
id              UUID PRIMARY KEY
email           VARCHAR(255) UNIQUE
password_hash   VARCHAR(255)
full_name       VARCHAR(200)
is_active       BOOLEAN
last_login_at   TIMESTAMP
created_at      TIMESTAMP
updated_at      TIMESTAMP
```

**organization_users** (Authorization - junction table)
```sql
id                UUID PRIMARY KEY
organization_id   UUID FK → organizations.id
user_id           UUID FK → users.id
role              VARCHAR(50)  -- owner|admin|manager|technician|readonly
is_active         BOOLEAN
created_at        TIMESTAMP
updated_at        TIMESTAMP

UNIQUE(organization_id, user_id)
```

### Core Business Tables

**customers**
```sql
id                    UUID PRIMARY KEY
organization_id       UUID FK → organizations.id
name                  VARCHAR(200)
address               VARCHAR(500)
city                  VARCHAR(100)
state                 VARCHAR(2)
zip_code              VARCHAR(10)
latitude              FLOAT
longitude             FLOAT
service_type          VARCHAR(20)  -- residential|commercial
difficulty            INTEGER DEFAULT 1  -- 1-5 scale
service_day           VARCHAR(20)  -- monday|tuesday|etc
time_window_start     TIME
time_window_end       TIME
is_active             BOOLEAN
created_at            TIMESTAMP
updated_at            TIMESTAMP

INDEX idx_customers_org_id (organization_id)
INDEX idx_customers_service_day (organization_id, service_day)
INDEX idx_customers_location (latitude, longitude)
```

**drivers**
```sql
id                    UUID PRIMARY KEY
organization_id       UUID FK → organizations.id
name                  VARCHAR(200)
color                 VARCHAR(7)  -- Hex color for map display
start_address         VARCHAR(500)
start_latitude        FLOAT
start_longitude       FLOAT
end_address           VARCHAR(500)
end_latitude          FLOAT
end_longitude         FLOAT
work_start_time       TIME
work_end_time         TIME
is_active             BOOLEAN
created_at            TIMESTAMP
updated_at            TIMESTAMP

INDEX idx_drivers_org_id (organization_id)
```

**routes**
```sql
id                UUID PRIMARY KEY
organization_id   UUID FK → organizations.id
driver_id         UUID FK → drivers.id
service_day       VARCHAR(20)
total_distance    FLOAT  -- Miles
total_duration    INTEGER  -- Minutes
is_active         BOOLEAN
created_at        TIMESTAMP
updated_at        TIMESTAMP

INDEX idx_routes_org_id (organization_id)
INDEX idx_routes_driver_day (organization_id, driver_id, service_day)
```

**route_stops**
```sql
id              UUID PRIMARY KEY
route_id        UUID FK → routes.id
customer_id     UUID FK → customers.id
sequence        INTEGER  -- Stop order (1, 2, 3...)
arrival_time    TIME
departure_time  TIME
created_at      TIMESTAMP
updated_at      TIMESTAMP

INDEX idx_route_stops_route (route_id)
UNIQUE(route_id, sequence)
```

### Service Tracking (Planned)

**customer_service_agreements**
```sql
id                UUID PRIMARY KEY
organization_id   UUID FK → organizations.id
customer_id       UUID FK → customers.id
service_plan_id   UUID FK → service_plans.id
start_date        DATE
end_date          DATE
billing_status    VARCHAR(50)
created_at        TIMESTAMP
updated_at        TIMESTAMP
```

**visit_features** (Tracks individual visits)
```sql
id              UUID PRIMARY KEY
customer_id     UUID FK → customers.id
visit_date      DATE
technician_id   UUID FK → drivers.id
status          VARCHAR(50)  -- completed|skipped|issue
notes           TEXT
created_at      TIMESTAMP
```

**water_features** (Chemical tracking)
```sql
id            UUID PRIMARY KEY
visit_id      UUID FK → visit_features.id
ph            FLOAT
chlorine      FLOAT
alkalinity    FLOAT
created_at    TIMESTAMP
```

### Geocoding Tracking

**geocoding_requests**
```sql
id                UUID PRIMARY KEY
organization_id   UUID FK → organizations.id
provider          VARCHAR(50)
request_count     INTEGER
month             DATE  -- First day of month
created_at        TIMESTAMP
```

**geocoding_cache**
```sql
id              UUID PRIMARY KEY
address_hash    VARCHAR(64) UNIQUE  -- SHA256 of normalized address
latitude        FLOAT
longitude       FLOAT
provider        VARCHAR(50)
created_at      TIMESTAMP
```

## Service Layer Pattern

**Architecture: API → Service → Model**

```python
# API Layer (FastAPI Router)
@router.post("/customers")
async def create_customer(
    data: CustomerCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    service = CustomerService(db)
    return await service.create_customer(user.org_id, data)

# Service Layer (Business Logic)
class CustomerService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_customer(self, org_id: str, data: CustomerCreate):
        # Validate data
        # Geocode address
        # Create customer with org_id
        customer = Customer(**data.dict(), organization_id=org_id)
        self.db.add(customer)
        await self.db.commit()
        return customer

# Model Layer (SQLAlchemy)
class Customer(Base):
    __tablename__ = "customers"
    id = Column(UUID, primary_key=True)
    organization_id = Column(UUID, ForeignKey("organizations.id"))
    name = Column(String(200))
    # ... other fields
```

**Benefits:**
- Clear separation of concerns
- Easy to test (mock service layer)
- Reusable business logic
- Consistent error handling

## Route Optimization Engine

**Algorithm:** Google OR-Tools Vehicle Routing Problem (VRP)

**Constraints:**
- Driver work hours (time windows)
- Customer time windows (if specified)
- Service difficulty (affects time at stop)
- Maximum route duration
- Vehicle capacity (future)

**Optimization Goals:**
1. Minimize total distance
2. Minimize total time
3. Balance load across drivers

**Process:**
```python
1. Load customers for service_day
2. Load available drivers
3. Build distance matrix (geocoding cache)
4. Configure OR-Tools VRP model:
   - Time windows
   - Capacity constraints
   - Service durations
5. Solve (configurable time limit)
6. Generate routes with stop sequences
7. Save to database
```

## Geocoding Strategy

**Provider Abstraction:**
```python
class GeocodingService:
    def __init__(self, provider: str):
        self.provider = provider  # openstreetmap | google

    async def geocode(self, address: str) -> Tuple[float, float]:
        # Check cache first
        cached = await self.get_from_cache(address)
        if cached:
            return cached

        # Make API call based on provider
        result = await self._geocode_with_provider(address)

        # Cache result
        await self.cache_result(address, result)

        # Track usage
        await self.increment_usage_count()

        return result
```

**Benefits:**
- Easy to switch providers
- Usage tracking per organization
- Caching reduces API costs
- Rate limiting built-in

## Frontend Architecture

**Pattern:** Modular JavaScript (no framework)

**Structure:**
```
static/js/
├── app.js              # Entry point, initialization
├── modules/
│   ├── navigation.js   # Module routing
│   ├── map.js          # Leaflet map, markers
│   ├── routes.js       # Route optimization UI
│   ├── drivers.js      # Driver management
│   ├── customers.js    # Customer CRUD
│   ├── bulk-edit.js    # Bulk operations
│   └── modals.js       # Modal dialogs
└── utils/
    ├── api.js          # Fetch wrappers
    ├── forms.js        # Form helpers
    └── helpers.js      # Utilities
```

**Load Order:**
1. Utils (no dependencies)
2. Core modules (navigation, map, modals)
3. Feature modules (routes, drivers, customers)
4. Main app.js (depends on all)

**Global State Management:**
```javascript
// Minimal globals
let map = null;
let customerMarkers = {};
let selectedDriverIds = new Set();
let currentRouteResult = null;

// Module functions in global scope
function loadCustomers() { ... }
function displayRoutesOnMap() { ... }
```

## Subscription & Billing (Planned)

**Tiers:**
1. **Starter** ($49/mo) - 1 user, 100 customers, basic features
2. **Professional** ($149/mo) - 5 users, 500 customers, advanced routing
3. **Enterprise** (Custom) - Unlimited, white-label, API access

**Implementation:** Stripe Checkout + Customer Portal

**Feature Flags:**
```json
{
  "ai_recommendations": false,
  "advanced_reporting": false,
  "api_access": false,
  "white_label": false
}
```

## Deployment Architecture (Planned)

**Infrastructure:**
- **Web:** Docker containers on Digital Ocean App Platform
- **Database:** Managed PostgreSQL (DO)
- **Storage:** Digital Ocean Spaces (S3-compatible)
- **CDN:** Cloudflare
- **Email:** SendGrid
- **Monitoring:** Sentry

**Scaling Strategy:**
- Horizontal scaling via container replicas
- Database connection pooling
- Redis for session storage (future)
- Background jobs with Celery (future)

---

## Development Setup

### Quick Start
```bash
cd /mnt/Projects/quantum-pools
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Database setup
createdb routeoptimizer
alembic upgrade head

# Run server
./restart_server.sh  # http://localhost:7008
```

### Common Commands
```bash
# Migrations
alembic revision --autogenerate -m "description"
alembic upgrade head

# Testing
pytest
pytest --cov=app

# Code quality
mypy app/
flake8 app/
black app/
```

## Code Standards

### Core Principles
1. **Production-ready from day one** - No TODOs or placeholders
2. **Industry best practices** - Follow GitHub, Stripe, AWS patterns for auth, rate limits, validation
3. **Complete error handling** - Specific exceptions, never bare `except:`
4. **Type hints required** - All Python functions must have type annotations
5. **Security by default** - Parameterized queries, input validation, bcrypt passwords
6. **Multi-tenancy aware** - Always filter by `organization_id`

### Security Checklist
- ✅ Validate all input (Pydantic schemas)
- ✅ Parameterized queries (SQLAlchemy ORM)
- ✅ Hash passwords (bcrypt via passlib)
- ✅ JWT with expiration
- ✅ HTTPS in production
- ✅ CORS configured
- ✅ Never commit .env

### Git Standards
```
<type>: <description>

Types: feat, fix, docs, refactor, test, chore
Branches: feature/name, fix/name
```
