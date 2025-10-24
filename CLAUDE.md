# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**RouteOptimizer** is a web application for optimizing pool service routes with support for multiple drivers, service constraints, and schedule generation. While built for pool service businesses, it's designed to work for any routing/scheduling use case.

**Core Philosophy**: Build enterprise-grade, production-ready routing software that's flexible enough to scale beyond pool services.

**Tech Stack:**
- **Language:** Python 3.11+
- **Framework:** FastAPI (async REST API)
- **Database:** PostgreSQL (production) / SQLite (development)
- **Key Libraries:**
  - SQLAlchemy 2.0 (async ORM)
  - Alembic (database migrations)
  - Google OR-Tools (route optimization)
  - Geopy (geocoding addresses to GPS coordinates)
  - Pydantic (data validation)
  - Leaflet.js (map visualization)
  - ReportLab/WeasyPrint (PDF generation)

## Development Commands

### Setup & Installation
```bash
# Initial project setup (one-time)
cd /mnt/Projects/RouteOptimizer
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Initialize database
alembic upgrade head

# Create .env file from template
cp .env.example .env
# Then edit .env with your database credentials
```

### Running the Development Server
```bash
# Start FastAPI development server with auto-reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 7006

# Access the application:
# - Web UI: http://localhost:7006
# - API Docs (Swagger): http://localhost:7006/docs
# - Alternative API Docs (ReDoc): http://localhost:7006/redoc
```

### Database Migrations
```bash
# Create a new migration (auto-generate from model changes)
alembic revision --autogenerate -m "description of changes"

# Apply all pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# View migration history
alembic history

# View current database version
alembic current
```

### Testing
```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=app --cov-report=html

# Run specific test suite
pytest tests/unit/           # Unit tests only
pytest tests/integration/    # Integration tests only

# Run specific test file
pytest tests/unit/test_optimization.py -v

# Run and watch for changes
pytest-watch
```

### Maintenance
```bash
# Check database connection
psql -h localhost -U routeoptimizer -d routeoptimizer

# View application logs (if running with supervisor/systemd)
tail -f logs/app.log

# Run health check
curl http://localhost:8000/health

# Import sample customer data
python -m app.scripts.import_customers data/sample_customers.csv
```

## Workflow Commands for AI-Assisted Development

When working with Claude Code, the user can use special shorthand commands for common workflows. These commands streamline development without interrupting flow.

**See [docs/COMMANDS.md](docs/COMMANDS.md) for complete reference.**

### Quick Reference

**Commit & Progress:**
- `commit` or `commit-go` - Commit changes, **push to GitHub**, update docs, continue working
- `commit-pause` - Commit changes, **push to GitHub**, update docs, pause for review
- `commit-local` - Commit WITHOUT pushing (rare, stays local only)
- `commit-status` - Show what would be committed (dry run)

**Feature Ideas:**
- `backlog: [idea]` - Add feature idea without interrupting current work
- `backlog-review` - Show recent backlog items
- `backlog-priority` - Sort backlog by priority

**Task Management:**
- `todo` or `tasks` - Show current task list with status
- `next` - Get recommendation for what to work on next
- `done [task]` - Mark specific task complete

**Navigation & Context:**
- `where` - Quick status (phase, progress, current task)
- `status` - Show PROJECT_STATUS.md summary
- `roadmap` - Show LAUNCH_PLAN.md timeline (if applicable)
- `list` or `help` - Show all commands

**Development:**
- `test` - Run tests for current feature
- `review` - Review changes before committing
- `docs` - Update documentation for current feature
- `swagger` - Show API testing instructions (if applicable)
- `files` - Show key files for current work
- `api` - Show relevant API endpoints (if applicable)
- `db` - Show database schema for current model

### Command Behavior for Claude

When the user uses these commands:
1. Execute immediately without asking for confirmation
2. Be concise in output (user wants quick results)
3. Update TodoWrite and SESSION_LOG.md as appropriate
4. For `commit` commands, create detailed git messages following project conventions

