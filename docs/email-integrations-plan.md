# Email Integrations — Implementation Plan

This is the detailed build plan to support multiple email integration modes per organization. See `email-strategy.md` for the high-level vision.

## Current state (as of 2026-04-10)

- **Sapphire Pools**: managed mode (Cloudflare Workers + Postmark). Working but lacks spam filtering.
- **Architecture**: provider-agnostic webhook ingestion already exists. `AgentMessage` model is source-agnostic. Permission-based visibility already works.
- **Outbound**: Postmark only, no SMTP fallback. Per-org sender via `agent_from_email`.
- **Monitoring**: Sentry + ntfy alerts on failures.

## Phase 0: Sapphire Hybrid (immediate, no code)

**Goal:** Get Gmail's spam filtering back for Sapphire Pools without breaking the current architecture.

**Approach:** Cloudflare Email Routing currently sends emails directly to our Worker. We change it to forward to BOTH `sapphpools@gmail.com` AND our Worker. Brian/team uses Gmail as their email client (mobile, search, spam filtering), and the QP app continues to ingest emails for AI processing and case linking.

**Tradeoffs:**
- Pro: Gmail's spam filtering, mobile apps, search, calendar — all back
- Pro: Zero code changes, ~10 minutes of config
- Pro: QP app still gets every email for AI processing
- Con: Two-way sync doesn't work — marking read in Gmail doesn't mark read in QP
- Con: Replies sent from Gmail bypass QP's outbound logic, signature, tracking
- Con: Replies sent from QP don't appear in Gmail's Sent folder

**Implementation:**
1. Cloudflare → Email Routing → Routing rules
2. For each rule (`contact@`, `brian@`, `kim@`, `chance@`, catch-all):
   - Add a second action: "Send to email" → `sapphpools@gmail.com`
   - Keep the existing "Send to worker" action
3. Verify by sending a test email — should arrive in both Gmail AND the QP inbox
4. Done

**OR** alternative without changing routing rules: have the Worker itself forward to Gmail after POSTing to webhook. Slightly more complex but keeps routing config simple.

## Phase 1: EmailIntegration foundation (1 week)

**Goal:** Add the `EmailIntegration` model and refactor existing code to use it. Lays the groundwork for Gmail/MS modes without changing user-visible behavior.

**Backend:**
- New model: `EmailIntegration`
  ```
  organization_id (FK)
  type (managed | gmail_api | ms_graph | forwarding | manual)
  status (connected | disconnected | error | setup_required)
  config (JSONB) — OAuth tokens, refresh tokens, forwarding address, etc.
  inbound_sender_address (the address users send TO — e.g., contact@sapphire-pools.com)
  outbound_provider (postmark | gmail_api | ms_graph)
  last_sync_at (timestamp)
  last_error (text)
  created_at, updated_at
  ```
- Refactor `EmailService.send_agent_reply()` to dispatch based on org's `outbound_provider`
- Refactor `inbound_email_service.py` to read org's integration mode (currently it's hardcoded)
- Migration: backfill `EmailIntegration` records for existing orgs (Sapphire Pools = managed)
- Encrypt `config` field at rest (for OAuth tokens)
- Admin UI: read-only view of current integration in Settings → Email

**Frontend:**
- Settings → Email page showing current integration mode
- "Disconnected" state with re-connect button
- Read-only for now — selection happens in Phase 2

## Phase 2: Gmail API integration (2 weeks)

**Goal:** Add Gmail mode. Org owners can connect their Gmail account, all email syncs into QP automatically, two-way actions work.

**Backend:**
- Google Cloud project setup (OAuth credentials, Pub/Sub topic)
- OAuth flow: `/v1/email-integrations/gmail/authorize` → redirect → callback → store tokens
- Initial sync service: `GmailSyncService.initial_sync(org_id, days=30)`
  - Fetch message list via `users.messages.list()`
  - For each message, fetch full content via `users.messages.get()`
  - Create `AgentMessage` records
  - Run normal pipeline (customer matching, threading, classification)
- Real-time push: Gmail Pub/Sub → our Pub/Sub subscriber endpoint → fetch and process
- Two-way write methods:
  - `mark_read(message_id)` → API call
  - `mark_unread(message_id)` → API call
  - `add_label(message_id, label)` → API call
  - `move_to_trash(message_id)` → API call
  - `send_reply(thread_id, body)` → API call (sends as the user, appears in their Sent folder)
