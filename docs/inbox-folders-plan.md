# Inbox Folders Plan

> **Removal note:** Delete this doc and its CLAUDE.md index entry when all 3 phases are shipped and verified.

## Status (2026-04-12)

- **Phase 1 (Folders + Backend + UI):** ✅ SHIPPED. System folders: Inbox, Sent, Spam (Automated folder killed — replaced with inline "Auto" badge). Custom folders indented under Inbox. Desktop sidebar + mobile pill bar.
- **Phase 2 (Filter Rules):** ~PARTIAL. Tag-driven auto-routing works via `SuppressedEmailSender.folder_id` — tagging a sender (billing/vendor/etc.) can route all their threads to a folder, including domain patterns (`*@scppool.com`). Full rule builder UI not built.
- **Phase 3 (Gmail Label Sync):** ~PARTIAL. Read/unread state syncs to Gmail via `users.threads.modify()`. Folder move → Gmail label push NOT built. `gmail_thread_id` stored on AgentThread during sync for identification.

## Overview

Folders add organizational scaffolding to the inbox. Three independently shippable phases: basic folders, filter rules, Gmail label sync.

Folders are orthogonal to thread status (pending/handled/ignored). A thread in the "Vendors" folder can still be pending. Folders are *where*, status is *what state*.

---

## Phase 1: Folders Model + Backend + Basic UI ✅ SHIPPED

### 1a. Database

**New model: `inbox_folders`**

| Column | Type | Notes |
|--------|------|-------|
| id | String(36) PK | uuid4 |
| organization_id | String(36) FK | indexed |
| name | String(100) | NOT NULL |
| icon | String(50) | nullable, lucide icon name |
| color | String(20) | nullable, tailwind color token |
| sort_order | Integer | default 0 |
| is_system | Boolean | default False, can't delete/rename |
| system_key | String(20) | "inbox", "sent", "automated", "spam" — unique per org |
| gmail_label_id | String(200) | nullable, Phase 3 only |
| created_at | DateTime | |
| updated_at | DateTime | |

UniqueConstraint(organization_id, system_key) NULLS NOT DISTINCT.

**Alter `agent_threads`:**
- Add `folder_id String(36) FK inbox_folders.id, nullable, indexed` — NULL = Inbox
- Add `folder_override Boolean default=False` — set True on manual move, prevents rules from re-assigning

**System folder seeds** (per org):
- Inbox (system_key="inbox", icon="inbox", sort_order=0)
- Sent (system_key="sent", icon="send", sort_order=1)
- Automated (system_key="automated", icon="bot", sort_order=2)
- Spam (system_key="spam", icon="shield-alert", sort_order=3)

**Backfill existing threads:**
- category in (spam, auto_reply) → Spam folder
- last_direction == "outbound" AND has_pending == False → Sent folder
- status == "handled" AND category in (no_response, thank_you, general with no draft) → Automated folder
- All others → NULL (Inbox)

### 1b. Backend

**New service: `inbox_folder_service.py`**
- `list_folders(org_id)` — returns all folders with thread counts (total + unread per folder). Single query with LEFT JOIN + COUNT FILTER.
- `create_folder(org_id, name, icon, color)` — custom folder
- `update_folder(org_id, folder_id, ...)` — can't rename system folders
- `delete_folder(org_id, folder_id)` — can't delete system; moves threads back to Inbox
- `move_thread(org_id, thread_id, folder_id)` — sets folder_id + folder_override=True
- `ensure_system_folders(org_id)` — idempotent, called on org creation

**New router: `inbox_folders.py`**
- GET /v1/inbox-folders — list with counts
- POST /v1/inbox-folders — create
- PUT /v1/inbox-folders/{id} — update
- DELETE /v1/inbox-folders/{id} — delete
- POST /v1/inbox-folders/move-thread — body: {thread_id, folder_id}

**Modify existing:**
- `admin_threads.py`: add `folder_id` query param to thread listing
- `agent_thread_service.py`: add `folder_id` filter to `list_threads()`, per-folder counts in stats
- `thread_presenter.py`: add `folder_id` and `folder_name` to output

**Event:** `EventType.FOLDER_UPDATED` — publish on create/delete/move.

### 1c. Frontend

**Inbox page restructure:**
- Add `selectedFolderId` state (null = Inbox system folder)
- Pass `folder_id` to thread listing API
- Status tabs (pending/handled) become secondary filter within a folder

**New component: `inbox-folder-sidebar.tsx`**
- Vertical folder list: icon, name, unread badge
- System folders on top, then custom sorted by sort_order
- Active folder gets `bg-accent`
- "+" button to add custom folder (dialog)
- Right-click/kebab on custom folders: Rename, Change Color, Delete

**Layout:**
- Desktop: left panel (240px, collapsible) for folders
- Mobile: horizontal scrolling pill bar above thread list

**Thread table:** "Move to" dropdown action (ghost icon button). Calls move-thread endpoint.