**Example:**
```
User: commit
→ Claude commits with message, pushes to GitHub, updates SESSION_LOG.md, continues

User: backlog: Add [feature idea]
→ Claude adds to BACKLOG.md under appropriate category, continues current task

User: where
→ Claude shows: "Phase [X] - [Name], [X]% complete, working on [current task]"
```

**Note on Auto-Push:**
By default, `commit` and `commit-pause` push to GitHub immediately for cloud backup. This protects against data loss (your primary concern). Use `commit-local` for rare cases when you want local-only commits.

## Enterprise-Grade Development Standards

**This application will be used by thousands of users - build production-ready code from the start.**

### 1. Understand Intent Before Generating Code
**ALWAYS confirm understanding before writing code**
- Ask clarifying questions if requirements are ambiguous
- Present a clear plan with TodoWrite for complex tasks
- Wait for confirmation before proceeding
- Use Read/Grep/Glob to verify what exists before building

### 2. Work One Item at a Time (Sequential Execution)
**Use TodoWrite to track and complete tasks sequentially**
- Break complex work into discrete tasks in TodoWrite
- Mark task as `in_progress` before starting
- Work through issues until fully resolved
- Mark `completed` only when production-ready
- Never jump between multiple incomplete tasks

### 3. Enterprise-Grade Code (No Placeholders)
**Build production-ready code from the start - no shortcuts**
- ❌ No "TODO" or "FIXME" comments
- ❌ No "we'll implement this later" shortcuts
- ❌ No dummy data or stub functions
- ❌ No placeholder implementations
- ✅ Complete error handling and validation
- ✅ Proper async/await usage
- ✅ Type hints on all functions
- ✅ Security best practices

### 4. Use Appropriate Tools (Claude Code First)
**Prefer Claude Code specialized tools over bash commands**

**For file operations:**
- ✅ **Read** - View file contents (NOT cat)
- ✅ **Write** - Create new files (NOT cat with heredoc)
- ✅ **Edit** - Modify existing files (NOT sed/awk)
- ✅ **Grep** - Search code (NOT grep command)
- ✅ **Glob** - Find files by pattern (NOT find)

**Use Bash only for:**
- Git operations
- Package management (pip, npm)
- Running tests
- Starting services
- Database operations (migrations, psql)
- System commands that require shell

**Why:** Claude Code tools are safer, more precise, and have better error handling.

### 5. Fix Issues Immediately (Zero Technical Debt)
**Never dismiss issues or defer fixes**
- If an issue is identified, stop and fix it now
- Never say "not blocking" or "fix later"
- Small issues cost hours of debugging later
- Document the fix in SESSION_LOG.md
- Commit after fix before moving forward

### 6. Professional Architecture & Patterns
**Follow enterprise best practices consistently**
- UUID primary keys (not integers)
- Proper relationships and foreign keys
- Async/await patterns (FastAPI, SQLAlchemy)
- Service layer pattern (API → Service → Model)
- Dependency injection for sessions
- Proper error handling and HTTP status codes
- Input validation with Pydantic schemas
- Security: never commit secrets, validate input, parameterized queries

### 7. Multi-Browser & Production Compatibility
**Test and document compatibility across environments**
- Consider all major browsers (Chrome, Firefox, Safari)
- Document niche browser issues in BROWSER_COMPATIBILITY.md
- Don't dismiss compatibility problems
- Production app must work everywhere

### 8. Document Decisions Automatically
**Use SESSION_LOG.md for decision tracking**
- `commit` and `commit-pause` update SESSION_LOG.md automatically
- Document: decisions made, alternatives considered, issues fixed
- Keep PROJECT_STATUS.md current with phase progress
- Use `backlog: [idea]` to capture future work
- Everything in git-tracked files (no external gists)

