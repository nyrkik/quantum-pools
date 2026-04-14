# Inbox Rules Unification Plan

> **Priority:** HIGH. Two parallel sender-handling systems exist (`inbox_routing_rules` and `suppressed_email_senders`). They overlap conceptually, neither is aware of the other, and the dual-system gap is how the **scppool block incident** went undetected (see Background). This plan unifies them into a single `inbox_rules` table.
>
> **Status:** Not started. Estimated 7-10 days when picked up.
>
> **Removal note:** Delete this doc when Phase E ships and verified.

---

## Kickoff context — read this first if you're starting fresh

If you're a Claude session beginning this work without the prior conversation in context, here's everything you need to start solidly:

### Patterns to mirror (don't re-derive these)

1. **Shared service helper pattern.** See `app/src/services/agents/send_failure.py` — a single helper that every send path calls in its except block. The `InboxRulesService` should follow the same shape: one entry point (`evaluate(message, thread, org_id) -> [Action]`), one application method (`apply(actions, thread, db)`), all callers route through it. No "we'll inline it just this once."
2. **Test-first discipline.** Every new endpoint/service gate gets a test. Patterns to copy from `app/tests/`:
   - `test_webhook_auth.py` — gating on a secret/token (mirror for any new admin endpoint)
   - `test_org_isolation.py` — every fetch-by-id needs `organization_id` in the where clause; the test asserts cross-org leakage is impossible
   - `test_send_failure_recovery.py` — exception handling that persists state (mirror for the new InboxRulesService failure paths)
   - `test_failed_filter.py` — query semantics tests (mirror for any new filter logic)
   See CLAUDE.md "Testing" section for run command + DB setup. 22 tests passing as of session 2026-04-13.
3. **The no-half-stepping rule.** From `~/.claude/projects/-srv-quantumpools/memory/feedback_no_half_stepping.md` — when fixing a bug, audit every similar path, add detection (canary/reconciliation/alert), close the visibility gap so the next instance is impossible to miss. Especially load-bearing for Phase B since the orchestrator is the email path and bugs there hide actual emails.
4. **Org-isolation everywhere.** Every fetch-by-id MUST filter by `organization_id` matching the caller's org. The 2026-04-13 security audit (`docs/inbox-security-audit-2026-04-13.md`) found 6 places that violated this — don't add more.

### Recent context (what shipped just before you start)

The 2026-04-13 session was a heavy hardening pass. Key things to be aware of:

- **All 5 outbound send paths** are wrapped in try/except using `record_outbound_send_failure` from `app/src/services/agents/send_failure.py`. Don't break that pattern when wiring InboxRulesService into the orchestrator.
- **Webhook auth** (`X-Webhook-Token`) gates `/api/v1/admin/postmark-webhook` and `/api/v1/inbound-email/webhook/{slug}`. Token in `.env` as `POSTMARK_WEBHOOK_TOKEN`. Verifier is `verify_postmark_webhook_token` in `admin_webhooks.py`.
- **Cross-org isolation** — every relevant fetch is org-filtered after the audit. Don't regress.
- **Failed filter "latest only"** semantic — `agent_thread_service.py` counts a thread as failed only if its most recent outbound attempt failed. Preserves the fix even if you touch list_threads.
- **Redis graceful degradation** — `events.publish()` swallows + resets cache on failure. `agent_poller` has a 60s health probe. Don't add new Redis usage without try/except + reset_redis on exception.
- **Test infrastructure exists.** Don't say "no tests yet" — there are 22 in `app/tests/`. Add to them.
- **Database backups** run nightly, weekly verify. Documented in `docs/backup-and-restore.md`. Take a manual backup before any destructive migration: `/srv/quantumpools/scripts/backup_db.sh`.

### Phase ordering — DO NOT skip ahead

Phase B is the load-bearing one because the orchestrator is the email path. The plan calls for a **50-email regression test fixture BEFORE Phase B ships** — anonymized real emails from production, run through both old and new code paths, asserting identical folder/tag/visibility outcomes. This is the safety net for the migration itself. Without it, Phase B can silently mis-route during cutover.

