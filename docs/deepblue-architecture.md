# DeepBlue Field — Architecture

DeepBlue is QuantumPools' in-app AI assistant. It's a tool-using agent with persistent conversations, cost controls, and a knowledge-gap learning loop.

## Overview

DeepBlue has three UI surfaces:
1. **Floating button** — ephemeral quick lookups on any page
2. **Bottom sheet** — expands from the button, drawer view with history
3. **Full page** (`/deepblue`) — ChatGPT-style sidebar + chat for longer work

Conversations are persisted server-side and can be private, shared with the team, or case-linked.

## Schema

### Core table: `deepblue_conversations`

Primary entity. One row per conversation (which may contain many messages).

| Column | Type | Purpose |
|---|---|---|
| id | String(36) PK | UUID |
| organization_id | FK → organizations | Org scoping |
| user_id | FK → users | Creator/owner |
| case_id | FK → service_cases (nullable) | If case-linked, always visible to case viewers |
| context_json | Text (JSON) | `{customer_id, property_id, bow_id, visit_id}` at creation time |
| title | String(200) | Auto-generated from first message |
| messages_json | Text (JSON array) | Full message history with tool blocks |
| model_tier | String(20) | `fast` (Haiku) or `standard` (Sonnet) |
| total_input_tokens | Integer | Cumulative for conversation |
| total_output_tokens | Integer | Cumulative |
| visibility | String(20) | `private` | `shared` | `case` |
| pinned | Boolean | Owner's pin flag |
| deleted_at | DateTime (nullable) | Soft delete timestamp |
| shared_at | DateTime (nullable) | When visibility changed to shared |
| shared_by | String(36) | User who shared |

### Per-turn logging: `deepblue_message_logs`

One row per assistant turn. Anomaly detection foundation.

| Column | Type | Purpose |
|---|---|---|
| id | PK | UUID |
| organization_id | FK | |
| user_id | FK | |
| conversation_id | String(36) | Links to conversation (not FK for retention resilience) |
| message_index | Integer | Position in conversation |
| input_tokens | Integer | |
| output_tokens | Integer | |
| total_tokens | Integer | |
| tool_calls_made | Text (JSON array) | Tools invoked this turn |
| tool_count | Integer | Denormalized count |
| user_prompt_hash | String(32) | SHA-256 for pattern detection without storing prompts |
| user_prompt_length | Integer | |
| response_length | Integer | |
| latency_ms | Integer | End-to-end time |
| category | String(30) | `pool_service` | `business_ops` | `off_topic` | `unknown` |
| off_topic_detected | Boolean | Relevance flag |
| model_used | String(20) | |
| created_at | DateTime (indexed) | 90-day retention |

### Daily user rollup: `deepblue_user_usage`

Denormalized daily aggregates for quota enforcement.

| Column | Purpose |
|---|---|
| user_id + date | Unique key |
| message_count | |
| input_tokens, output_tokens | |
| tool_calls_count | |
| off_topic_count | |

### Monthly cost rollup: `deepblue_usage_monthly`

Survives conversation retention cleanup. Preserves cost data indefinitely.

| Column | Purpose |
|---|---|
| organization_id + user_id + year + month | Unique key |
| conversations_created, messages_sent | |
| total_input_tokens, total_output_tokens | |
| total_cost_usd_estimated | Rolled up at retention hard-delete time |

### Knowledge gaps: `deepblue_knowledge_gaps`

When the meta-tool (`query_database`) is used or DeepBlue says "I don't know," a gap is logged. Reviewed weekly to decide which new tools to build.

| Column | Purpose |
|---|---|
| user_question | Original prompt |
| resolution | `meta_tool` | `unresolved` |
| sql_query | SQL used if meta_tool |
| reason | Claude's stated reason for meta-tool use |
| result_row_count | |
| reviewed | Admin flag |
| promoted_to_tool | Tool name if promoted |

## Relationships

```
organizations
    │
    ├─→ deepblue_conversations (many)
    │       │
    │       ├─→ case_id → service_cases (optional)
    │       └─ messages_json (self-contained)
    │
    ├─→ deepblue_message_logs (many) ─── user_id
    │       └─ conversation_id (soft link)
    │
    ├─→ deepblue_user_usage (many) ─── user_id + date
    │
    ├─→ deepblue_usage_monthly (many) ─── user_id + year + month
    │
    └─→ deepblue_knowledge_gaps (many) ─── user_id
            └─ conversation_id (soft link)

users
    └─→ deepblue_conversations.user_id (owner)
```