### 1d. Orchestrator Auto-Assign

After classification + `update_thread_status()` in `process_incoming_email()`:
- category in (spam, auto_reply) → Spam folder
- last_direction == "outbound" → Sent folder
- Auto-handled general (no draft, not customer) → Automated folder
- Everything else → Inbox (default)

Only applies when `folder_override == False`.

---

## Phase 2: Inbox Filter Rules

### 2a. Database

**New model: `inbox_filter_rules`**

| Column | Type | Notes |
|--------|------|-------|
| id | String(36) PK | uuid4 |
| organization_id | String(36) FK | indexed |
| name | String(200) | NOT NULL |
| sort_order | Integer | evaluation priority (lower = first) |
| target_folder_id | String(36) FK | inbox_folders.id |
| is_active | Boolean | default True |
| conditions | JSONB | array of condition objects |
| created_at | DateTime | |
| updated_at | DateTime | |

**Conditions schema** (array, all must match = AND):
```json
[
  {"field": "sender_email", "op": "contains", "value": "@entrata.com"},
  {"field": "subject", "op": "contains", "value": "invoice"}
]
```

Fields: sender_email, sender_domain, subject, category, customer_id, delivered_to
Operators: equals, contains, starts_with, ends_with, matches (glob)

No OR groups — create two rules pointing to the same folder instead.

### 2b. Backend

**New service: `inbox_filter_rule_service.py`**
- `list_rules(org_id)`
- `create_rule(org_id, name, conditions, target_folder_id, sort_order?)`
- `update_rule(org_id, rule_id, ...)`
- `delete_rule(org_id, rule_id)`
- `evaluate_rules(org_id, thread, message) -> folder_id | None` — load all active rules ordered by sort_order, first match wins

**New router: `inbox_filter_rules.py`**
- CRUD endpoints + POST /test (dry-run against existing thread)

### 2c. Orchestrator Integration

After classification, before final status update:
```python
if not thread.folder_override:
    target = await filter_svc.evaluate_rules(org_id, thread, agent_msg)
    if target:
        thread.folder_id = target
```

Runs after system folder assignment — user rules can override system defaults.

### 2d. Frontend

**New page: Settings → Inbox Rules** (`/settings/inbox-rules/page.tsx`)
- Table of rules: name, conditions summary, target folder, active toggle
- Add/Edit opens dialog with conditions builder
- Field + Operator + Value rows, "Add condition" button
- "Test" button: pick a thread, show which rule matches
- Link from Settings hub + inbox settings

---

## Phase 3: Gmail Label Sync

### 3a. Database

- Add `sync_folders Boolean default=True` to `email_integrations`
- `inbox_folders.gmail_label_id` already exists from Phase 1

### 3b. Label Sync Service

**New file: `gmail/label_sync.py`**
- `sync_labels(integration)` — `users.labels.list()` → create/update QP folders with gmail_label_id. System Gmail labels (INBOX, SENT, SPAM, TRASH) map to QP system folders. Custom labels create custom folders.
- `apply_labels_to_thread(integration, gmail_msg_data, thread)` — read labelIds, find matching QP folder, set folder_id. Multiple labels → first non-system label wins.
- `push_label_change(integration, thread, old_folder, new_folder)` — `users.messages.modify()` to add/remove labels in Gmail. Non-blocking — QP move succeeds even if Gmail fails.

### 3c. Sync Integration

**`gmail/sync.py` changes:**
- `initial_sync()`: call `sync_labels()` first to create folders, then sync messages
- `_fetch_and_ingest()`: after process_incoming_email(), if sync_folders=True, call `apply_labels_to_thread()`
- `_sync_history()`: watch labelsAdded/labelsRemoved history types, update thread folder_id (unless folder_override=True)

### 3d. Bidirectional Push

**`inbox_folder_service.move_thread()`**: after updating folder_id, if org has gmail_api integration with sync_folders=True and both folders have gmail_label_id, call `push_label_change()` fire-and-forget.

### 3e. Frontend

- Settings → Email: "Sync Folders" toggle per gmail_api integration
- "Sync Labels Now" button → POST /v1/email-integrations/{id}/sync-labels
- PATCH /v1/email-integrations/{id} to update sync_folders toggle

---

## Key Design Decisions

1. **folder_id nullable = Inbox** — avoids migrating every thread, simplifies default view query
2. **folder_override flag** — cheapest way to prevent rules from fighting manual moves
3. **JSONB conditions** — simple for 5-20 rules per org, no junction table needed
4. **Folders orthogonal to status** — no breaking change to existing workflow
5. **No folder-level permissions** — existing visibility_permission on threads handles access control
6. **Gmail sync is non-blocking** — QP folder move succeeds even if Gmail API fails, error is logged

## Dependencies

- Phase 2 depends on Phase 1 (needs folders to exist)
- Phase 3 depends on Phase 1 (needs gmail_label_id column) but NOT Phase 2
- Each phase ships independently