### 9. Verify Before Building
**Always inspect existing code before modifying**
- Use **Read** to check file contents first
- Use **Grep** to search for existing implementations
- Use **Glob** to find related files
- Verify database models match expectations
- Test endpoints after creating them
- Don't assume structure - inspect it

### 10. Complete Testing & Validation
**Every implementation must be tested**
- Provide test commands (pytest, curl, Swagger UI)
- Test happy path AND error cases
- Verify edge cases are handled
- Check database state after operations
- Run tests before marking task complete

### Quality Checklist (Self-Check Before Completing Task)

Every implementation must have:
- [ ] No TODOs, FIXMEs, or placeholders
- [ ] Complete error handling (try/except with specific exceptions)
- [ ] Input validation (Pydantic schemas)
- [ ] Proper async/await usage
- [ ] Type hints on all functions
- [ ] Security considerations addressed
- [ ] Follows project patterns (service layer, dependency injection)
- [ ] Will scale to thousands of users
- [ ] Tested and verified working
- [ ] Documented in SESSION_LOG.md (if significant)

### Communication Style

**✅ DO SAY:**
- "Let me check what exists first" (then uses Read)
- "I'll create a TodoWrite plan for this"
- "Found an issue, stopping to fix it now"
- "Task completed, moving to next"
- "Does this plan match your vision?"

**❌ DON'T SAY:**
- "Would you like to review this code?"
- "We can fix this later"
- "This is just a placeholder"
- "Not blocking, we can skip it"
- "We'll implement that in Phase 2"

## Architecture Overview

### Monolithic Web Application with Service Layer Pattern

**Architecture:**
- FastAPI backend serving both REST API and static frontend
- PostgreSQL database for persistent storage
- Service layer for business logic separation
- Background task queue for route optimization (async processing)

**Key Components:**
- **API Layer**: FastAPI routers handling HTTP requests/responses
- **Service Layer**: Business logic (optimization, geocoding, scheduling)
- **Data Layer**: SQLAlchemy models and database operations
- **Optimization Engine**: Google OR-Tools VRP solver
- **Frontend**: Static HTML/JS with Leaflet.js for map visualization

### Project Structure
```
RouteOptimizer/
├── app/                    # Main application code
│   ├── api/               # FastAPI routers/endpoints
│   │   ├── customers.py   # Customer CRUD endpoints
│   │   ├── drivers.py     # Driver management endpoints
│   │   ├── routes.py      # Route optimization endpoints
│   │   └── imports.py     # CSV import endpoints
│   ├── models/            # SQLAlchemy database models
│   │   ├── customer.py
│   │   ├── driver.py
│   │   ├── route.py
│   │   └── route_stop.py
│   ├── schemas/           # Pydantic validation schemas
│   │   ├── customer.py
│   │   ├── driver.py
│   │   └── route.py
│   ├── services/          # Business logic layer
│   │   ├── optimization.py   # Route optimization service
│   │   ├── geocoding.py      # Address geocoding service
│   │   └── pdf_export.py     # PDF generation service
│   ├── database.py        # Database connection and session
│   ├── config.py          # Configuration management
│   └── main.py            # FastAPI application entry point
├── migrations/            # Alembic database migrations
├── tests/                 # Test suite
│   ├── unit/             # Unit tests
│   ├── integration/      # Integration tests
│   └── conftest.py       # Pytest configuration
├── static/               # Frontend static files
│   ├── index.html        # Main web interface
│   ├── css/
│   └── js/
├── docs/                 # Project documentation
├── data/                 # Sample/import data files
├── alembic.ini           # Alembic configuration
├── requirements.txt      # Python dependencies
├── .env.example          # Environment variable template
├── .gitignore
└── CLAUDE.md             # This file
```

### Database Pattern

**Single PostgreSQL Database:**
- All data in one database: `routeoptimizer`
- Tables: customers, drivers, routes, route_stops
- UUID primary keys for all tables
- Proper foreign key relationships and cascading deletes
- Indexes on frequently queried fields (service_day, customer addresses)