- Token refresh handler (Gmail tokens expire)
- New parser: `_parse_gmail_api()` in `inbound_email_service.py`
- Outbound dispatch: `EmailService.send_agent_reply()` checks org integration, sends via Gmail API for Gmail-mode orgs
- Health check: monitor token validity, Pub/Sub subscription health

**Frontend:**
- Settings → Email → "Connect Gmail" button
- OAuth consent flow (browser redirect)
- Connection status display (connected as `user@domain.com`, last sync at)
- Disconnect button
- Initial sync progress indicator

**OAuth scopes:**
- `gmail.modify` (read, write labels, send) — required
- We do NOT request `gmail.metadata` (full body access required for AI)
- Privacy policy must be clear: we read all email to provide customer intelligence

**Estimated timeline:** 1 week backend, 1 week frontend + testing

## Phase 3: Inbox UI redesign — full email client (2-3 weeks)

**Goal:** Make the inbox a real email client UX, not just an AI triage queue. Users in Gmail mode (or any mode) get a full email management experience.

**Features (from email client expectations):**
- Folder/label sidebar (Inbox, Sent, Drafts, Trash, Spam, custom labels)
- Multi-select with bulk actions (mark read, archive, delete, label)
- Threaded conversation view with proper indentation
- Reply, Reply All, Forward
- Compose new email to anyone (not just customers)
- Drafts auto-save, sync to Gmail in Gmail mode
- Attachments (view, download, send)
- Search bar with filters (from:, to:, has:, date ranges)
- Unread badge per folder
- Keyboard shortcuts (j/k for next/prev, e for archive, etc.)
- Scheduled send
- Snooze
- Mark important / star

**Two UI modes (user preference, per-account):**

**Mode A — Full email client:**
- Show ALL emails, not just customer-related
- Standard folders, labels, all features
- Customer context shown alongside customer-matched emails (sidebar panel)

**Mode B — Customer-focused inbox (current behavior):**
- Show only customer-related threads
- Action buttons: Create Job, Link Case, Reply
- Less clutter, focused on customer ops

Toggle in Settings → Inbox. Same data model, different filter and UI density.

**Backend changes:**
- Endpoints for label management
- Bulk action endpoints
- Search endpoint with full-text + filters
- Draft endpoints
- Attachment storage and serving (already partially exists)

**Estimated timeline:** 2-3 weeks for polished version

## Phase 4: Microsoft Graph (Outlook) integration (1-2 weeks)

**Goal:** Same as Phase 2 but for Outlook / Microsoft 365.

**Approach:** Mirror Gmail integration with MS Graph API. Same data flow, same `EmailIntegration` model, just a different OAuth provider and API.

**Estimated timeline:** Roughly the same as Gmail (most of the work transfers), maybe 1.5 weeks

## Phase 5: Forwarding mode polish (1 week)

**Goal:** Make forwarding mode setup self-service for orgs that want to use it.

**Backend:**
- Generate unique inbound subdomain per org: `org-{slug}@inbound.quantumpoolspro.com`
- Set up wildcard MX for `inbound.quantumpoolspro.com` → Cloudflare Email Routing
- Single Cloudflare Worker handles all `inbound.quantumpoolspro.com` mail, looks up org by recipient address
- Resend instructions email with the forwarding address

**Frontend:**
- Settings → Email → "Use Forwarding" → shows the unique address with copy button
- Step-by-step instructions for setting up forwarding in Gmail, Outlook, Zoho, generic

**Estimated timeline:** ~1 week (most plumbing exists)

## Phase 6: Onboarding wizard (1 week)

**Goal:** New orgs go through a smooth wizard to pick their email mode during signup.

**Wizard steps:**
1. "How do you handle email?"
   - Gmail / Google Workspace
   - Outlook / Microsoft 365
   - Other (forwarding mode)
   - We don't have business email yet (managed mode upsell)
   - Skip for now (manual mode)
2. Mode-specific setup:
   - Gmail/MS: OAuth flow
   - Other: forwarding instructions
   - Managed: domain verification + DNS setup wizard
3. Initial sync (if applicable)
4. Test email
5. Done

**Estimated timeline:** ~1 week

## Phase 7: Per-domain Postmark sender verification (1 week)

**Goal:** For orgs in forwarding/managed modes, send via their own domain (not ours), verified through Postmark.

**Backend:**
- Postmark Account API (need account-level token from Brian)
- Add domain → Postmark returns DKIM/Return-Path records
- Display them to user with copy buttons
- Verify button → calls Postmark API to check status
- Once verified, store domain on `EmailIntegration.config` and use for outbound

