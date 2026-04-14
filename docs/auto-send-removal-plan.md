# Auto-Send Removal Plan

> **Priority:** HIGH (do before onboarding any non-Sapphire customer). **Effort:** ~half day. **Status:** Not started, planned 2026-04-14.
>
> **Removal note:** Delete this doc once Phase 5 ships and `feedback_no_auto_send.md` memory is in place.

## Why

QuantumPools currently has an auto-send feature: when the AI classifier returns high confidence and `Organization.email_auto_send_enabled=True`, the orchestrator sends the AI's draft directly to the customer without human approval. Brian explicitly rejected this product direction on 2026-04-14.

**The argument:**
- Even acknowledgments ("Got it, thanks") imply a human read the email. We don't actually know that. The customer goes quiet thinking we're handling it; nothing happens; relationship damages.
- Substantive replies (scheduling confirmations, billing answers) are liability vectors. AI saying "we'll be there Tuesday" when the route is full → contractual exposure for the org owner.
- A SaaS subscriber running a 2-person shop doesn't have time to monitor what the AI auto-sent. The "Auto-Sent review banner" we built creates a NEW review queue, which is the opposite of less-work.
- If we onboard another QP customer with this feature on, an over-eager auto-send to one of THEIR customers is a churn event waiting to happen.

**The replacement:** AI drafts every reply (the actual time-saver); humans always send. One-click approve from the timeline.

## What stays

This plan is not "AI is dumb, kill it." Most of the AI infrastructure stays:

- ✅ **AI draft generation** for every inbound — `classifier.classify_and_draft()` keeps running, populates `AgentMessage.draft_response`
- ✅ **One-click approve** flow via the timeline / `thread_action_service.approve_thread`
- ✅ **AgentLearningService** continues recording edits + acceptances when humans modify drafts before sending. With auto-send gone, ALL training signal comes from human edits — cleaner corpus, no auto-sent acceptances polluting it.
- ✅ **Auto-Handled review loop** — DIFFERENT system. That's about the AI hiding noise (spam, vendor automated mail, classified `no_response`) FROM the Inbox. It doesn't send anything. Stays.
- ✅ **Classifier outputs** — category, urgency, customer matching, suggested actions. All stay.

## What gets deleted

| # | Component | File:line / location |
|---|---|---|
| 1 | Orchestrator auto-send branch | `app/src/services/agents/orchestrator.py` — the `else: # Auto-send` block (was hardened in d671d82, now goes away entirely) |
| 2 | Commitment phrase guard | `app/src/services/agents/classifier.py` (search "commitment_phrase" / "follow up", "get back", "look into") — was a safety net for auto-send only |
| 3 | First-contact auto-send ntfy | inside the orchestrator auto-send block |
| 4 | `Organization.email_auto_send_enabled` column | Alembic migration: drop column |
| 5 | Settings UI: Auto-Reply Safety toggle card | `frontend/src/app/(dashboard)/settings/email/page.tsx` (search "Auto-Reply Safety", "auto-send") |
| 6 | Inbox Auto-Sent filter chip | `frontend/src/components/inbox/inbox-filters.tsx` |
| 7 | Auto-Sent review banner (Yes/No) | `frontend/src/components/inbox/thread-detail-sheet.tsx` (`AutoSentFeedbackBanner` component) |
| 8 | Backend `auto-sent-feedback` endpoint | `app/src/api/v1/admin_threads.py` |
| 9 | Stats `auto_sent` count | `app/src/services/agent_thread_service.py` `get_thread_stats` — drop the field |
| 10 | Failed filter `status='auto_sent'` reference (in latest_outbound subquery) | `app/src/services/agent_thread_service.py` — irrelevant after, but harmless to keep |
| 11 | Weekly auto-sent digest cron | `app/app.py` `_send_auto_sent_digest` + scheduler.add_job |
| 12 | `email/auto-sent` permission slug if any exists | grep |
| 13 | `email_auto_send_enabled` references in docs | `docs/email-pipeline.md`, `CLAUDE.md` Phase 5b line |

## What stays as historical truth (do NOT delete)

- `AgentMessage.status = 'auto_sent'` enum value — past auto-sent messages exist in DB, keep the value so they render correctly. New messages will never get this status.
- The `is_auto_handled` derived flag and Auto-Handled filter — that's about the orchestrator HIDING noise, not auto-sending. Different concept, both confusingly use the prefix "auto."

## Phase order (safe deletion sequence)

Order matters: kill the dangerous code path FIRST (the actual safety risk), then clean up dead UI and DB schema after.

### Phase 1: Disable the auto-send code path (~30 min)

**Why first:** this is the actual safety hole. Until this is gone, any future Claude session who flips `email_auto_send_enabled=True` on an org accidentally restarts auto-sending.

- Replace the `else: # Auto-send` block in orchestrator with `# Auto-send removed 2026-04-14 — see docs/auto-send-removal-plan.md` and the inbound message just stays in `pending` for human approval (same as `needs_approval=True` path)
- Delete the commitment phrase guard (now dead code)
- Delete the first-contact auto-send ntfy
- Add a test: assert that an inbound classified as auto-sendable still ends up `pending`, no outbound row created

Verify: send a test email that historically would have auto-sent. Confirm it lands in inbox `pending` instead.

### Phase 2: Delete backend dead code (~30 min)

- Delete `_send_auto_sent_digest` function in `app/app.py` + remove the `scheduler.add_job` line
- Delete `auto-sent-feedback` endpoint in `admin_threads.py`
- Drop the `auto_sent` count from `get_thread_stats` return dict (frontend will tolerate missing key)
- Drop `commitment_phrase_guard` calls from classifier if any caller exists outside the deleted auto-send block