## Cost controls

Four enforcement layers, all in `quota_service.py`:

1. **Rate limit** — Redis counter, per-user per-minute. Default 30/min. Fails open if Redis is down.
2. **User daily quota** — checked against `deepblue_user_usage` row for today. Defaults: 500K input tokens, 100K output tokens.
3. **User monthly quota** — sum of last 30 days. Defaults: 5M input, 1M output.
4. **Org monthly quota** — sum across all users, last 30 days. Defaults: 50M input, 10M output.

Quotas are configurable per org on the `organizations` table.

## Retention policy

Managed by `retention_service.py`:

| Data | Lifetime | Triggers |
|---|---|---|
| `deepblue_conversations` (private, unpinned, no case) | 90 days inactive → soft delete | |
| soft-deleted conversations | +30 days → hard delete | Rolls up to `deepblue_usage_monthly` first |
| `deepblue_message_logs` | 90 days | Purged |
| `deepblue_knowledge_gaps` | 90 days | Purged |
| case-linked conversations | never | Case lifecycle |
| shared conversations | never | Manual unshare or delete |
| pinned conversations | never | Manual unpin or delete |

Cleanup triggered via `POST /v1/deepblue/retention/run` (owner only). Future: APScheduler cron.

## Tool-use loop

`engine.py:DeepBlueEngine.process_message()` implements the agent loop:

```
1. Quota check (fails fast if exceeded)
2. Build context (org profile + page context IDs → rich text)
3. Load or create conversation
4. Reconstruct claude_messages from messages_history (text + structured blocks)
5. Loop (max 5 rounds):
     a. Call Claude with system prompt + tools + messages
     b. For each content block in response:
          - text: stream to client, append to assistant turn
          - tool_use: execute tool, stream result, append to turn
     c. If no tools called, exit loop
     d. Otherwise append tool_results as user message, loop again
6. Persist conversation (text + structured blocks for next-turn fidelity)
7. Log to message_logs, user_usage, knowledge_gaps
8. Yield done event
```

Max 5 tool-use rounds per turn prevents runaway loops. Per-turn counter in `ToolContext` also caps parts searches at 3 per turn.

## Tools (as of 2026-04-05)

### Knowledge (auto-execute, no confirmation)
- `chemical_dosing_calculator` — deterministic, wraps `dosing_engine.py`. Never AI math.
- `get_organization_info` — org profile (also in baseline context)

### Lookup (auto-execute)
- `get_agent_health` — agent metrics, failures, per-agent breakdown (wraps agent-ops observability)
- `find_customer` — fuzzy search customers (ILIKE + pg_trgm fallback)
- `find_property` — fuzzy search properties with BOW details
- `get_equipment` — equipment on a property/BOW
- `get_chemical_history` — recent readings
- `get_service_history` — visits
- `get_customer_info` — full customer detail
- `find_replacement_parts` — catalog + web search, supports compare_retailers mode
- `search_equipment_catalog` — shared catalog search
- `get_billing_documents` — invoices + estimates merged tool
- `get_open_jobs` — agent_actions
- `get_cases` — service cases
- `get_routes_today` — today's routes per tech
- `get_techs` — active techs
- `get_billing_terms` — org cost settings
- `get_service_tiers` — residential tier packages
- `get_inspections` — health dept inspection history for a property
- `get_payments` — payment history

### Meta
- `query_database` — read-only SELECT with 6-layer safety stack (sqlparse validator, table whitelist, org-scope enforcement, row limit, timeout, read-only transaction)

### Action (requires preview + confirm)
- `draft_broadcast_email` — bulk email with recipient filters (all_active, commercial, residential, custom, test)
- `add_equipment_to_pool` — adds equipment_items row
- `log_chemical_reading` — adds chemical_readings row
- `update_customer_note` — appends to customers.notes

Each action tool returns a preview; the frontend renders a confirmation card; user taps confirm → dedicated `POST /confirm-*` endpoint executes the write.

## Visibility model

Three states:

| State | Who can see | Who can modify |
|---|---|---|
| private (default) | Owner only | Owner |
| shared | Everyone in the org | Owner only |
| case (case_id set) | Anyone who can view the case | Owner only |

Shared conversations are read-only for non-owners. "Fork" creates a private copy for the viewer to continue.