**Database Schema:**
- **customers**: Customer data with address, service type, difficulty, time windows
- **drivers**: Driver configuration with start/end locations and working hours
- **routes**: Generated route assignments for each driver/day combination
- **route_stops**: Ordered sequence of customer stops within each route

**Session Management:**
Always use dependency injection for database sessions in API endpoints.

## Database Session Management

**FastAPI Dependency Injection Pattern:**
```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db

@router.get("/customers")
async def get_customers(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Customer))
    return result.scalars().all()

@router.post("/customers")
async def create_customer(
    customer: CustomerCreate,
    db: AsyncSession = Depends(get_db)
):
    db_customer = Customer(**customer.dict())
    db.add(db_customer)
    await db.commit()
    await db.refresh(db_customer)
    return db_customer
```

**CRITICAL**:
- Always use `Depends(get_db)` for database access in API endpoints
- Never create sessions manually in endpoint functions
- The session is automatically committed/rolled back by FastAPI
- Use `await` for all database operations (async SQLAlchemy 2.0)

## API Development Patterns

### Creating New Endpoints

**1. Define Pydantic Schema** (`app/schemas/`):
```python
# app/schemas/customer.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import time

class CustomerBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    address: str = Field(..., min_length=1)
    service_type: str = Field(..., pattern="^(residential|commercial)$")
    difficulty: int = Field(1, ge=1, le=5)
    service_day: str
    time_window_start: Optional[time] = None
    time_window_end: Optional[time] = None

class CustomerCreate(CustomerBase):
    pass

class CustomerResponse(CustomerBase):
    id: str
    latitude: Optional[float]
    longitude: Optional[float]
    created_at: datetime

    class Config:
        from_attributes = True
```

**2. Create Database Model** (`app/models/`):
```python
# app/models/customer.py
from sqlalchemy import Column, String, Float, Integer, Time, DateTime
from sqlalchemy.dialects.postgresql import UUID
import uuid
from app.database import Base

class Customer(Base):
    __tablename__ = "customers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    address = Column(String(500), nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    service_type = Column(String(20), nullable=False)
    difficulty = Column(Integer, default=1)
    service_day = Column(String(20), nullable=False)
    time_window_start = Column(Time, nullable=True)
    time_window_end = Column(Time, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
```

**3. Create Service Layer** (`app/services/`):
```python
# app/services/customer_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.customer import Customer
from app.schemas.customer import CustomerCreate

class CustomerService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_customer(self, data: CustomerCreate) -> Customer:
        customer = Customer(**data.dict())
        self.db.add(customer)
        await self.db.commit()
        await self.db.refresh(customer)
        return customer
```

**4. Add API Endpoint** (`app/api/`):
```python
# app/api/customers.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.customer import CustomerCreate, CustomerResponse
from app.services.customer_service import CustomerService

router = APIRouter(prefix="/api/customers", tags=["customers"])

@router.post("/", response_model=CustomerResponse, status_code=201)
async def create_customer(
    customer: CustomerCreate,
    db: AsyncSession = Depends(get_db)
):
    service = CustomerService(db)
    return await service.create_customer(customer)
```

## Testing Guidelines

### Test Structure
```
tests/
├── unit/           # Fast, isolated tests
├── integration/    # Tests with database/external services
└── e2e/           # Full user flow tests
```

### Writing Tests

**Unit Test Example:**
```python
# tests/unit/test_[feature].py
import pytest

def test_[function_name]():
    """Test description"""
    # Arrange
    [setup]

    # Act
    result = [function_call]

    # Assert
    assert result == [expected]
```

**Integration Test Example:**
```python
# tests/integration/test_[feature].py
import pytest

@pytest.mark.asyncio
async def test_[integration]():
    """Test with real dependencies"""
    # Your integration test
    pass
```

