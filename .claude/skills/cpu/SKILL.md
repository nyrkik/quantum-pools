---
name: cpu
description: Commit, push, and update docs — use after any code changes to keep docs aligned
user_invocable: true
---

Commit, push, and update documentation. Run all three steps in order.

## Step 1: Commit & Push

1. Run `git status` and `git diff --stat` to see all changes.
2. Draft a concise commit message following the repo's style (see `git log --oneline -5`). Summarize the "why" in 1-2 sentences, then bullet the key changes.
3. Stage the relevant files (not .env, credentials, or large binaries). Commit and push to origin.

## Step 2: Review Docs Against Changes

Read the diff from this commit (`git diff HEAD~1 --name-only` to get changed files, then `git diff HEAD~1` for the actual changes). For each changed area, check whether any of these docs need updating:

| Doc | What it covers | Update when... |
|-----|---------------|----------------|
| `CLAUDE.md` | Architecture, conventions, phase status, key relationships | New models, new services, new conventions, phase completion |
| `docs/email-pipeline.md` | Inbound/outbound email flow, agent pipeline | Changes to agents/, email_service, orchestrator, thread management |
| `docs/realtime-events.md` | WebSocket + Redis event system | New EventTypes, new publish() calls, frontend hook changes |
| `docs/data-model.md` | All models organized by domain | New models, new relationships, schema changes, migrations |
| `docs/deepblue-architecture.md` | DeepBlue AI system | Changes to deepblue/, new tools, eval changes |
| `docs/ai-agents-plan.md` | 10 planned agents + implementation status | Agent status changes, new agent capabilities built |
| `docs/build-plan.md` | Phase roadmap with completion status | Phase items completed, new phases started |
| `docs/competitive-research.md` | Market analysis + differentiator status | New differentiators built, status changes |
| `docs/profitability-feature-plan.md` | Profitability system design reference | Changes to profitability calculations, scoring, jurisdictions |

## Step 3: Update Docs

For each doc that needs changes:
1. Read the current doc
2. Make **targeted edits** — don't rewrite sections that are still accurate
3. For CLAUDE.md: update phase status, key relationships, architecture table, or dev notes as needed
4. For system docs: update component descriptions, add new components, fix inaccurate claims

If docs were updated, make a second commit:
- Message: `docs: update [doc names] to reflect [what changed]`
- Push again

## Rules
- Do NOT add new docs unless a major new system was introduced (new service subdirectory, new frontend provider, new infrastructure component)
- Do NOT rewrite docs that are still accurate — only edit what changed
- If nothing needs updating, say so and skip Step 3
- Always verify claims against actual code before writing them into docs