Pin is owner-only today. Future: per-user pin table if shared chats need personal bookmarking.

## UI entry points

- **Floating button** (`components/deepblue/deepblue-trigger.tsx`) — bottom-right on all pages
- **Bottom sheet** (`components/deepblue/deepblue-sheet.tsx`) — opens from trigger, contains history drawer
- **Full page** (`app/(dashboard)/deepblue/page.tsx`) — ChatGPT-style layout with sidebar
- **Case card** (`components/deepblue/case-deepblue-card.tsx`) — embedded in case detail right column, persistent per case
- **Dashboard card** — "Recent DeepBlue Chats" on main dashboard links to `/deepblue?id=...`

## Admin pages

- `/settings/deepblue-usage` — token usage, cost estimates, per-user breakdown with anomaly highlighting
- `/settings/deepblue-gaps` — knowledge gap review, promote patterns to tools

## Endpoints

### Chat
- `POST /v1/deepblue/message` — SSE streaming, main entry point
- `GET /v1/deepblue/conversations?scope=mine|shared|all` — list
- `GET /v1/deepblue/conversations/{id}` — detail (access: owner, shared, or case-linked)
- `PATCH /v1/deepblue/conversations/{id}/visibility` — share/unshare (owner only)
- `PATCH /v1/deepblue/conversations/{id}/pin` — toggle pin (owner only)
- `PATCH /v1/deepblue/conversations/{id}/save-to-case` — attach to case
- `DELETE /v1/deepblue/conversations/{id}` — soft delete (owner only, no case-linked)
- `POST /v1/deepblue/conversations/{id}/restore` — undelete within 30-day window
- `POST /v1/deepblue/conversations/{id}/fork` — copy shared conversation into private

### Actions (confirmation endpoints for write tools)
- `POST /v1/deepblue/confirm-add-equipment`
- `POST /v1/deepblue/confirm-log-reading`
- `POST /v1/deepblue/confirm-update-note`
- `POST /v1/deepblue/confirm-broadcast`

### Case conversations
- `GET /v1/deepblue/cases/{case_id}/conversations` — list case-linked

### Admin
- `GET /v1/deepblue/knowledge-gaps` — list gaps
- `PATCH /v1/deepblue/knowledge-gaps/{id}/review` — mark reviewed
- `GET /v1/deepblue/usage-stats` — dashboard data
- `POST /v1/deepblue/retention/run` — owner-only cleanup trigger
- `POST /v1/deepblue/eval-run` — owner-only tool selection eval harness

## Design decisions

**Why persist tool results in conversation history?**
Without tool results, resuming a conversation loses fidelity. Claude only sees its own text summary of prior tool outputs. With structured blocks persisted, the full raw data survives across turns — so "find parts for the pump we discussed" can reference exact model numbers seen in a prior `get_equipment` call.

**Why separate tables for each DeepBlue concern?**
- `deepblue_conversations`: primary entity, the chat itself
- `deepblue_message_logs`: per-turn analytics, separate lifecycle from conversations (90-day purge regardless)
- `deepblue_user_usage`: daily rollup for fast quota checks (avoids scanning message_logs)
- `deepblue_usage_monthly`: preserves cost data when conversations are retention-purged
- `deepblue_knowledge_gaps`: learning loop, independent of conversation retention

Each table has a single responsibility. Mixing them would create schema drift and coupling.

**Why a meta-tool (`query_database`)?**
Covers the long tail of data questions without requiring a new tool for every possibility. Hard-secured with 6 defense layers. Every use is logged to `deepblue_knowledge_gaps` so repeated patterns can be promoted to dedicated tools.

**Why trigram similarity for search?**
User typos and variant spellings ("walili" vs "walali") broke exact ILIKE searches. pg_trgm provides typo-tolerant fallback with a 0.3 similarity threshold. Primary search is still exact ILIKE for speed; trigram only runs when exact returns nothing.

## Living eval suite

The eval harness is not a static test list — it's a corpus that grows from real usage and adversarial generation.

### Architecture

**Table: `deepblue_eval_prompts`** — DB-backed test cases. Each prompt has:
- `prompt_key` (stable slug for tracking across runs)
- `source`: `static | knowledge_gap | ai_generated | manual`
- `max_turns` (1-3) — for multi-step workflows
- Expectations: `expected_tools`, `expected_tools_any`, `expected_off_topic`, `expected_no_tools_required`, `must_not_contain`
- `active` flag — can disable without deleting
- `consecutive_passes` + `last_run_at` — smart mode uses these

