# Code Standards & Best Practices

**Enterprise-grade development rules for Quantum Pool Solutions.**

## Core Principles

1. **Production-ready from day one** - No TODOs, no placeholders
2. **One task at a time** - Sequential execution, complete before moving on
3. **Fix issues immediately** - Never defer bugs or problems
4. **Design for scale** - Build for 1,000 users, not just 1
5. **Security by default** - Validate input, parameterize queries, hash passwords

## Code Quality Standards

### No Placeholders Policy

**❌ NEVER:**
- TODO comments
- FIXME markers
- "We'll implement this later"
- Dummy data or stub functions
- Commented-out code "for reference"

**✅ ALWAYS:**
- Complete implementations
- Full error handling
- Input validation
- Type hints on all functions
- Docstrings for complex logic

### Python Standards

**Type Hints:**
```python
# ✅ CORRECT
async def get_customer(customer_id: str, db: AsyncSession) -> Customer:
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    return result.scalar_one_or_none()

# ❌ WRONG - No type hints
async def get_customer(customer_id, db):
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    return result.scalar_one_or_none()
```

**Error Handling:**
```python
# ✅ CORRECT - Specific exceptions
try:
    result = await some_operation()
except ValueError as e:
    logger.error(f"Invalid value: {e}")
    raise HTTPException(400, "Invalid input")
except DatabaseError as e:
    logger.error(f"Database error: {e}")
    raise HTTPException(500, "Database operation failed")

# ❌ WRONG - Bare except
try:
    result = await some_operation()
except:
    pass
```

**Async Patterns:**
```python
# ✅ CORRECT
async def get_customers(db: AsyncSession, org_id: str) -> List[Customer]:
    result = await db.execute(
        select(Customer).where(Customer.organization_id == org_id)
    )
    return result.scalars().all()

# ❌ WRONG - Blocking call in async function
async def get_customers(db: AsyncSession, org_id: str):
    return db.query(Customer).filter_by(organization_id=org_id).all()
```

### JavaScript Standards

**Function Documentation:**
```javascript
// ✅ CORRECT
/**
 * Load and display customers on the map
 * @param {string} serviceDay - Filter by day (e.g., 'monday')
 * @param {boolean} showInactive - Include inactive customers
 */
async function loadCustomers(serviceDay = null, showInactive = false) {
    // Implementation
}

// ❌ WRONG - No documentation
async function loadCustomers(serviceDay, showInactive) {
    // Implementation
}
```

**Error Handling:**
```javascript
// ✅ CORRECT
try {
    const response = await fetch(`${API_BASE}/customers`);
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    const data = await response.json();
    return data;
} catch (error) {
    console.error('Failed to load customers:', error);
    showError('Unable to load customers. Please try again.');
    return [];
}

// ❌ WRONG - No error handling
const response = await fetch(`${API_BASE}/customers`);
const data = await response.json();
return data;
```

**Global Variables:**
```javascript
// ✅ ACCEPTABLE - Necessary globals
let map = null;  // Leaflet map instance
let customerMarkers = {};  // Track markers for cleanup
const API_BASE = '/api/v1';  // API endpoint

// ❌ AVOID - Unnecessary globals
let tempData = [];
let counter = 0;
```

## Security Standards

### Input Validation

**Always validate user input:**
```python
# ✅ CORRECT - Pydantic schema validation
from pydantic import BaseModel, Field, validator

class CustomerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    email: str = Field(..., regex=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    service_day: str = Field(..., pattern='^(monday|tuesday|wednesday|thursday|friday|saturday|sunday)$')

    @validator('name')
    def name_must_not_be_empty(cls, v):
        if not v.strip():
            raise ValueError('Name cannot be empty')
        return v.strip()
```

### Database Security

**Always use parameterized queries:**
```python
# ✅ CORRECT - SQLAlchemy ORM (parameterized)
result = await db.execute(
    select(Customer).where(Customer.email == email)
)

# ✅ CORRECT - Raw SQL with parameters
result = await db.execute(
    text("SELECT * FROM customers WHERE email = :email"),
    {"email": email}
)

# ❌ WRONG - SQL injection vulnerable
query = f"SELECT * FROM customers WHERE email = '{email}'"
result = await db.execute(text(query))
```

### Authentication Security

**Password hashing:**
```python
# ✅ CORRECT - bcrypt with salt
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

# ❌ WRONG - Storing plain text
user.password = password  # NEVER DO THIS
```

**JWT handling:**
```python
# ✅ CORRECT - Expiration, secret from env
from jose import jwt
from datetime import datetime, timedelta

def create_token(user_id: str, org_id: str) -> str:
    expires = datetime.utcnow() + timedelta(hours=24)
    payload = {
        "user_id": user_id,
        "org_id": org_id,
        "exp": expires
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

# ❌ WRONG - No expiration, hardcoded secret
token = jwt.encode({"user_id": user_id}, "my-secret", algorithm="HS256")
```

## Multi-Tenancy Security

**CRITICAL: Always filter by organization_id:**

```python
# ✅ CORRECT
async def get_customers(org_id: str, db: AsyncSession):
    result = await db.execute(
        select(Customer).where(Customer.organization_id == org_id)
    )
    return result.scalars().all()

# ❌ WRONG - No organization filter (data leak!)
async def get_customers(db: AsyncSession):
    result = await db.execute(select(Customer))
    return result.scalars().all()
```

**Middleware pattern for automatic scoping:**
```python
async def require_org_context(request: Request) -> str:
    """Extract org_id from JWT, validate access"""
    token = request.headers.get("Authorization")
    if not token:
        raise HTTPException(401, "Not authenticated")

    payload = decode_jwt(token)
    org_id = payload.get("org_id")

    if not org_id:
        raise HTTPException(403, "No organization context")

    return org_id
```

