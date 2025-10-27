# CLAUDE.md - Core Rules for AI Development

## Read These Rules FIRST - Always Apply

### 1. Response Length (ENFORCED)
- Max 3 lines unless asked for detail
- No bullets, celebrations, or summaries
- Just: "Done" or "Fixed X"

### 2. Process Management (CRITICAL)
- NEVER use background bash (no `&`, no `run_in_background: true`)
- NEVER manually start uvicorn - use `restart_server.sh`
- Kill processes immediately with KillShell if accidentally created
- Use Read with `offset`/`limit` for large files (>500 lines)

### 3. Sequential Work (TodoWrite)
- One task at a time, mark `in_progress` → `completed`
- Never jump between incomplete tasks
- Fix issues immediately before moving forward

### 4. File Operations
Use Claude Code tools (not bash):
- Read (not cat)
- Write (not heredoc)
- Edit (not sed/awk)
- Grep (not grep command)
- Glob (not find)

Use bash ONLY for: git, pip/npm, tests, migrations, service restarts

### 5. No Placeholders
- No TODOs, FIXMEs, or "implement later"
- Production-ready code from day one
- Complete error handling and validation

### 6. Session Start Protocol
After context compacting, start with:
```
Understood - core rules:
1. Max 3 lines per response unless asked
2. NEVER background bash
3. NEVER manually start uvicorn
4. Sequential work with TodoWrite
5. Use Claude Code tools for files
6. No placeholders, production-ready only
7. Check existing docs before creating new ones
```

### 7. Documentation Discipline (CRITICAL)
- **Check existing docs BEFORE creating new ones**
- Update existing docs, never duplicate content
- Max 500 lines per doc (split if larger, archive old content)
- Delete outdated docs immediately, don't let them rot
- Use git commits for change history (not SESSION_LOG.md)
- One topic = one location (use links for cross-references)

---

## Project: Quantum Pool Solutions (Quantum Pools)

**AI-powered pool service management SaaS platform**
- Python 3.11 + FastAPI (async)
- PostgreSQL + SQLAlchemy 2.0
- Server: `localhost:7006`
- Path: `/mnt/Projects/quantum-pools`

**Quick Start:**
```bash
cd /mnt/Projects/quantum-pools
source venv/bin/activate
./restart_server.sh  # Kills old processes, starts new server
```

---

## Documentation Structure

**All detailed docs are in `/docs` directory:**
- `DEVELOPMENT.md` - Setup, commands, running the app
- `ARCHITECTURE.md` - Tech stack, multi-tenancy, auth, database
- `STANDARDS.md` - Code quality rules, enterprise standards
- `PROJECT_STATUS.md` - Current phase, progress, next steps
- `BACKLOG.md` - Future features by priority

**Documentation Rules:**

### Single Source of Truth
- Before creating ANY new doc, check if topic exists elsewhere
- If exists: update existing doc, don't create new one
- Cross-reference with links, never duplicate content

### Doc Size Limits
- Individual docs: 500 lines maximum
- CLAUDE.md: 75 lines maximum (this file)
- If exceeding: split into focused sub-docs OR archive old content

### What NOT to Document
- ❌ Individual commit decisions (use git messages)
- ❌ Session-by-session logs (use git history)
- ❌ Temporary debugging notes (delete after fixed)
- ❌ "Work in progress" status (use TodoWrite)

### What TO Document
- ✅ Architecture decisions (why we chose X over Y)
- ✅ Non-obvious patterns (not self-evident from code)
- ✅ External dependencies and their quirks
- ✅ Multi-step setup procedures

### Before Creating a New Doc - Ask:
1. Does this exist in another doc? → Update that doc instead
2. Is this temporary? → Don't document, use git/TodoWrite
3. Will this be >500 lines? → Plan to split it now
4. Should code be self-documenting instead? → Improve code

### Doc Lifecycle
- **Create:** Only if no existing doc covers the topic
- **Update:** Modify existing doc instead of creating new
- **Delete:** When doc is outdated, remove it immediately
- **Archive:** Move to `docs/archive/` if history needed

---

## Workflow Commands

Quick shortcuts for common tasks:

**Commit & Progress:**
- `commit` - Commit, push, update docs, continue
- `commit-pause` - Commit, push, update docs, pause for review

**Doc Management:**
- `docs-check` - List docs >400 lines, flag duplicates
- `docs-status` - Show PROJECT_STATUS.md summary

**Task Management:**
- `todo` - Show current TodoWrite tasks
- `where` - Quick status (phase, task, progress)

**Navigation:**
- `rules` - Trigger acknowledgment protocol (repeat core rules)

---

**Last Updated:** October 27, 2025
