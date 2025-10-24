# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**[PROJECT_NAME]** is [brief description of what the project does].

**Core Philosophy**: [Your project's guiding principle]

**Tech Stack:**
- **Language:** [Python/JavaScript/etc.] [version]
- **Framework:** [FastAPI/Django/Flask/Express/etc.]
- **Database:** [PostgreSQL/MongoDB/SQLite/etc.]
- **Key Libraries:** [List main dependencies]

## Development Commands

### Setup & Installation
```bash
# Initial project setup (one-time)
[Your setup command]

# Activate virtual environment (if applicable)
source venv/bin/activate

# Install dependencies
[Your install command]

# Initialize database (if applicable)
[Your db init command]
```

### Running the Development Server
```bash
# Start server
[Your dev server command]

# Common variations:
# ./manage.sh dev
# python app.py
# npm run dev
# uvicorn main:app --reload
```

### Database Migrations (if applicable)
```bash
# Create a new migration
[Your migration create command]

# Apply migrations
[Your migration apply command]

# Rollback migration
[Your migration rollback command]

# Example for Alembic:
# alembic revision --autogenerate -m "description"
# alembic upgrade head
# alembic downgrade -1
```

### Testing
```bash
# Run all tests
[Your test command]

# Run specific test suite
[Your test suite commands]

# Example:
# pytest tests/
# pytest tests/unit/
# pytest tests/test_specific.py -v
```

### Maintenance
```bash
# Check system status
[Your status command]

# View logs
[Your logs command]

# Run health check
[Your health check command]
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

### [Your Architecture Pattern]

[Describe your project's architecture. Examples:]

**Monolithic Web App:**
- Single application server
- Direct database access
- [Framework] with [pattern] structure

**Microservices:**
- Service A: [Purpose]
- Service B: [Purpose]
- Message queue: [Technology]

**API + Frontend:**
- Backend API: [Technology/Framework]
- Frontend: [Technology/Framework]
- Communication: REST/GraphQL/gRPC

### Project Structure
```
[your-project]/
├── [main-code-dir]/     # Source code
│   ├── [subdir]/        # Description
│   ├── [subdir]/        # Description
│   └── [subdir]/        # Description
├── tests/               # Test suite
├── docs/                # Documentation
├── scripts/             # Utility scripts
├── [config-file]        # Main configuration
└── requirements.txt     # Dependencies (or package.json, etc.)
```

### Database Pattern (if applicable)

**[Your database approach]:**

**Single Database:**
- All data in one database
- [Schema organization approach]

**Multiple Databases:**
- Database 1: [Purpose]
- Database 2: [Purpose]

**Critical**: Always use the correct database session/connection:
- [How to access database 1]
- [How to access database 2]

## Database Session Management (if applicable)

**[Your framework] Dependency Injection Pattern** (if using DI):
```python
# Example for FastAPI with SQLAlchemy
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from [your_project].database import get_session

@router.get("/items")
async def get_items(db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(Item))
    return result.scalars().all()
```

**Manual Session Management** (if not using DI):
```python
# Your session management pattern
async with get_session() as session:
    # Your database operations
    pass
```

## API Development Patterns (if applicable)

### Creating New Endpoints

**1. Define Schema** (if using schemas):
```python
# [path/to/schemas]
class [Entity]Base(BaseModel):
    field1: str
    field2: int

class [Entity]Create([Entity]Base):
    pass

class [Entity]Response([Entity]Base):
    id: str
    created_at: datetime
```

**2. Create Service** (if using service layer):
```python
# [path/to/services]
class [Entity]Service:
    def __init__(self, db: Session):
        self.db = db

    async def create_[entity](self, data: [Entity]Create):
        # Business logic
        pass
```

**3. Add Endpoint**:
```python
# [path/to/routes]
@router.post("/[entities]")
async def create_[entity](
    data: [Entity]Create,
    service: [Entity]Service = Depends()
):
    return await service.create_[entity](data)
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
[VAR_NAME]=[description]
[VAR_NAME]=[description]
```

**Optional:**
```bash
[VAR_NAME]=[description]
[VAR_NAME]=[description]
```

## Common Issues & Solutions

### Issue 1: [Problem Description]
**Symptoms:** [What the user sees]

**Solution:**
```bash
[Commands to fix]
```

### Issue 2: [Problem Description]
**Symptoms:** [What the user sees]

**Solution:**
```bash
[Commands to fix]
```

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
- **[Framework]**: [URL]
- **[Database]**: [URL]
- **[Key Library]**: [URL]

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

**Last Updated:** [DATE]
**Project Version:** [VERSION]
