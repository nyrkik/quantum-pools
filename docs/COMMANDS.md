# Claude Code - Command Reference

**Last Updated:** October 23, 2025

Quick command reference for streamlined development workflow with Claude Code.

---

## Commit Commands

### `commit` or `commit-go`
Commit changes with descriptive message, **push to GitHub**, update SESSION_LOG.md, and continue working.

**Usage:**
```
User: commit
```

**What happens:**
1. Git status and diff review
2. Staged files committed with detailed message
3. **Pushed to GitHub (cloud backup)**
4. SESSION_LOG.md updated with progress
5. TodoWrite updated
6. Continues to next task automatically

**Why auto-push:**
- Immediate cloud backup (protects against data loss)
- Solo developer workflow (no team coordination needed)
- Network required anyway (Claude needs internet)

---

### `commit-pause`
Commit changes, **push to GitHub**, and pause for your review/input before continuing.

**Usage:**
```
User: commit-pause
```

**What happens:**
1. Same as `commit` (steps 1-5)
2. Stops and waits for your next instruction

**Use when:**
- Want to review changes before continuing
- Need to test manually before next step
- Switching context to different task

---

### `commit-local`
Commit changes WITHOUT pushing to GitHub (rare use).

**Usage:**
```
User: commit-local
```

**What happens:**
1. Git status and diff review
2. Staged files committed with detailed message
3. SESSION_LOG.md updated with progress
4. TodoWrite updated
5. **No push to GitHub** (stays local only)
6. Continues to next task automatically

**Use when:**
- Testing risky changes you might want to undo
- Experimenting with something you're not ready to backup
- Working offline (rare since Claude needs internet)

---

### `commit-status`
Show what would be committed without actually committing.

**Usage:**
```
User: commit-status
```

**What happens:**
- Shows `git status` summary
- Shows `git diff --stat` overview
- Lists modified files
- No actual commit made

**Use when:**
- Checking progress mid-task
- Verifying file changes before commit
- Quick status check

---

## Backlog Commands

### `backlog: [your idea]`
Instantly add feature idea to BACKLOG.md without interrupting current work.

**Usage:**
```
User: backlog: Add breed-specific activity benchmarks
User: backlog: Screenshot upload with AI vision for wearable data
User: backlog: critical - Fix user deletion cascade issue
```

**What happens:**
1. Idea added to appropriate category in BACKLOG.md
2. Priority auto-detected from keywords (critical, important, experiment)
3. Timestamp added
4. Continues current task without interruption

**Priority keywords:**
- `critical` or `blocking` → 🔥 Critical
- `important` or `high` → ⭐ High Priority
- `nice` or `medium` → 📌 Medium Priority
- `experiment` or `explore` → 🧪 Experiment
- No keyword → 💡 Low Priority

---

### `backlog-review`
Show recent backlog items (last 10).

**Usage:**
```
User: backlog-review
```

**Output:**
- Last 10 items added
- Grouped by priority
- Quick scanning view

---

### `backlog-priority`
Sort and show backlog by priority level.

**Usage:**
```
User: backlog-priority
```

**Output:**
- All items sorted by priority (Critical → Low)
- Count of items per priority
- Helps with planning sessions

---

## Task Management

### `todo` or `tasks`
Show current TodoWrite list with status.

**Usage:**
```
User: todo
User: tasks
```

**Output:**
- All current tasks with status (pending/in_progress/completed)
- Progress summary (X of Y completed)
- Currently in-progress task highlighted

---

### `next`
Get recommendation for what to work on next based on priorities.

**Usage:**
```
User: next
```

**What happens:**
1. Reviews current TodoWrite list
2. Reviews PROJECT_STATUS.md roadmap
3. Recommends specific next task
4. Provides brief rationale

**Output example:**
```
Recommended next task: Create activity statistics/aggregation endpoints

Reasoning:
- Builds on completed activity tracking system
- Required for dashboard UI (upcoming)
- Mentioned in LAUNCH_PLAN.md Week 1 goals
- Unblocks OpenAI health insights integration

Ready to start? (yes/no)
```

---

### `done [task]`
Mark specific task as complete in TodoWrite.

**Usage:**
```
User: done activity statistics
User: done stripe integration
```

**What happens:**
- Finds matching task in TodoWrite
- Marks as completed
- Shows updated task list
- Suggests next task

---

## Navigation & Context

### `list` or `help`
Show all available commands with descriptions.

**Usage:**
```
User: list
User: help
```

**Output:**
This file! Complete command reference.

---

### `where`
Quick status - current phase, what's done, what's next.

**Usage:**
```
User: where
```

**Output:**
```
📍 Current Location:
Phase: Backend Development - Integrations
Last completed: Multi-source activity data architecture
Currently working on: Activity statistics endpoints
Next up: OpenAI health insights integration

Progress: ~50% complete (Foundation + Core Features)
```

---

### `status`
Show PROJECT_STATUS.md summary.

**Usage:**
```
User: status
```

**Output:**
- Current phase details
- Completed phases (checkmarks)
- Upcoming phases
- Overall progress percentage

---

### `roadmap`
Show LAUNCH_PLAN.md timeline.

**Usage:**
```
User: roadmap
```

**Output:**
- 6-week timeline with current week highlighted
- Pre-beta requirements checklist
- Next milestone dates
- Completion status