**Frontend:**
- Settings → Email → "Send From Your Domain" wizard

## Phase 8: Compliance & security (ongoing, 2 weeks total)

- Encrypt OAuth tokens at rest (Fernet or KMS)
- Audit logging of email access (who viewed what when)
- GDPR data export for emails
- GDPR data deletion (delete all emails for an org / customer)
- Privacy policy update
- Security review of OAuth scopes
- Rate limiting on email API calls
- Monitoring for abnormal access patterns

## Cross-cutting concerns

### Search
- **Managed mode**: Postgres FTS on `agent_messages.body` + `subject`
- **Gmail/MS mode**: forward search to Gmail/MS Graph API for native search performance
- **Mixed**: search both DB and API, merge results

### Attachments
- **Managed mode**: store in S3/local disk on inbound, serve from same
- **Gmail/MS mode**: lazy fetch from API on demand, cache locally
- **Outbound**: stored in `message_attachments` table, sent via API or Postmark

### Threading
- **All modes**: use `In-Reply-To` and `References` headers (RFC 5322)
- **Gmail mode**: also use Gmail thread ID as authoritative
- **Cross-mode**: same conversation across multiple addresses → AI matching to merge into one thread (already partially built)

### Read state
- **Managed mode**: stored locally in `thread_reads` per user
- **Gmail/MS mode**: synced bidirectionally with provider
- **Conflict resolution**: last-write-wins

### Notifications
- **Email arrival**: WebSocket push to UI (already built)
- **Mobile push**: ntfy (already built for alerts) — extend to user notifications
- **Per-user settings**: notification on every email vs only assigned vs only mentioned

### Multi-account support
- Some orgs have multiple Gmail accounts (e.g., contact@ and accounting@ as separate accounts, not aliases)
- `EmailIntegration` should support multiple per org, each with its own OAuth tokens
- UI: "Add another email account" in settings

## Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| OAuth tokens revoked / expired | Refresh flow + monitoring + UI prompt to reconnect |
| Gmail API rate limits | Exponential backoff + batch operations + Pub/Sub instead of polling |
| Email volume exceeds Postmark plan | Monitoring + alerts at 80% of plan limit |
| Spam getting through (managed mode) | Add SpamAssassin or AI-based filter as Worker stage |
| Sender domain reputation damaged | Per-domain Postmark accounts, monitoring DMARC reports |
| User accidentally disconnects integration | Confirmation dialog, ability to reconnect, no data loss |
| Multi-tenant data leakage | Strict org_id filtering on every query, integration tests |
| Customer confusion about which mode they're on | Clear labeling in settings, tooltips explaining differences |

## Things easy to overlook

- **Vacation auto-responder** — only matters in managed mode (Gmail/MS handle their own)
- **Mailing list / unsubscribe** — Postmark handles List-Unsubscribe headers for outbound
- **Customer portal email** — separate concern; replies from customer portal threads should still flow through normal pipeline
- **Email signatures** — per-org and per-user, need management UI
- **Timezone handling** — `received_at` should always be UTC, displayed in user's timezone
- **Long subjects / non-ASCII** — already handled in mail_agent helpers
- **Encrypted/signed emails (S/MIME, PGP)** — not supported, document as limitation
- **Calendar invites (.ics)** — render inline in email view, link to calendar
- **DSN bounce reports** — Postmark handles for managed/forwarding, Gmail handles for Gmail mode
- **Quota / storage limits per org** — needed for SaaS billing
- **Migration between modes** — what happens when an org switches from managed to Gmail? Need migration tooling

## Open questions

- Do we want to support a single org having BOTH Gmail mode AND managed mode (e.g., contact@ via managed for customer-facing, owner@gmail.com via Gmail mode for personal)?
- What's the right abstraction for shared inboxes vs personal inboxes within a single account?
- Should we build our own DKIM signing or always rely on the email provider?
- Cost model: do we charge per email volume, per integration, per user?

## Sapphire Pools migration timeline

- **Today**: Phase 0 — set up Cloudflare to forward to Gmail in addition to Worker. ~10 min config.
- **Phase 2 complete**: Sapphire switches to Gmail API mode. Disconnect managed mode. Cloudflare MX → Google MX.
- **Until Phase 2**: Sapphire runs in hybrid (Cloudflare → Gmail + Worker). Best of both temporarily.
