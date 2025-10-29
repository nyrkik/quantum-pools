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

### 6. BASH COMMAND RESTRICTIONS (CRITICAL)
- Do NOT use bash_tool for any reason
- Do NOT execute terminal commands
- ONLY provide commands for human to run
- No exceptions - not for "quick checks" or "verifying"

### 7. Session Start Protocol
After context compacting, acknowledge core rules (see end of doc)

---

## Project: Quantum Pool Solutions

**AI-powered pool service management SaaS platform**
- Python 3.11 + FastAPI (async)
- PostgreSQL + SQLAlchemy 2.0
- Server: `localhost:7006`
- Path: `/mnt/Projects/quantum-pools`

**Quick Start:**
```bash
cd /mnt/Projects/quantum-pools
source venv/bin/activate
./restart_server.sh
```

---


---

## Documentation Discipline (CRITICAL)
## Project Structure (ENFORCED)
```
quantum-pools/                    (project root)
├── app/                          (deployable code ONLY)
│   ├── api/
│   ├── models/
│   ├── services/
│   └── static/
│
├── docs/                         (documentation at ROOT)
│   ├── app/                      (technical/developer docs)
│   │   ├── ARCHITECTURE.md
│   │   ├── DEVELOPMENT.md
│   │   ├── STANDARDS.md
│   │   ├── PROJECT_STATUS.md
│   │   └── BACKLOG.md
│   └── business/                 (business files - NOT deployed)
│       ├── financials/
│       ├── legal/
│       └── contracts/
│
├── venv/                         (dependencies at ROOT level)
├── scripts/                      (operational scripts)
├── tests/                        (test suite)
└── CLAUDE.md                     (this file)
```

**CRITICAL Rules:**
- ❌ NEVER create `app/docs/` - docs live at ROOT in `docs/app/`
- ❌ NEVER create `app/venv/` - venv lives at ROOT
- ✅ `app/` contains ONLY deployable application code
- ✅ Technical docs in `docs/app/`, business docs in `docs/business/`

**Exception:** Deployment docs (README for ops) can live in `app/docs/` if needed for production

### Before Creating ANY Doc:
1. Check if topic exists elsewhere → Update existing doc
2. Is this temporary? → Don't document, use git/TodoWrite
3. Will this be >500 lines? → Split into focused sub-docs
4. Should code be self-documenting? → Improve code instead

### Doc Size Limits
- Individual docs: 500 lines max (split if larger)
- CLAUDE.md: 150 lines max (this file)
- Check with: `./project-health-check.sh`

### Single Source of Truth
- One topic = one location
- Cross-reference with links, never duplicate
- Update existing docs, don't create new ones
- Delete outdated docs immediately

### What NOT to Document
- ❌ Session logs (use git history)
- ❌ Temporary debugging notes
- ❌ Individual commit decisions
- ❌ "Work in progress" status

---

## Health Monitoring (AUTOMATED)

**Pre-commit hook runs automatically** - Shows warnings before each commit

**Manual check:**
```bash
./project-health-check.sh
```

**Thresholds (warnings trigger at):**
- Source files: >500 files
- Python files: >500 lines each
- Docs: >500 lines each
- Venv: >600MB
- Git repo: >100MB
- Dependencies: >25 packages

**When warnings appear:**
- Red = Critical, fix immediately
- Yellow = Warning, address soon
- Green = Healthy

---

## Workflow Commands

**Commit & Progress:**
- `commit` - Commit, push, update docs, continue
- `commit-pause` - Commit, push, update docs, pause

**Doc Management:**
- `docs-check` - List docs >400 lines, flag duplicates
- `docs-status` - Show PROJECT_STATUS.md summary

**Task Management:**
- `todo` - Show current TodoWrite tasks
- `where` - Quick status (phase, task, progress)

**Navigation:**
- `rules` - Trigger acknowledgment protocol

---

## Session Start Acknowledgment

After context compacting, respond with:
```
Understood - core rules:
1. Max 3 lines per response
2. NEVER run bash commands
3. NEVER background processes
4. Sequential work with TodoWrite
5. Production-ready code only
6. Check existing docs before creating
7. docs/ at ROOT, never in app/
8. Run health check before major work
```

---

**Last Updated:** October 28, 2025