---

## Development Workflow

### `test`
Run tests for current feature.

**Usage:**
```
User: test
```

**What happens:**
1. Identifies current feature from context
2. Runs relevant test suite
3. Shows pass/fail summary
4. Reports any errors with file locations

**Smart detection:**
- Working on activity endpoints → Runs activity tests
- Just modified auth_service.py → Runs auth tests
- "test everything" → Runs full test suite

---

### `review`
Review current changes before committing.

**Usage:**
```
User: review
```

**Output:**
- Files modified
- Lines added/removed
- Key changes summary
- Potential issues flagged (if any)
- Suggestions for improvement

**Use before:** Major commits, PR creation, deploying

---

### `docs`
Update documentation for current feature.

**Usage:**
```
User: docs
```

**What happens:**
1. Identifies what was just implemented
2. Updates relevant docs (FEATURES.md, CLAUDE.md, etc.)
3. Adds API endpoint documentation
4. Updates SESSION_LOG.md

---

### `swagger`
Show Swagger UI testing instructions for current endpoint.

**Usage:**
```
User: swagger
```

**Output:**
- URL: http://localhost:8000/docs
- Login instructions (if needed)
- How to authorize with JWT
- Relevant endpoint to test
- Sample request body

**Example:**
```
Testing the activity upload endpoint:

1. Go to: http://localhost:8000/docs
2. Login with your test credentials
3. Copy access_token from response
4. Click "Authorize" button
5. Paste token and click "Authorize"
6. Find: POST /api/v1/activity/upload/{pet_id}
7. Try it out with:
   - pet_id: 45f7d4a4-be9c-4a9e-936a-006727700acf
   - file: test_data/fitbark_sample_7days.csv
   - source_type: fitbark
```

---

## Quick References

### `files`
Show key files related to current work.

**Usage:**
```
User: files
```

**Output:**
Based on current context (e.g., working on activity tracking):
```
Key files for Activity Tracking:

Models:
- src/models/activity.py

API Endpoints:
- src/api/v1/activity.py

Services:
- src/services/activity_service.py
- src/services/providers/fitbark_provider.py
- src/services/providers/manual_provider.py

Schemas:
- src/schemas/activity.py

Tests:
- tests/unit/test_activity_service.py
- tests/integration/test_activity_upload.py

Migrations:
- migrations/versions/0dd39480674c_add_multi_source_activity_fields.py
```

---

### `api`
Show relevant API endpoints for current feature.

**Usage:**
```
User: api
```

**Output:**
```
Activity Tracking API Endpoints:

POST   /api/v1/activity              Create manual activity
POST   /api/v1/activity/upload/{id}  Upload CSV data
GET    /api/v1/activity/{id}         Get single activity
GET    /api/v1/activity/pet/{id}     List pet activities
GET    /api/v1/activity/pet/{id}/stats  Activity statistics
PATCH  /api/v1/activity/{id}         Update activity
DELETE /api/v1/activity/{id}         Delete activity

All endpoints require authentication (JWT Bearer token)
Swagger UI: http://localhost:8000/docs
```

---

### `db`
Show database schema info for current model.

**Usage:**
```
User: db
```

**Output:**
```
Activity Model Schema:

Table: activities

Fields:
- id (UUID, PK)
- pet_id (UUID, FK → pets)
- user_id (UUID, FK → users)
- date (DateTime)
- source_type (String, indexed) - fitbark, manual, etc.
- activity_score (Integer)
- minutes_rest (Integer)
- minutes_active (Integer)
- minutes_play (Integer)
- distance_miles (Float)
- calories (Integer)
- provider_data (JSON) - Device-specific extras
- created_at (DateTime)
- updated_at (DateTime)

Indexes:
- ix_activities_pet_id
- ix_activities_user_id
- ix_activities_source_type
- ix_activities_date
```

---

## Command Aliases

Some commands have shortcuts:

| Command | Alias |
|---------|-------|
| `commit-go` | `commit` |
| `tasks` | `todo` |
| `help` | `list` |

---

## Tips & Best Practices

### When to Use Commands

**During active development:**
- Use `commit` frequently (every logical checkpoint)
- Use `backlog: [idea]` to capture ideas without losing focus
- Use `test` before committing major changes

**When stuck or context switching:**
- Use `where` to regain context
- Use `status` or `roadmap` to see big picture
- Use `files` to find relevant code

**Before ending session:**
- Always `commit-pause` to save progress
- Use `todo` to see what's left
- Use `next` to plan next session

### Command Composition

You can use multiple commands in one message:
```
User: test, then commit-pause
User: review, and if it looks good, commit
User: where are we, and what's next?
```

---

## Future Commands (Ideas)

These don't exist yet but might be useful:

- `refactor [file]` - Suggest refactoring opportunities
- `optimize` - Performance optimization suggestions
- `security` - Security audit of recent changes
- `coverage` - Test coverage report
- `bench` - Run benchmarks
- `deploy` - Deploy to staging/production

Add these to BACKLOG.md if you want them!

---

**For Claude Code instances:**
When user uses these commands, execute the documented behavior immediately without asking for confirmation (unless specified otherwise).

**For users:**
These commands are designed to minimize interruptions and keep you in flow state. Use them freely!