### Test Coverage
- Aim for [X]% overall coverage
- Critical paths: [X]% coverage
- Run coverage: `[your coverage command]`

## Common Development Patterns

### [Pattern 1 Name]
**When to use:** [Description]

**Example:**
```python
# Your code example
```

### [Pattern 2 Name]
**When to use:** [Description]

**Example:**
```python
# Your code example
```

## Error Handling

**Standard error response:**
```python
# Your error handling pattern
```

**Common exceptions:**
- [ExceptionType]: [When it's raised]
- [ExceptionType]: [When it's raised]

## Security Considerations

- [Security practice 1]
- [Security practice 2]
- [Security practice 3]

**Example:**
- Never commit secrets to git
- Use environment variables for sensitive data
- Validate all user input
- Use parameterized queries (prevent SQL injection)

## Environment Variables

**Required:**
```bash
DATABASE_URL=postgresql+asyncpg://user:password@localhost/routeoptimizer
SECRET_KEY=your-secret-key-for-session-encryption
```

**Optional:**
```bash
# Geocoding service (defaults to OpenStreetMap/Nominatim - free)
GOOGLE_MAPS_API_KEY=your-google-maps-api-key

# Environment
ENVIRONMENT=development  # development, staging, production

# CORS settings for frontend
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000

# Logging
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
```

## Common Issues & Solutions

### Issue 1: Database Connection Failed
**Symptoms:** `sqlalchemy.exc.OperationalError: could not connect to server`

**Solution:**
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Start PostgreSQL if stopped
sudo systemctl start postgresql

# Verify DATABASE_URL in .env file is correct
cat .env | grep DATABASE_URL
```

### Issue 2: Geocoding Not Working
**Symptoms:** Customer addresses have null latitude/longitude

**Solution:**
```bash
# If using free OpenStreetMap Nominatim, respect rate limits (1 req/sec)
# For production, set GOOGLE_MAPS_API_KEY in .env
# Or run manual geocoding batch job:
python -m app.scripts.geocode_customers
```

### Issue 3: Route Optimization Takes Too Long
**Symptoms:** Optimization endpoint times out

**Solution:**
- Reduce number of customers or split by service day
- Adjust optimization time limit in config
- Consider upgrading OR-Tools or using background tasks

## Git Workflow

**Branch naming:**
- `feature/[feature-name]` - New features
- `fix/[bug-name]` - Bug fixes
- `docs/[doc-change]` - Documentation updates

**Commit message format:**
```
[type]: [short description]

[Longer description if needed]

[Breaking changes or notes]

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

**Types:** feat, fix, docs, refactor, test, chore

## Additional Resources

### Documentation
- **Project Status**: [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md)
- **Feature Backlog**: [docs/BACKLOG.md](docs/BACKLOG.md)
- **Session Log**: [docs/SESSION_LOG.md](docs/SESSION_LOG.md)
- **Commands**: [docs/COMMANDS.md](docs/COMMANDS.md)

### External Documentation
- **FastAPI**: https://fastapi.tiangolo.com/
- **SQLAlchemy**: https://docs.sqlalchemy.org/en/20/
- **Google OR-Tools**: https://developers.google.com/optimization/routing
- **Alembic**: https://alembic.sqlalchemy.org/
- **Leaflet.js**: https://leafletjs.com/

---

## Customization Checklist

When setting up a new project with this template:

- [ ] Replace all `[PLACEHOLDERS]` with your project details
- [ ] Update tech stack and versions
- [ ] Customize development commands
- [ ] Add your architecture patterns
- [ ] Document your testing approach
- [ ] Add project-specific error handling
- [ ] List all environment variables
- [ ] Document common issues you've encountered
- [ ] Update file structure to match your project
- [ ] Add any framework-specific patterns

---

**Last Updated:** October 23, 2025
**Project Version:** 0.1.0 (Initial Development)