## Performance Standards

### Database Optimization

**Use indexes:**
```sql
-- ✅ CORRECT - Index frequently queried columns
CREATE INDEX idx_customers_org_service_day
ON customers(organization_id, service_day);

CREATE INDEX idx_customers_location
ON customers(latitude, longitude);
```

**Avoid N+1 queries:**
```python
# ✅ CORRECT - Eager loading with joinedload
result = await db.execute(
    select(Route)
    .options(joinedload(Route.stops).joinedload(RouteStop.customer))
    .where(Route.organization_id == org_id)
)

# ❌ WRONG - N+1 problem (loads stops in loop)
routes = await db.execute(select(Route).where(Route.organization_id == org_id))
for route in routes:
    stops = await db.execute(select(RouteStop).where(RouteStop.route_id == route.id))
```

**Use pagination:**
```python
# ✅ CORRECT
@router.get("/customers")
async def get_customers(
    page: int = 1,
    per_page: int = 50,
    db: AsyncSession = Depends(get_db)
):
    offset = (page - 1) * per_page
    result = await db.execute(
        select(Customer)
        .limit(per_page)
        .offset(offset)
    )
    return result.scalars().all()
```

### Frontend Performance

**Lazy load data:**
```javascript
// ✅ CORRECT - Load on demand
async function loadCustomerDetails(customerId) {
    const response = await fetch(`${API_BASE}/customers/${customerId}`);
    return response.json();
}

// ❌ WRONG - Load everything upfront
async function loadAllCustomers() {
    const response = await fetch(`${API_BASE}/customers?include=all_details`);
    return response.json();  // Could be megabytes
}
```

**Debounce expensive operations:**
```javascript
// ✅ CORRECT
let searchTimeout;
function handleSearchInput(event) {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        performSearch(event.target.value);
    }, 300);  // Wait 300ms after typing stops
}

// ❌ WRONG - Search on every keystroke
function handleSearchInput(event) {
    performSearch(event.target.value);  // Fires constantly
}
```

## Testing Standards

### Unit Tests

**Pattern: Arrange → Act → Assert**
```python
@pytest.mark.asyncio
async def test_create_customer(db_session):
    # Arrange
    org_id = uuid.uuid4()
    data = CustomerCreate(
        name="Test Customer",
        address="123 Main St",
        service_day="monday"
    )

    # Act
    service = CustomerService(db_session)
    customer = await service.create_customer(org_id, data)

    # Assert
    assert customer.name == "Test Customer"
    assert customer.organization_id == org_id
    assert customer.is_active is True
```

### Integration Tests

**Test with real database:**
```python
@pytest.mark.asyncio
async def test_customer_api_endpoint(client, auth_token):
    # Create customer via API
    response = await client.post(
        "/api/v1/customers",
        json={"name": "Test", "address": "123 Main St"},
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 201

    # Verify in database
    customer_id = response.json()["id"]
    customer = await db.get(Customer, customer_id)
    assert customer is not None
```

## Accessibility Standards

### WCAG 2.1 AA Compliance

**Keyboard Navigation:**
```html
<!-- ✅ CORRECT - Keyboard accessible -->
<button onclick="openModal()" tabindex="0">Open</button>
<div role="dialog" aria-labelledby="modal-title" aria-modal="true">
  <h2 id="modal-title">Modal Title</h2>
</div>

<!-- ❌ WRONG - Not keyboard accessible -->
<div onclick="openModal()">Open</div>
```

**Color Contrast:**
- Text: 4.5:1 minimum contrast ratio
- Large text (18pt+): 3:1 minimum
- Use tools like WebAIM contrast checker

**Screen Reader Support:**
```html
<!-- ✅ CORRECT - Proper labels -->
<label for="customer-name">Customer Name:</label>
<input id="customer-name" type="text" required aria-required="true">

<!-- ❌ WRONG - No label -->
<input type="text" placeholder="Customer Name">
```

## Git Standards

### Commit Messages

**Format:**
```
<type>: <short description>

<optional longer description>

<optional breaking changes>
```

**Types:**
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation only
- `refactor:` Code restructuring
- `test:` Adding tests
- `chore:` Maintenance

**Examples:**
```bash
feat: add bulk customer import via CSV

Implements CSV parsing with validation, geocoding, and error reporting.
Users can now import up to 1000 customers at once.

fix: prevent duplicate route optimization requests

Added request debouncing and loading state to prevent
users from triggering multiple simultaneous optimizations.

refactor: extract customer module from app.js

Moved 296 lines of customer management code to dedicated module
for better organization and maintainability.
```

### Branch Naming

```bash
feature/customer-bulk-import
fix/route-optimization-timeout
docs/api-documentation
refactor/extract-drivers-module
```

## Code Review Checklist

Before marking a task complete, verify:

- [ ] No TODOs, FIXMEs, or placeholders
- [ ] Complete error handling (try/except with specific exceptions)
- [ ] Input validation (Pydantic schemas)
- [ ] Type hints on all Python functions
- [ ] JSDoc comments on JavaScript functions
- [ ] Security: no SQL injection, no hardcoded secrets
- [ ] Multi-tenancy: organization_id filter on all queries
- [ ] Tests written and passing
- [ ] No console.log() or print() debugging statements
- [ ] Follows project patterns (service layer, dependency injection)
- [ ] Performance: no N+1 queries, proper indexing
- [ ] Accessibility: keyboard navigation, ARIA labels
- [ ] Works in all major browsers

---

**See Also:**
- [ARCHITECTURE.md](ARCHITECTURE.md) - System design patterns
- [DEVELOPMENT.md](DEVELOPMENT.md) - Setup and workflow