Build order:
1. Phase A (schema + Alembic) — pure additive, no code path changes
2. Build the 50-email regression fixture — `app/tests/test_inbox_rules_migration.py` or similar
3. Phase B (service + data migration + orchestrator wiring) — only after fixture green
4. Phase C (UI) — once Phase B has run clean for at least a few days
5. Phase D (delete old code) — wait at least 2 weeks of clean Phase B operation
6. Phase E (drop tables) — 30 days after Phase D

Take a backup before Phase B's data migration.

### Verify before declaring complete

For each phase, the "done" checklist:
- [ ] Tests written and passing (run `cd app && /home/brian/00_MyProjects/QuantumPools/venv/bin/pytest tests/ -W ignore::DeprecationWarning`)
- [ ] No org-isolation regressions (cross-org test in `test_org_isolation.py` passes)
- [ ] Doc updated (this file's status section + email-pipeline.md if behavior changed)
- [ ] Deployed via `/srv/quantumpools/scripts/deploy.sh` (never restart individual services)
- [ ] No 401s/500s in `journalctl -u quantumpools-backend` for at least 5 minutes
- [ ] If you touched anything email-related: send a test from external account → contact@sapphire-pools.com → confirm it lands

---

---

## Background — how we got here

Two suppression/routing systems were built in different sessions without coordination:

### `inbox_routing_rules` (`InboxRoutingRule` model) — older
- Fields: `address_pattern`, `match_type` (exact/contains), `match_field` (from/to), `action` (route/block), `category`, `required_permission`, `priority`, `is_active`
- Original purpose: route inbound mail to specific permission groups; block obvious noise (`noreply@`, `mailer-daemon@`)
- **Block action originally dropped emails entirely** — they never landed in the DB
- 41 block rules accumulated organically; some legit (`noreply@`), some destructive (`scppool.com`, `pool360.com`, `americanexpress.com`)
- **Patched 2026-04-13:** block now routes to Spam folder instead of dropping. Recoverable in All Mail.

### `suppressed_email_senders` (`SuppressedEmailSender` model) — newer
- Fields: `email_pattern` (exact or `*@domain`), `reason` (tag), `folder_id` (auto-route), `created_by`
- Built for: sender tagging (billing/vendor/notification/personal/etc.), folder routing per sender, suppressing the "Add Contact" prompt
- Used by: SenderTagChip (UI), orchestrator (folder routing on ingest), thread presenter (display tag)

### The overlap

Both match on sender pattern. Both can route to folders. Both have priority. Conceptually they're the same thing wearing different costumes.

### The incident

- `scppool.com` was added to `inbox_routing_rules` as a block at some point
- Block silently dropped every email from SCP Pool — your primary supply vendor
- `suppressed_email_senders` separately tagged some scppool addresses as "vendor" with a folder route — but only for emails that had already been ingested before the block was added
- Brian noticed missing emails, audit found 41 destructive blocks across the dual system
- Cleanup: 9 rules removed, block semantics changed to "route to Spam"

**Root cause:** two systems, no single source of truth, no audit trail of "where did this email go."

---

## Goal

A single `inbox_rules` table that handles all sender/recipient pattern matching. One UI. One service. One mental model. Backwards-compatible during migration via dual-write.

---

## Phase A: Design + new model (~1 day)

### Schema

```sql
CREATE TABLE inbox_rules (
  id              VARCHAR(36) PRIMARY KEY,
  organization_id VARCHAR(36) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  name            VARCHAR(200),  -- optional human label, e.g. "Stripe billing routing"
  priority        INTEGER NOT NULL DEFAULT 100,  -- lower = first
  conditions      JSONB NOT NULL,  -- array of {field, operator, value}, AND-joined
  actions         JSONB NOT NULL,  -- array of {type, params}
  is_active       BOOLEAN NOT NULL DEFAULT TRUE,
  created_by      VARCHAR(100),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_inbox_rules_org_active_priority ON inbox_rules (organization_id, is_active, priority);
```

### Conditions schema

```json
[
  { "field": "sender_email", "operator": "equals", "value": "system@entrata.com" },
  { "field": "subject", "operator": "contains", "value": "invoice" }
]
```

**Fields**: `sender_email` | `sender_domain` | `recipient_email` | `subject` | `category` | `customer_id` | `body`

**Operators**: `equals` | `contains` | `starts_with` | `ends_with` | `matches` (glob like `*@scppool.com`)

All conditions in a rule must match (AND). For OR logic, create multiple rules with the same actions.

### Actions schema

```json
[
  { "type": "assign_folder", "params": { "folder_id": "abc-123" } },
  { "type": "assign_tag", "params": { "tag": "billing" } },
  { "type": "suppress_contact_prompt" }
]
```

**Action types**:
- `assign_folder` — set thread's folder_id
- `assign_tag` — apply sender tag (billing/vendor/etc.)
- `assign_category` — set message category
- `set_visibility` — set thread's visibility_permission
- `suppress_contact_prompt` — never show "Add Contact" for this sender
- `route_to_spam` — force into Spam folder (replaces old `block` action)

A rule can have multiple actions. They apply in order.

---

## Phase B: New service + dual-write migration (~2 days)

### `InboxRulesService`

Single entry point in `app/src/services/inbox_rules_service.py`:

```python
class InboxRulesService:
    async def evaluate(self, message, thread, org_id) -> list[Action]:
        """Load all active rules for org, return matching actions in priority order."""

    async def apply(self, actions, thread, db):
        """Execute the actions on the thread (set folder_id, set tag, etc.)."""
```

### Data migration (Alembic data migration, not just schema)

```python
def upgrade():
    # Create inbox_rules table
    op.create_table(...)

    # Migrate inbox_routing_rules → inbox_rules
    op.execute("""
        INSERT INTO inbox_rules (id, organization_id, name, priority, conditions, actions, is_active, created_by, created_at, updated_at)
        SELECT
            gen_random_uuid()::text,
            organization_id,
            'Migrated from routing rule: ' || address_pattern,
            priority,
            jsonb_build_array(jsonb_build_object(
                'field', CASE match_field WHEN 'from' THEN 'sender_email' ELSE 'recipient_email' END,
                'operator', CASE match_type WHEN 'exact' THEN 'equals' ELSE 'contains' END,
                'value', address_pattern
            )),
            CASE action
                WHEN 'block' THEN jsonb_build_array(jsonb_build_object('type', 'route_to_spam'))
                WHEN 'route' THEN jsonb_build_array(
                    jsonb_build_object('type', 'assign_category', 'params', jsonb_build_object('category', category)),
                    jsonb_build_object('type', 'set_visibility', 'params', jsonb_build_object('permission_slug', required_permission))
                )
            END,
            is_active,
            'migration',
            now(),
            now()
        FROM inbox_routing_rules;
    """)

    # Migrate suppressed_email_senders → inbox_rules
    op.execute("""
        INSERT INTO inbox_rules (id, organization_id, name, priority, conditions, actions, is_active, created_by, created_at, updated_at)
        SELECT
            gen_random_uuid()::text,
            organization_id,
            'Migrated tag: ' || email_pattern,
            200,  -- lower priority than routing rules
            jsonb_build_array(jsonb_build_object(
                'field', CASE WHEN email_pattern LIKE '*@%' THEN 'sender_domain' ELSE 'sender_email' END,
                'operator', CASE WHEN email_pattern LIKE '*@%' THEN 'matches' ELSE 'equals' END,
                'value', email_pattern
            )),
            (
              jsonb_build_array(jsonb_build_object('type', 'suppress_contact_prompt'))
              || (CASE WHEN reason IS NOT NULL THEN jsonb_build_array(jsonb_build_object('type', 'assign_tag', 'params', jsonb_build_object('tag', reason))) ELSE '[]'::jsonb END)
              || (CASE WHEN folder_id IS NOT NULL THEN jsonb_build_array(jsonb_build_object('type', 'assign_folder', 'params', jsonb_build_object('folder_id', folder_id))) ELSE '[]'::jsonb END)
            ),
            true,
            COALESCE(created_by, 'migration'),
            created_at,
            now()
        FROM suppressed_email_senders;
    """)
```

### Wire orchestrator

Replace these three call sites with one:
- `check_sender_blocked` (orchestrator + inbound_email_service)
- `match_routing_rule` (orchestrator)
- sender_tag lookup (thread_presenter)

All become: `await InboxRulesService(db).evaluate(message, thread, org_id)`.

### Keep old tables read-only

For 1 week post-deployment:
- Old tables remain (no DROP)
- Old code paths still callable (commented but not deleted)
- Feature flag `INBOX_RULES_USE_NEW_SYSTEM` allows instant rollback
- Both systems write to their respective tables; only new system is read

---

## Phase C: Unified UI (~2-3 days)

**Replace:**
- Settings → Inbox Settings sheet → `InboxRoutingSection` (old)
- `SenderTagChip` quick-retag dropdown (old)
- ContactLearningPrompt → Tag Sender dialog (old)

**With one page: Settings → Inbox Rules**

Layout:
- Single table of all rules: priority | name | conditions | actions | active toggle | edit | delete
- "Add Rule" button → editor dialog
- Search/filter: find rules matching a sender or pattern
- Test button: pick a thread, dry-run a rule, see what would change

Editor dialog:
- Name field
- Priority field
- Conditions builder (add/remove rows: field dropdown + operator dropdown + value input)
- Actions builder (multi-select with per-action config)
- Test button (pick a thread → "this rule would: assign folder X, assign tag Y")
- Save / Cancel

**Migration banner** in old Settings → Inbox Settings sheet:
> "Inbox rules have moved! All your routing and tag rules are now in one place: [Settings → Inbox Rules](/settings/inbox-rules)"

**SenderTagChip** still works as a quick action — but writes via new InboxRulesService instead of dismiss-contact-prompt endpoint.

---

## Phase D: Code deprecation (~1 day)

1. Remove `check_sender_blocked` calls from `inbound_email_service.py` and `orchestrator.py`
2. Remove `match_routing_rule` calls from `orchestrator.py`
3. Remove sender_tag lookup from `orchestrator.py` and `thread_presenter.py`
4. Old `InboxRoutingSection` deleted
5. Old `dismiss-contact-prompt` endpoint → either delete or just have it call the new service
6. Tables remain for safety (DROP in Phase E)

---

## Phase E: Drop old tables (~1 day, ~30 days post-deployment)

1. Verify no code references `inbox_routing_rules` or `suppressed_email_senders` (grep + run a CI check)
2. Verify all data has been migrated (count rows in old vs. expected migrated rules)
3. Final sanity check: process a test email — confirm right folder/tag/visibility
4. Drop both tables in a migration
5. Drop this doc and CLAUDE.md index entry

---

## Risk Mitigations

**Critical: orchestrator is the email path. Bugs hide actual emails.**

1. **Test harness before Phase B ships**: build a test fixture of 50 sample emails (real cases from the DB anonymized). Run them through both old + new code paths. Assert identical folder/tag/visibility outcomes for every email. This becomes a regression test.

2. **All Mail folder is the universal safety net** (already shipped). Even if a rule misfires, blocked/hidden emails are findable.

3. **Dual-write during transition**: write to both systems, but only read from new. If new path breaks, flip the feature flag back to old.

4. **Migration is reversible**: keep old tables intact until Phase E. If anything goes wrong in Phase B-D, revert to old code paths.

5. **Audit log**: every rule application should log which rule fired and what actions it applied. Add `inbox_rule_applications` table or use existing `agent_messages.notes` field. Future debugging asks "why did this email go to spam?" → look at the log.

---

## Lessons baked in

From the scppool incident:

1. **Never drop emails as a side effect.** Hard delete only via explicit user action with a confirmation dialog.
2. **One source of truth per concept.** No "two tables that both kinda manage senders."
3. **Audit trail is mandatory.** Every routing decision should be reviewable.
4. **All Mail is sacred.** No code path may hide an email from All Mail.
5. **When in doubt, route to Spam folder, not delete.** Spam is recoverable. Drop is forever.

These rules apply to ANY future inbox/routing work.