### Phase 3: Frontend cleanup (~1 hour)

- Delete `AutoSentFeedbackBanner` component in `thread-detail-sheet.tsx` + the conditional render that uses `thread.has_auto_sent`
- Delete the Auto-Sent filter pill in `inbox-filters.tsx`
- Delete the `autoSentFilter` state + related logic in `inbox/page.tsx`
- Delete the "Auto-Reply Safety" card in `settings/email/page.tsx`
- Delete the `Auto-Sent` chip on outbound messages (or repurpose for delivery status only — check current usage)
- TypeScript types: remove `auto_sent` from stats interface, `has_auto_sent` from Thread type if unused after these deletions
- Run `npx tsc --noEmit` to catch references

### Phase 4: DB migration (~15 min)

After backend stops reading it (Phases 1+2), drop the column:

```python
# alembic migration
def upgrade():
    op.drop_column('organizations', 'email_auto_send_enabled')

def downgrade():
    op.add_column('organizations', sa.Column('email_auto_send_enabled', sa.Boolean(), nullable=False, server_default='false'))
```

Take a backup first via `/srv/quantumpools/scripts/backup_db.sh` (per CLAUDE.md backups discipline).

### Phase 5: Docs + memory (~30 min)

- Update `docs/email-pipeline.md`: remove "Auto-send monitoring" section; replace with one line stating QP does not auto-send and why
- Update `CLAUDE.md` Phase 5b line: drop "auto-sent monitoring + weekly digest" from the bullet list
- Update `docs/realtime-events.md` if the auto-sent feedback endpoint was referenced
- Add memory entry `~/.claude/projects/-srv-quantumpools/memory/feedback_no_auto_send.md` with the rationale (text in the next section)
- Add the new memory entry to `MEMORY.md` index under "Architecture Rules"
- Delete THIS plan doc + remove from CLAUDE.md Documentation Index

## Memory entry text (for `feedback_no_auto_send.md`)

```markdown
---
name: AI drafts every customer reply; humans always send. No auto-send.
description: Auto-sending customer email was explored and explicitly rejected. AI generates drafts; one-click approve from the timeline. Do not propose adding auto-send back.
type: feedback
---

QuantumPools does NOT auto-send customer email under any circumstances. Even
acknowledgments. Even "you're welcome." Auto-send was implemented in 2026-04
with safety nets (org flag, commitment phrase guard, review banners,
first-contact ntfy) and removed 2026-04-14 because:

1. Even basic acknowledgments imply false human engagement. "Got it, thanks"
   sent by an AI makes the customer believe a person saw and is handling their
   message. They go quiet expecting follow-through that doesn't happen.
2. Substantive AI replies are liability vectors — "we'll be there Tuesday"
   when the route is full creates contractual exposure for the org owner.
3. The "review what the AI auto-sent" workflow we built created MORE work,
   not less. Opposite of the less-work pillar.
4. For SaaS subscribers we don't directly oversee, an over-eager auto-send
   to their customer is a churn event.

The actual time-saver is AI DRAFTING every reply — typing is the cost.
Owner reads the draft, edits if needed (the edit is the training signal
for AgentLearningService), clicks Approve. One click vs. composing from
scratch.

**How to apply:**
- If you find yourself proposing "we should auto-send X because it's safe"
  — stop. The decision is made. Re-litigating costs cycles.
- AI-drafted-then-human-approved IS the workflow. Make that path faster /
  better instead of bypassing it.
- The Auto-Handled review loop (AI hiding noise from Inbox without sending)
  is a DIFFERENT system and stays. Don't confuse "auto-handled" (hide email)
  with "auto-sent" (reply to email). Only the latter is rejected.
```

## Verification checklist (per phase)

- [ ] Run `cd app && /home/brian/00_MyProjects/QuantumPools/venv/bin/pytest tests/ -W ignore::DeprecationWarning` — all tests pass
- [ ] Frontend type-check: `cd frontend && npx tsc --noEmit` — clean
- [ ] Deploy via `/srv/quantumpools/scripts/deploy.sh`
- [ ] No 500s / 401s in `journalctl -u quantumpools-backend --since "5 minutes ago"`
- [ ] Send a test inbound email that previously auto-sent (e.g., simple "thanks") → confirm it lands in inbox `pending` with a draft, NOT sent automatically
- [ ] DB migration applied successfully (after Phase 4)
- [ ] Memory entry exists at `~/.claude/projects/-srv-quantumpools/memory/feedback_no_auto_send.md` and is indexed in MEMORY.md

## Risks

**Low overall.** This is a pure feature removal — no new code paths, no new schema, fewer external integrations. Risk surface:

| Risk | Mitigation |
|---|---|
| An existing thread with `has_auto_sent=True` breaks the UI when AutoSentFeedbackBanner is removed | Conditional render guard already exists; remove banner cleanly without breaking thread detail |
| Stats endpoint missing `auto_sent` field crashes frontend | Frontend already uses optional access (`stats.auto_sent ?? 0`) — verify but should be fine |
| Org currently has `email_auto_send_enabled=True` and someone expects auto-send tomorrow | Brian is the only org owner; confirm no surprise. Currently `False` per recent audit. |
| Future Claude session "improves" auto-send back into existence | Memory entry + this plan's explicit rationale prevents that |

## Order to start

If picking this up cold, work top-to-bottom through the phases. Don't skip ahead — the order is deliberate (kill dangerous code FIRST, clean up dead code AFTER, drop DB schema LAST). Phase 1 alone removes the actual safety risk; everything else is hygiene.