**Table: `deepblue_eval_runs`** — history of all runs (total, passed, failed, model_used, system_prompt_hash, full results JSON)

**New column on `deepblue_knowledge_gaps`:** `promoted_to_eval` — tracks which gaps have become eval prompts

### Runner (`eval_runner.py`)

Multi-turn capable. For each prompt:
1. Start with user message
2. Call Claude with tools
3. If tools are called, execute them (reads go to real DB, writes return preview responses)
4. Feed tool results back to Claude
5. Loop up to `max_turns` or until no more tools called
6. Evaluate all tools called across all turns against expectations

**Safety:** write tools (`add_equipment_to_pool`, `log_chemical_reading`, `update_customer_note`) return preview dicts and never write to the DB — writes only happen via confirm endpoints which the runner doesn't call. So eval runs are always safe.

### Modes

- **Full**: runs all active prompts every time. Use for regression check after big changes.
- **Smart**: skips prompts with ≥5 consecutive passes AND last run within 7 days. Focuses compute on unstable tests and stale stability checks. Use for routine runs.

### Growth mechanisms

1. **Static seeds** — `EVAL_PROMPTS` in `eval_prompts.py` are seeded into the DB on first run via `seed_static_prompts()`. Idempotent.
2. **Knowledge gap promotion** — `POST /v1/deepblue/eval-prompts/promote-gap/{gap_id}` turns a real user question DeepBlue couldn't answer into an eval prompt. The resulting prompt has `must_not_contain: ["i don't know", "i can't find", ...]` so passing means DeepBlue now handles it.
3. **AI adversarial generation** — `POST /v1/deepblue/eval-prompts/generate` calls Sonnet with the current tool list + recent failures + unresolved gaps + existing prompts, asks it to write new tricky test cases. Returns drafts for human review. `POST /v1/deepblue/eval-prompts/approve-draft` activates approved ones.

### Endpoints

- `POST /v1/deepblue/eval-run?mode=full|smart` — run suite, persist results
- `GET /v1/deepblue/eval-runs` — list recent runs
- `GET /v1/deepblue/eval-runs/{id}` — load a specific run with full results
- `GET /v1/deepblue/eval-prompts` — list all prompts in the corpus
- `PATCH /v1/deepblue/eval-prompts/{id}` — enable/disable a prompt
- `POST /v1/deepblue/eval-prompts/promote-gap/{gap_id}` — promote a gap
- `POST /v1/deepblue/eval-prompts/generate` — generate drafts
- `POST /v1/deepblue/eval-prompts/approve-draft` — activate a draft

### Dev UI

`/dev` page has an "Eval Suite" card with three buttons:
- **Smart** — skip-passing mode, fast iteration
- **Full** — run everything
- **Generate** — produce drafts via AI, review + approve individually

Draft approval, history review, and per-prompt details all inline on the same card.

### Future work

- Mutation testing: auto-vary passing prompts to find brittleness ("Keith Lew" → "keith", "pH 6.8" → "pH 6.8-7.0")
- Auto-promote knowledge gaps on a schedule instead of manual click
- Per-prompt cost tracking (track how many tokens each eval prompt consumes across runs)

## Related systems

### Agent health monitoring
Not part of DeepBlue per se, but feeds into it via `get_agent_health` tool.
- `src/services/agents/health_monitor.py` — threshold-based alerting on `agent_logs`
- `POST /v1/agent-ops/health-check` — manual trigger (cron hook later)
- Fires `type=agent_health` notifications to owners/admins with 60-minute dedup
- Thresholds: success rate < 90% (24h), ≥3 failures/hour per agent, ≥10 failures/hour org-wide
- DeepBlue users can ask "how are the agents doing?" and get the same data conversationally
- See `memory/plan-agent-anomaly-detection.md` for the future upgrade path to baseline-based detection

## Future work

- APScheduler job to run retention cleanup daily (currently manual)
- APScheduler job to run agent health checks every 15 min (currently manual via endpoint)
- Anomaly detection upgrade for agent health (see memory plan doc)
- Per-user pins table (`deepblue_user_pins`) if shared chats need personal bookmarks
- CC capture for inbound emails + multi-sender contact learning (unrelated to DeepBlue but will affect customer matching which DeepBlue relies on)
- Voice input (Web Speech API)
- Offline service worker + static dosing reference tables
