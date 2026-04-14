# Inbox/Email Subsystem Security Audit — 2026-04-13

> **Status:** Audit complete, fixes IN PROGRESS. Each fix updates this doc with date + commit SHA when shipped.
>
> **Removal note:** Delete this doc when every CRITICAL/HIGH item is closed AND a follow-up audit confirms no regression.

## Context

Audit triggered by a session pattern where bugs were found one at a time as they bit Brian (FB-24 silent send failures, 30-hour Gmail blackout, etc.). After hardening the obvious paths, ran a security/org-isolation audit from a different angle to find latent issues.

Audit was run by an Explore subagent reading every email-related router/service end to end. Findings below are file:line specific and reproduced by reading the code directly — not speculation.

## CRITICAL findings (real cross-org/auth bugs, must fix immediately)

### C1. Customer lookup without org filter — compose path
- **File:** `app/src/services/email_compose_service.py:79-81`
- **Bug:** `select(Customer).where(Customer.id == customer_id)` has no `Customer.organization_id == org_id` predicate.
- **Impact:** An authenticated user in org A can pass a `customer_id` belonging to org B in the compose payload and the resulting email gets the wrong org's customer name/property/contact data attached. Cross-tenant data leak via composed email content.
- **Fix:** Add `Customer.organization_id == org_id` to the where clause. Also re-check the `Property` lookup right after (line 84-86) — same pattern.
- **Status:** PENDING

### C2. Case unlink — cross-org mutation by ID
- **File:** `app/src/api/v1/cases.py:411,415`
- **Bug:** Case unlink endpoint fetches AgentAction (line 411) and AgentThread (line 415) by ID alone. The case lookup IS org-filtered, but the entity being unlinked is not.
- **Impact:** An authenticated user can unlink any thread or action from any org's case, by ID. Mutation across tenants.
- **Fix:** Add `organization_id == ctx.organization_id` to both fetches.
- **Status:** PENDING

### C3. Postmark webhook — zero signature validation
- **File:** `app/src/api/v1/admin_webhooks.py:15-70`
- **Bug:** The endpoint accepts any unauthenticated POST and writes to `AgentMessage.delivery_status`, `delivery_error`, `open_count`, `first_opened_at`. No HMAC check, no shared-secret in URL, no source-IP allowlist.
- **Impact:** Anyone on the internet who guesses the URL can mark every outbound email in the DB as `bounced` with a script. Or fake "Delivered/Opened" events. Or trigger spam-complaint cascades.
- **Fix:** Validate the request signature using Postmark's HMAC-SHA256 + a shared `POSTMARK_WEBHOOK_SECRET` env var. Reject anything that doesn't match. (Postmark sends the signature in the `X-Postmark-Signature` header.)
- **Status:** PENDING

## HIGH findings

### H1. Customer lookup without org filter — admin draft-followup path
- **File:** `app/src/api/v1/admin_messages.py:402-406`
- **Bug:** Same C1 pattern in the AI-drafted-followup endpoint.
- **Impact:** AI drafts referencing the wrong org's customer record.
- **Fix:** Add `Customer.organization_id == ctx.organization_id`.
- **Status:** PENDING

### H2. Unauthenticated attachment downloads
- **File:** `app/app.py` — `app.mount("/uploads", StaticFiles(...))`
- **Bug:** `/uploads/attachments/{org_id}/{stored_filename}` is served with no auth. Filenames are UUIDs but they're returned to clients in API responses, so they're discoverable.
- **Impact:** Anyone with a URL gets the file. Customer photos, PDFs, contracts, anything emailed in.
- **Fix:** Replace the static mount with an authenticated FastAPI endpoint `/api/v1/attachments/{id}` that:
  - Looks up MessageAttachment by id
  - Verifies `attachment.organization_id == ctx.organization_id`
  - Streams the file from disk
- Update every URL builder to point at the new endpoint instead of `/uploads/attachments/...`.
- **Status:** PENDING

