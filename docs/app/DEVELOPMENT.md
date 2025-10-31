# Development Guide

**Quick reference for setup, commands, and running Quantum Pool Solutions.**

## Setup

### Initial Installation
```bash
cd /mnt/Projects/quantum-pools
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Database Setup
```bash
# Create PostgreSQL database
sudo -u postgres createdb routeoptimizer
sudo -u postgres createuser routeoptimizer -P

# Run migrations
alembic upgrade head

# Load sample data (optional)
python -m app.scripts.import_customers data/sample_customers.csv
```

### Environment Configuration
```bash
cp .env.example .env
# Edit .env with your settings:
# - DATABASE_URL
# - SECRET_KEY
# - GOOGLE_MAPS_API_KEY (optional)
```

## Running the Application

### Start Development Server
```bash
source venv/bin/activate
./restart_server.sh  # Kills old processes on port 7007, starts new server
```

**Access:**
- Web UI: http://localhost:7007
- API Docs: http://localhost:7007/docs
- ReDoc: http://localhost:7007/redoc

### Manual Start (if restart_server.sh fails)
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 7006
```

## Database Operations

### Migrations
```bash
# Create migration after model changes
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# View history
alembic history

# View current version
alembic current
```

### Direct Database Access
```bash
psql -h localhost -U routeoptimizer -d routeoptimizer
```

## Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=app --cov-report=html

# Specific test suite
pytest tests/unit/
pytest tests/integration/

# Watch mode
pytest-watch
```

## Common Tasks

### Import Customer Data
```bash
python -m app.scripts.import_customers data/customers.csv
```

### Geocode Existing Customers
```bash
python -m app.scripts.geocode_customers
```

### Check Health
```bash
curl http://localhost:7007/health
```

### View Logs
```bash
tail -f logs/app.log
```

## Troubleshooting

### Database Connection Failed
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql
sudo systemctl start postgresql

# Verify DATABASE_URL in .env
cat .env | grep DATABASE_URL
```

### Port Already in Use
```bash
# Kill process on port 7007
lsof -ti:7007 | xargs kill -9

# Or use restart script
./restart_server.sh
```

### Geocoding Not Working
- Free tier: OpenStreetMap Nominatim (1 req/sec limit)
- Production: Set `GOOGLE_MAPS_API_KEY` in .env
- Manual batch job: `python -m app.scripts.geocode_customers`

### Route Optimization Timeout
- Reduce customer count or split by service day
- Adjust time limit in config
- Check Google OR-Tools installation

## Development Workflow

### Git Workflow
```bash
# Feature branch
git checkout -b feature/feature-name

# Commit
git add .
git commit -m "feat: description"

# Push
git push origin feature/feature-name
```

**Commit Types:** feat, fix, docs, refactor, test, chore

### Code Quality Checks
```bash
# Type checking
mypy app/

# Linting
flake8 app/

# Format
black app/
```

## Project Structure
```
quantum-pools/
├── app/
│   ├── api/              # FastAPI routers
│   ├── models/           # SQLAlchemy models
│   ├── schemas/          # Pydantic schemas
│   ├── services/         # Business logic
│   ├── database.py       # DB connection
│   ├── config.py         # Configuration
│   └── main.py           # FastAPI app
├── migrations/           # Alembic migrations
├── tests/
│   ├── unit/
│   └── integration/
├── static/               # Frontend
│   ├── index.html
│   ├── css/
│   └── js/
├── docs/                 # Documentation
├── requirements.txt
└── .env
```

## Environment Variables

**Required:**
```bash
DATABASE_URL=postgresql+asyncpg://user:password@localhost/routeoptimizer
SECRET_KEY=your-secret-key-here
```

**Optional:**
```bash
# Geocoding (defaults to OpenStreetMap)
GOOGLE_MAPS_API_KEY=your-api-key

# Environment
ENVIRONMENT=development  # development|staging|production

# CORS
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:7007

# Logging
LOG_LEVEL=INFO  # DEBUG|INFO|WARNING|ERROR
```

## Performance Tips

- Use connection pooling for database (configured in `database.py`)
- Enable query logging in development: `LOG_LEVEL=DEBUG`
- Monitor slow queries with `pg_stat_statements`
- Cache geocoding results (already implemented)
- Use indexes on frequently queried fields

## Security Checklist

- ✅ Never commit `.env` file (in `.gitignore`)
- ✅ Use parameterized queries (SQLAlchemy ORM)
- ✅ Validate all user input (Pydantic schemas)
- ✅ Hash passwords with bcrypt
- ✅ Use HTTPS in production
- ✅ Set CORS allowed origins
- ✅ Keep dependencies updated

---

**See Also:**
- [ARCHITECTURE.md](ARCHITECTURE.md) - System design and patterns
- [STANDARDS.md](STANDARDS.md) - Code quality rules
- [PROJECT_STATUS.md](PROJECT_STATUS.md) - Current development phase