### H3. Inbound email webhook — no signature validation
- **File:** `app/src/api/v1/inbound_email.py:21-72`
- **Bug:** Same as C3 — no Postmark signature check on the inbound webhook either. The `org_slug` is taken from the URL with no proof the request is legitimate.
- **Impact:** Network-adjacent attacker can inject forged inbound emails into any org's inbox.
- **Fix:** Same HMAC validation as C3, on this endpoint too.
- **Status:** PENDING

### H4. Status webhook handler — no org filter
- **File:** `app/src/services/inbound_email_service.py:146-149`
- **Bug:** `select(AgentMessage).where(AgentMessage.postmark_message_id == message_id)` — no org_id constraint.
- **Impact:** Defense-in-depth gap. With C3 fixed this is less exploitable, but the principle still violates least-privilege.
- **Fix:** The status webhook payload includes the recipient address — derive org_id from there, add to the where clause.
- **Status:** PENDING

## MEDIUM findings

### M1. Email bodies in logs (PII)
- **File:** `app/src/services/agents/orchestrator.py:212, 262-268, 287`
- **Bug:** Full subjects + 200-char body snippets are logged. Bodies routinely contain customer names, addresses, billing info.
- **Fix:** Log message ID + first 50 chars of subject only. Bodies never.
- **Status:** PENDING

### M2. Raw exception text returned to client
- **File:** `app/src/services/email_compose_service.py:223-232`
- **Bug:** The FB-24 hardening returns `f"{type(exc).__name__}: {exc}"` to the client. Exposes internal types and stack info.
- **Fix:** Log the full exception server-side, return a generic "Send failed" + a stable error code to the client. Keep the actual reason in `delivery_error` (visible only via authenticated thread detail).
- **Status:** PENDING

### M3. Bulk thread ops — verify org filter
- **File:** `app/src/api/v1/admin_threads.py:750+` (mark-read, mark-unread, move, spam, not-spam)
- **Bug:** Audit flagged but didn't confirm. Bulk operations accept `thread_ids: list[str]` — need to verify the service layer filters every ID by `organization_id`.
- **Fix:** Read each handler, add `organization_id` constraint to bulk update queries if missing.
- **Status:** PENDING

### M4. No per-org rate limiting on webhooks
- **File:** `app/src/api/v1/admin_webhooks.py`, `app/src/api/v1/inbound_email.py`
- **Bug:** Webhook endpoints have a global rate limit but not per-org. An attacker could DoS one org's webhook handling.
- **Fix:** Add per-org rate limiter (counter keyed on `org_slug` derived from payload).
- **Status:** PENDING

## Operational gaps (separate from this audit, tracked here for visibility)

- **No tests anywhere.** Every fix this session relies on manual verification.
- **Redis dependency.** Backend uses Redis for WS pubsub; no graceful degradation if Redis dies (frontend has fallback polling, backend doesn't).
- **No backup verification.** DB backup strategy unverified — never tested a restore.

These are NOT inbox-security items but they showed up adjacent to the audit. Track separately if they become work items.

## Execution order

1. **C3** first — public-internet exposure, smallest diff (validate signature + reject), no UX impact.
2. **C1, C2, H1** — straightforward `where` clause additions.
3. **H4** — small follow-on to C3.
4. **H2** — bigger change (new endpoint + URL builder updates) but architecturally important. Touches multiple places.
5. **H3** — same fix shape as C3.
6. **M1, M2** — log scrub + error-message redaction.
7. **M3** — verify + tighten bulk ops.
8. **M4** — per-org rate limiting (smaller surface, do last).

Each fix gets its own commit with `security:` prefix. This doc is updated with the date + commit SHA when each item ships.

## Why we wrote this down

If this session ends mid-execution (compaction, disconnect, restart), the next Claude session needs to pick up exactly where this one left off without re-running the audit. This doc + the CLAUDE.md index entry + the task list together provide three independent recovery paths.
