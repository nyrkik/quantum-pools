# Email Pipeline — Architecture

The email pipeline handles all inbound and outbound email for QuantumPools. **Multi-mode:** inbound arrives via Gmail API sync (OAuth-connected orgs) or Cloudflare Email Workers (managed mode). Outbound dispatches to Gmail API (connected orgs, appears in user's Sent folder) with Postmark as fallback. The pipeline classifies emails with AI, matches senders to customers, threads conversations, extracts action items, drafts responses, and tracks delivery status. **QP never auto-sends customer email** — AI drafts every reply; humans always approve from the inbox timeline. See `memory/feedback_no_auto_send.md` for the rationale.

**Organization:** Threads live in folders (Inbox/Sent/Spam + custom). Senders can be tagged (billing/vendor/notification/personal/etc.) with optional auto-folder routing. Domain patterns supported (`*@scppool.com`). `rfc_message_id` prevents cross-source duplicates.

**Rendering:** HTML bodies stored alongside stripped text, rendered client-side in a sandboxed iframe (no script execution, CSS isolated). Quoted text auto-detected and collapsed. Attachments render as image grid + type-colored file cards.

**Deliverability:** Postmark webhook (`/api/v1/admin/postmark-webhook`) receives Delivery/Bounce/Open/SpamComplaint events. Outbound messages show status chips (Delivered, Opened Nx, Bounced, Spam, **Send failed**, **Sending…**). The "Failed" filter surfaces ALL outbound failure modes — bounces and spam complaints from the recipient, plus our-side `delivery_error`/`status=failed`/`status=queued` (sender path crashed before delivery).

**Send-failure hardening (post FB-24):** Every outbound send path — compose, reply approval (service + admin endpoint), follow-up (service + admin endpoint) — is wrapped in try/except. On any exception the shared helper `services/agents/send_failure.py:record_outbound_send_failure` rolls back the crashed transaction, persists a `failed` outbound `AgentMessage` with the actual error in `delivery_error`, and recomputes thread state. The Failed filter counts threads only by their LATEST outbound attempt, so a successful retry resolves the thread (no false-positive failure inflation from retry storms). An APScheduler `_run_outbound_send_janitor` runs every 2 minutes, flips outbound messages stuck in `queued` >5 min to `failed` ("timed out in queue"), recomputes thread state, and fires a high-priority ntfy alert. When Gmail OAuth fails, `send_agent_reply` marks the integration `status='error'` with `last_error_at` so the inbox page shows a "Reconnect" banner instead of silently falling through to Postmark indefinitely. Backend 500s alert via ntfy (was email — chicken-and-egg when the email path itself is broken).

**Pipeline health monitoring (`agent_poller`):**
- **Gmail incremental sync** every 60s for every connected `gmail_api` integration. After 3 consecutive failures the integration auto-flips to `status='error'` with `last_error` populated and ntfy fires.
- **Inbound freshness canary** every 5 min. System-wide alert if no inbound mail has arrived in 6 h (business hours) / 24 h (overnight/weekends). Catches the case where per-integration health probes look fine but no mail is actually flowing.
- **Thread state reconciliation** every 30 min. Detects drift between `AgentThread.message_count` and the actual count, runs `update_thread_status` on any mismatched thread. Alerts ops if it has to fix more than 5 in a single pass.
- **Last-synced indicator** in inbox header (refetched on a 60 s tick) goes amber if `last_sync_at` is older than 5 min.

**Auto-handled visibility model (2026-04-25 redesign):** The classifier auto-closes inbound mail without a reply in three places: `general` + no draft + sender-not-customer; `no_response`/`thank_you` past the first-contact guardrail; `spam`/`auto_reply` (also moved to Spam folder). Each of those decision points calls `_mark_thread_auto_handled` (in `orchestrator.py`) which stamps `agent_threads.auto_handled_at = now()` and emits `thread.auto_handled` (taxonomy §thread).

`thread.status` no longer encodes auto-handled — it's a clean lifecycle axis (`pending` → `handled` → `archived`). `update_thread_status` derives `handled` whenever ANY message is sent OR an inbound has `status='handled'`, so AI-auto-closed threads naturally land in the Handled segment alongside human replies. The old conflated `status='ignored'` (which the default Inbox query was hiding) is no longer derived; explicit user-dismiss now derives to `archived`.

Two fields layered on top:
- `auto_handled_at` (sticky) — drives the `was_auto_handled` row pill ("AI" badge in every Handled view, including for non-admins; first place non-admins ever see AI's work).
- `auto_handled_feedback_at` (ack) — drives `is_auto_handled` (in-thread feedback banner). Cleared once the user clicks Yes/No.

Surfaces:
- **AI Review sidebar folder** (system_key `ai_review`, owner+admin only via `inbox.manage`) — virtual folder seeded per org. Query: `auto_handled_at IS NOT NULL AND auto_handled_feedback_at IS NULL`. Amber sidebar badge. Replaces the prior `Auto` filter-chip segment, which was admin-only and easy to miss.
- **Handled segment** — every role sees auto-handled threads here, marked with the `AIBadge` row pill (badge order: sender → category → status → AI → stale).
- **Reading-pane Yes/No banner** — three-state behavior unchanged from 2026-04-14: `covered` (existing rule catches sender), `promotable` (single matching rule → "Add to rule" appends to its value list), `unclear` (classic Yes / Create-rule / No). All three paths feed `AgentLearningService` (`agent_type=email_classifier`); "No, move to Inbox" restores the thread + marks pending. `auto_handled_feedback_at` is set on every click so the banner doesn't reappear.

Backfill for legacy `status='ignored'` rows (AI-auto-closed pre-redesign): `app/scripts/migrate_auto_handled_status.py` (dry-run + commit modes). Heuristic: status='ignored' + has inbound `status='handled'` + no outbound sent → flip to `status='handled'` + populate `auto_handled_at` from the inbound's received_at. User-archived threads (no inbound `handled`) keep `status='ignored'`.

**Inbox rules any-of + virtual fields (2026-04-14):** Condition `value` can be scalar OR array; array matches when ANY element satisfies the operator (prevents rule bloat; `scripts/collapse_inbox_rules.py` merged 54 single-sender rules to 10). New actions: `skip_customer_match` (advisory — tells `match_customer` to skip step-2 previous-match reuse for shared/regional senders like CONAM regional contacts). New virtual condition field: `customer_matched` (derived at evaluate time from matched_customer_id; "yes" if present, "no" otherwise). Default "Clients folder routing" rule uses this: `customer_matched equals "yes" → assign_folder Clients`. Rule editor UI gained inline folder creation, free-form tag input with datalist autocomplete, and a grouped permission-catalog picker for the Restrict-visibility action.

**Gmail spam bidirectional sync (2026-04-14):** Gmail-filtered spam now flows into QP alongside regular inbox mail:
- `gmail/sync.py` passes `includeSpamTrash=True` on both the initial list and the history fetch. `historyTypes` expanded to `[messageAdded, labelAdded, labelRemoved]` so SPAM label transitions on existing messages mirror into QP via `_apply_spam_label_change`.
- Orchestrator's `classify_and_draft` is skipped when Gmail's `labelIds` include `SPAM` (trusts Gmail's judgment). Auto-handled spam branch routes the thread to the Spam folder so it's actionable inside QP.
- Known-customer override remains: Gmail SPAM on mail from a matched customer forces human review (category → `general`, `needs_approval=true`) instead of being silently hidden.
- QP → Gmail mark-as-spam propagates via `gmail/read_sync.py::sync_spam_label` (calls `users.threads.modify(addLabelIds=['SPAM'], removeLabelIds=['INBOX'])`, fire-and-forget). The `/bulk/spam` and `/bulk/not-spam` endpoints capture `gmail_thread_id`s pre-update and push after commit.
- 30-day retention APScheduler job (`_run_spam_retention`, 04:30 UTC daily) purges `category='spam'` threads older than 30 days. Skips threads with attached `AgentAction` rows to avoid FK violations.
- Backfill: `scripts/unwrap_stored_mime_bodies.py` (one-shot for pre-unwrap stored bodies) + `scripts/regenerate_missing_drafts.py` (idempotent draft regeneration).

**Raw-MIME envelope unwrap (centralized 2026-04-14):** Some Outlook/Exchange senders relayed via Postmark deliver `TextBody` that literally contains the multipart MIME envelope (boundary markers + Content-Type / Content-Transfer-Encoding headers) instead of decoded plain text. `_unwrap_embedded_mime` (in `mail_agent.py`) now runs inside `extract_bodies` as a post-extract safety net — any ingest path (Postmark, SendGrid, Mailgun, Generic, Gmail raw, future MS Graph) benefits. Per-provider patching no longer needed. 3 regression tests in `test_mail_agent_mime_unwrap.py` lock this in.

**Canonical body decode pipeline (2026-04-20):** Every text part flows through `decode_part(part)` in `mail_agent.py`, which replaces the previous ad-hoc `part.get_payload(decode=True).decode(charset)` with a 3-stage pipeline per `docs/email-body-pipeline-refactor.md`. Stages: (1) bytes→unicode with charset fallback (try declared → `charset-normalizer` → `latin-1 + errors='replace'`), (2) `ftfy.fix_text(uncurl_quotes=False)` to repair mojibake from upstream charset lies (fixes `youâ\x80\x99ll` → `you'll`), (3) `unicodedata.normalize("NFC", …)` + strip U+200B/C/D + U+FEFF marketer padding. `_post_decode_normalize` adds a QP safety net for pre-mangled bodies (Postmark TextBody with raw `=3D`/`=09`). `extract_bodies` runs decode_part per part, then detects HTML-in-plaintext + runs `inscriptis.get_text()` for layout-aware HTML→text. `strip_quoted_reply` + `strip_email_signature` now thin-wrap `mail-parser-reply` (multi-language; replaces brittle English-only regex). Postmark ingest prefers `payload['RawEmail']` over pre-parsed `TextBody`/`HtmlBody` so MIME + charset quirks are handled by stdlib, same as Gmail raw. Diagnostic flags (`charset_fallback_used`, `mojibake_repaired`, `zero_width_stripped`, `qp_decoded`, `html_stripped_from_text`, `mime_unwrapped`) accumulate in a ContextVar; the orchestrator emits `email.body_normalized` (taxonomy §8.10b) with per-transform keys so new provider quirks surface in `platform_events` before users report them. Post-deploy audit on Sapphire: zero rows with QP tokens, mojibake, or zero-widths in either `agent_messages.body` or `agent_threads.last_snippet`.

**Sender display name (`AgentMessage.from_name`, 2026-04-20):** Parsed at ingest via `parse_from_header` (uses `email.headerregistry.Address`, RFC 5322 grammar — not legacy `parseaddr` regex). Stores "American Express" for `r_07b156d0…@welcome.americanexpress.com`-style VERP senders. `ThreadPresenter` fallback chain for unmatched threads: matched customer → `thread.customer_name` → latest inbound `from_name` → `_prettify_contact_email` domain-based fallback (`welcome.americanexpress.com` → `americanexpress.com`). Historical-row recovery via `app/scripts/backfill_from_name_via_gmail.py` (refetches From headers from Gmail by thread ID — 71/90 Gmail-ingested legacy rows recovered on Sapphire). Postmark + legacy-UID rows stay NULL (no retrievable source) but degrade gracefully to the domain prettifier.

**Legacy `received_at` correction (2026-04-20):** Old IMAP-based ingest stamped `AgentMessage.received_at` with the moment QP pulled the message, not the `Date:` header. Current orchestrator honors the Date header via `parsedate_to_datetime`; `app/scripts/backfill_received_at_via_gmail.py` is a one-shot historical fix — searches Gmail by `from:<sender> subject:"<subject>"` and takes `internalDate` (ms since epoch, server-authoritative). Also recomputes `agent_threads.last_message_at` + `last_direction` denorms. Idempotent (skips rows within 60s of Gmail's internalDate).

**Manual refresh:** Inbox header has a refresh button (`POST /api/v1/email-integrations/sync-all`) that triggers incremental sync across all connected Gmail integrations in the org and returns aggregate stats. Used when the user wants to pull new mail without waiting for the polling cycle.

## Infrastructure

| Concern | Provider | Cost |
|---------|----------|------|
| Outbound sending | Postmark API | $15/month (10K emails) |
| Inbound receiving | Cloudflare Email Workers (free) | $0 |
| DNS / MX | Cloudflare | Included |
| DKIM signing | Postmark (outbound) + Cloudflare (routing) | Included |
| Bounce tracking | Postmark webhooks | Included |
| Delivery tracking | Postmark webhooks | Included |

### DNS records (sapphire-pools.com)

| Type | Name | Value | Purpose |
|------|------|-------|---------|
| MX | @ | route1/2/3.mx.cloudflare.net | Cloudflare Email Routing |
| TXT | @ | v=spf1 include:spf.mtasv.net include:_spf.mx.cloudflare.net ~all | SPF |
| TXT | 20260407020608pm._domainkey | k=rsa;p=... | Postmark DKIM |
| TXT | cf2024-1._domainkey | v=DKIM1;... | Cloudflare DKIM |
| CNAME | pm-bounces | pm.mtasv.net | Postmark Return-Path |
| TXT | _dmarc | v=DMARC1; p=none; rua=mailto:brian.parrotte@pm.me | DMARC (monitor mode) |

### Cloudflare Email Routing rules

All addresses route to the `sapphire-pools-email` Cloudflare Worker:
- contact@sapphire-pools.com → Worker
- brian@sapphire-pools.com → Worker
- kim@sapphire-pools.com → Worker
- chance@sapphire-pools.com → Worker
- Catch-all → Worker

Worker source: `/email-worker/src/index.ts`
Deploy: see "Webhook authentication & deploy" section below.

### Webhook authentication & deploy

Both inbound and outbound (delivery/bounce) webhooks are gated by a shared secret in `POSTMARK_WEBHOOK_TOKEN` (backend `.env`). Every webhook must POST with header `X-Webhook-Token: <token>`. Backend fails closed: if env var is unset, every webhook 401s. Constant-time compare prevents timing oracles. Confirmed safe over public internet.

**Where the secret is set (3 places must match):**

| Where | How |
|---|---|
| Backend | `POSTMARK_WEBHOOK_TOKEN` in `/srv/quantumpools/app/.env`. Restart `quantumpools-backend` to pick up. |
| Postmark webhooks | Postmark dashboard → Servers → Sapphire Pools → Default Transactional Stream → each webhook (Delivery, Bounce, Spam Complaint) → "Custom HTTP headers" → add `X-Webhook-Token: <token>`. |
| Cloudflare Worker | `wrangler secret put WEBHOOK_TOKEN` (interactive prompt) — bound to the worker, NOT in wrangler.toml. |

**Why three webhooks all point at the inbound endpoint** (not the dedicated `/admin/postmark-webhook`): we use `?type=bounce` and `?type=delivery` query params on the inbound URL. The backend dispatches to `_handle_status_webhook` based on that. The dedicated `/admin/postmark-webhook` exists but is unused — kept for future where a single multi-event subscription is preferable. Spam Complaint webhook uses `?type=bounce` (cosmetic — backend doesn't have a separate spam handler yet, treats as bounce).

**Webhook handler coverage:** `?type=` accepts `bounce`, `delivery`, `opens`, `spam_complaint`. All four write to `AgentMessage.delivery_status` (delivery state), never to `msg.status` (workflow state — that stays `sent`/`auto_sent`).

- `bounce`: `delivery_status='bounced'`, `delivery_error=<bounce type + description>`
- `delivery`: `delivery_status='delivered'`, `delivered_at=now` (skipped if already bounced/spam — out-of-order events)
- `opens`: bumps `open_count`, stamps `first_opened_at` once, sets `delivery_status='opened'` (skipped if already in terminal failure state)
- `spam_complaint`: `delivery_status='spam_complaint'`, `delivery_error='Recipient marked as spam'`

Not handled: `?type=subscription_change` (Postmark unsubscribe events) — we don't currently run a marketing list so opt-outs aren't relevant.

**To enable any of these in Postmark dashboard:** edit the corresponding webhook → set URL to `https://api.quantumpoolspro.com/api/v1/inbound-email/webhook/sapphire?provider=postmark&type=<type>` → add the same `X-Webhook-Token` custom header.

**What we do NOT use:** Postmark Inbound Stream (paid-plan only). Cloudflare Email Worker handles inbound.

**Worker deploy steps:**
```bash
cd /srv/quantumpools/email-worker
# Auth: needs CLOUDFLARE_API_TOKEN env var (already in /srv/quantumpools/app/.env).
# Token scope: "Edit Cloudflare Workers" template is sufficient.
export CLOUDFLARE_API_TOKEN=$(grep '^CLOUDFLARE_API_TOKEN=' /srv/quantumpools/app/.env | cut -d= -f2)
npx wrangler deploy             # ship code changes
echo '<token>' | npx wrangler secret put WEBHOOK_TOKEN   # set/rotate worker secret
npx wrangler whoami             # sanity check auth
```

Cloudflare account: `brian.e.parrotte@gmail.com` (account ID `4f5794507b55069e37d5ce874cec7e85`). Worker name: `sapphire-pools-email`.

**Token rotation procedure (do this if the secret is ever exposed):**
1. Generate new: `python -c 'import secrets; print(secrets.token_urlsafe(32))'`
2. Update `POSTMARK_WEBHOOK_TOKEN` in `/srv/quantumpools/app/.env`
3. Restart backend: `sudo systemctl restart quantumpools-backend`
4. Postmark dashboard: edit each webhook custom header to the new value, save
5. Update CF Worker secret: `echo '<new-token>' | npx wrangler secret put WEBHOOK_TOKEN`
6. Verify: send a test inbound email; check `journalctl -u quantumpools-backend | grep webhook` for 200s, not 401s

**Failure mode:** if any of the three places drift out of sync, that path silently 401s and inbound or delivery events vanish. The agent_poller's "inbound freshness canary" (every 5 min) and the backend's "webhook rejected" log line are the early-warning signals — both fire ntfy alerts.

## Data flow

```
                                   INBOUND
                                   -------

  Cloudflare Email Routing
  (MX → route3.mx.cloudflare.net)
       |
       v
  Email Worker (sapphire-pools-email)
  (parse raw email, extract
   from/to/subject/body/headers)
       |
       v
  POST /v1/inbound-email/webhook/sapphire?provider=cloudflare
       |
       v
  inbound_email_service.py
  (parse provider payload,
   build EmailMessage,
   resolve org by slug,
   check block rules,
   stable UID from Message-ID hash)
       |
       v
  orchestrator.py :: process_incoming_email()
       |
       |--- 1. Reply loop check (_is_own_email, INTERNAL_PATTERNS)
       |--- 2. Dedup check (AgentMessage.email_uid unique)
       |--- 3. Routing rule match (Delivered-To → visibility_role_slugs)
       |--- 4. Thread: get_or_create_thread() (thread_manager.py)
       |--- 5. Customer match (customer_matcher.py, 7-layer cascade)
       |--- 6. AI triage (triage_agent.py — "does this need a response?")
       |--- 7. AI classification + draft (classifier.py)
       |        |
       |        +--- spam/auto_reply/no_response → save as "handled" (visible in inbox)
       |        +--- spam/auto_reply from customer → override to "pending"
       |
       |--- 8. Save AgentMessage (status=pending or handled)
       |--- 9. Extract action items (max 3, dedup via word overlap)
       |--- 10. Create AgentAction records
       |--- 11. Send approval SMS (business hours + throttle) for urgent drafts
       |--- 12. Publish SSE event (THREAD_NEW / THREAD_MESSAGE_NEW)
       |--- 13. Post-verify customer match (verify_customer_match)
       v


                                   OUTBOUND
                                   --------

  Inbox UI (approve/reply)       Compose UI          Job draft_email       Broadcast
       |                              |                     |                  |
       v                              v                     v                  v
  agent_thread_service.py    email_compose_service.py  command_executor.py  broadcast_service.py
  (approve, send-followup,   (compose_and_send)        (_draft_email)      (create_broadcast)
   revise-draft)                     |                     |                  |
       |                              |                     |                  |
       +------------------------------+---------------------+------------------+
       |
       v
  email_service.py :: EmailService.send_agent_reply()   <-- SINGLE EXIT POINT
       |
       |--- Append signature (sender first name + org name + org block)
       |--- Add Re: prefix (unless is_new=True)
       |--- From address: org's agent_from_email
       |--- Check for gmail_api EmailIntegration (is_primary=True, status=connected)
       |       |
       |       +-- If a gmail_api integration EXISTS but isn't connected+primary:
       |           FAIL FAST with a user-visible error ("Reconnect Gmail in
       |           Inbox → Integrations"). Do NOT fall through to Postmark —
       |           that would send from the user's Gmail address, which is
       |           almost never a verified Postmark Sender Signature and
       |           guarantees a 422. Surfaces as a toast on the approve/send
       |           endpoint instead of an opaque 500.
       v
  Gmail API (if connected)                    PostmarkProvider (no gmail_api at all)
       |                                            |
       |--- users.messages.send()                   |--- Returns MessageID
       |--- Appears in user's Sent folder           |
       v                                            v
  AgentMessage (direction=outbound, status=sent)
  update_thread_status()


                          BOUNCE / DELIVERY TRACKING
                          --------------------------

  Postmark sends status webhooks:
       |
       +--- POST /webhook/sapphire?provider=postmark&type=bounce
       |    → Updates AgentMessage.status = "bounced", delivery_error = description
       |
       +--- POST /webhook/sapphire?provider=postmark&type=delivery
            → Updates AgentMessage.status = "delivered"
```

## Components

### email-worker/ (Cloudflare Worker)
TypeScript worker deployed to Cloudflare. Receives raw email via Cloudflare Email Routing's `email()` event handler. Parses MIME (multipart text/plain + text/html, quoted-printable, base64). POSTs parsed JSON to the webhook endpoint. Source: `email-worker/src/index.ts`.

### agent_poller.py (systemd background service)
The `quantumpools-agent` systemd service. Does NOT poll for email (inbound is webhook-based). Runs scheduled tasks every 60 seconds: estimate reminders (hourly), internal message escalations (every 5 min), stale visit auto-close (every 30 min). Includes monitoring: Sentry capture on all exceptions, ntfy push alerts after 3 consecutive failures per function, recovery notifications, heartbeat with failure state.

### orchestrator.py (main pipeline)
Ties all agents together. `process_incoming_email()` is the central function that takes a raw email message and runs the full inbound pipeline: loop detection, dedup, routing, threading, customer matching, triage, classification, action extraction, approval dispatch, and SSE event publishing. Also exposes `auto_close_stale_visits()` called from the poller.

### mail_agent.py (email parsing utilities)
Email parsing utilities. Includes `strip_quoted_reply()` (5 patterns: "On ... wrote:", "Sent from my iPhone", Outlook headers, forwarded markers, `>` quoting), `strip_email_signature()` (standard sig separator, sign-off lines, confidentiality disclaimers), `_clean_html()` (HTML-to-text conversion), `extract_text_body()` (MIME part extraction with charset handling), `_unwrap_embedded_mime()` (detects bodies that are themselves a raw multipart MIME envelope — Postmark sometimes leaks the boundary + Content-Type headers into TextBody for Outlook/Exchange-relayed messages — wraps in a synthetic envelope and re-parses to extract the inner text/plain), `decode_email_header()` (MIME-encoded header decoding). IMAP functions still exist but are unused — inbound is handled by webhooks.

### inbound_email_service.py (webhook processing)
Provider-agnostic inbound email processing. Supports Cloudflare (primary), Postmark, SendGrid, Mailgun, and generic webhooks. Resolves org by slug, parses provider-specific payload into `ParsedEmail` (with attachment support), checks block rules, generates stable UID from Message-ID hash (max 35 chars), builds a stdlib `EmailMessage`, and feeds it into `process_incoming_email()`. Also handles Postmark bounce/delivery status webhooks — updates `AgentMessage.status` and `delivery_error`.

### email_service.py (provider-agnostic sending)
Postmark is the only provider. `PostmarkProvider` sends via HTTP API. No SMTP fallback — failures are logged and reported via Sentry/ntfy, not silently swallowed. `EmailService` loads org config (from_email, from_name) and delegates to PostmarkProvider. Single exit point for customer email: `send_agent_reply()` handles signature assembly, Re: prefix, from_address (always org config, never delivered_to). Returns `EmailResult` with `message_id` (Postmark MessageID). Also provides: `send_team_invite()`, `send_invoice_email()`, `send_estimate_email()`, `send_notification_email()`, `send_password_reset()`, `send_password_changed()`, `send_payment_failed_email()`, `send_autopay_receipt()`.

Invoice/estimate recipient resolution: outbound billing emails resolve the To: address from `customer_contacts` filtered by `receives_invoices` / `receives_estimates` (primary first) and fall back to the legacy `customers.email` only when no matching contacts exist. See `EstimateWorkflowService._resolve_recipients` and `send_invoice` in `app/src/api/v1/invoices.py`.

### email_compose_service.py (compose + AI drafts)
Handles outbound email composition from the UI. `compose_and_send()`: FROM address uses org config (Postmark-verified), creates `AgentMessage` + `AgentThread` records (status=queued before send), loads file attachments (max 5), sends via `EmailService.send_agent_reply()`, stores `postmark_message_id`, updates status to sent/failed. `generate_draft()`: AI-assisted draft generation with full customer context.

### classifier.py (AI classification + draft)
Calls Claude (Haiku) with system prompt including tone rules, category definitions, and action extraction guidelines. Categories: `schedule`, `complaint`, `billing`, `gate_code`, `service_request`, `general`, `spam`, `auto_reply`, `no_response`. All categories are visible in inbox — no category auto-hides emails.

**Phase 5 email_drafter migration (shipped 2026-04-24)**: the classifier's `draft_response` output is staged as an `email_reply` proposal via `ProposalService.stage(entity_type="email_reply", ...)` with source_id = the inbound `AgentMessage.id`. The proposal carries the draft in its `proposed_payload.body`; `AgentMessage.draft_response` is never written for new inbound (and the R7 audit enforcer blocks regressions). The inbox reading pane renders `<ProposalCard>` exclusively — no legacy drawer. Accept → `proposals/creators/email_reply.py` delegates the send to `EmailService.send_agent_reply` (canonical outbound path), marks inbound sent, creates outbound `AgentMessage`, and recomputes thread status — all atomic inside `ProposalService.accept`'s transaction. Edit → `agent_corrections` row with the RFC 6902 patch, feeding the learning loop via `build_lessons_prompt(AGENT_EMAIL_DRAFTER)` on the next classification.

### customer_matcher.py (7-layer customer matching)
Matches inbound emails to customers. Layers: direct email, contact email, previous match, domain match, sender name, text search (scored), last name search. Fuzzy matches verified by Claude Haiku.

**Phase 5 customer_matcher extension (shipped 2026-04-24)**: high-confidence trusted-method matches (`email`, `contact_email`, `previous_match`, `sender_name`) auto-apply unchanged — deterministic join logic, not AI commitment. When a fuzzy match fails Claude QC verification, the dropped candidate is appended to an `unverified_sink` the orchestrator passes in, and each unverified candidate becomes a `customer_match_suggestion` proposal (source_type="thread", source_id=thread.id, payload carries `candidate_customer_id`, `reason`, `confidence`). Owner+admin review at `/inbox/matches`; Accept applies `thread.matched_customer_id`; Reject preserves unmatched + records correction.

### triage_agent.py (AI triage)
Quick Claude Haiku call: "Does this email require a response?" Returns boolean. Used for categorization but does NOT hide emails from inbox. All emails remain visible regardless of triage result.

### thread_manager.py (thread lifecycle)
Groups emails into conversation threads via `thread_key` = `normalized_subject|contact_email`. `update_thread_status()` recalculates: message_count, has_pending, status, last_message_at, last_direction, last_snippet.

### sent_tracker.py (DEPRECATED)
Previously tracked emails sent directly from Gmail's Sent folder. No longer called — all outbound sends go through the app and are tracked via `AgentMessage` records with `postmark_message_id`.

## Models

### AgentMessage (`agent_messages`)
Individual email records. Key fields: `email_uid` (unique, dedup key — `pm-{hash}` for webhook emails), `direction` (inbound/outbound), `from_email`, `to_email`, `subject`, `body`, `category`, `urgency`, `status` (pending/approved/sent/auto_sent/rejected/handled/queued/failed/bounced/delivered), `postmark_message_id` (Postmark tracking), `delivery_error` (bounce reason), `delivered_to`, `thread_id`, `received_at`.

`final_response` exists on inbound messages that have been replied to — written by the `email_reply` proposal creator as a convenience link back to the body that was sent. It duplicates `AgentMessage.body` on the corresponding outbound row; six downstream readers still depend on it. Denormalizing to a single source of truth is a separate future cleanup, not Phase 5 scope.

> **Column history**: `draft_response` was dropped in Phase 5b (2026-04-24). AI drafts now live on `agent_proposals(entity_type='email_reply')` exclusively; the R7 audit enforcer blocks any `.draft_response` attribute access in `app/src/` to prevent reintroduction.

### AgentThread (`agent_threads`)
Groups related emails into a conversation. Key fields: `thread_key`, `contact_email`, `subject`, `matched_customer_id`, `status` (pending/handled/archived), `last_direction`, `has_pending`, `visibility_role_slugs` (JSONB list — see `docs/data-model.md` for the role-group visibility model), `delivered_to`, `assigned_to_user_id`.

### AgentAction (`agent_actions`)
Job/action items extracted from emails or created manually.

## Configuration

### Environment variables

| Variable | Purpose |
|----------|---------|
| `POSTMARK_SERVER_TOKEN` | Postmark API token (required) |
| `AGENT_FROM_EMAIL` | Default sender address (must be Postmark-verified) |
| `AGENT_FROM_NAME` | Default sender display name |
| `AGENT_LOCATION` | Company location for classifier context |
| `ANTHROPIC_API_KEY` | Claude API key for all AI agents |
| `NOTIFICATION_EMAIL` | Alert recipient for health checks |

### Organization-level config

| Field | Purpose |
|-------|---------|
| `agent_from_email` | Org-specific sender address (Postmark-verified) |
| `agent_from_name` | Org-specific sender name |
| `agent_signature` | Shared org footer appended to every outbound signature (links, compliance lines). Standardized across all senders. |
| `auto_signature_prefix` | Admin toggle: prepend `{sender_first_name}\n{org_name}` above the user signature |
| `include_logo_in_signature` | Admin toggle: embed `logo_url` as inline CID image at the bottom of HTML signatures |
| `agent_tone_rules` | Custom tone guidelines for AI drafts |

Per-user fields live on `organization_users` (one row per user-per-org):

| Field | Purpose |
|-------|---------|
| `email_signature` | User's personal contact info rendered above the org footer |
| `email_signoff` | Optional valediction ("Best,", "v/r,") rendered above the name line |

Signature composition lives in `src/services/email_signature.py` — single source of truth. Order rendered (top → bottom): optional sign-off → optional auto-prepended name + org name → user's personal signature text → org footer → optional CID logo.

## Monitoring

### Agent poller (quantumpools-agent.service)
- **Sentry**: all exceptions captured with full tracebacks
- **ntfy**: push alerts to `qp-alerts` topic after 3 consecutive failures, recovery notifications on success
- **Heartbeat**: every 30 cycles (~30 min) with active failure counts

### Health check (cron, every 10 min)
- Agent service running and logging
- Postmark API reachable
- Webhook endpoint responding
- No stuck/bounced/failed outbound emails
- Backend API healthy
- Alerts via ntfy (primary) + Postmark email (secondary)

### Bounce/delivery webhooks
- Postmark POSTs bounce/delivery events to webhook endpoint
- `AgentMessage.status` updated to `bounced` or `delivered`
- `delivery_error` captures bounce reason

## Planned enhancements

- Inbox redesign as proper email client (current design is AI triage queue)
- CC capture on inbound emails
- Multi-sender thread handling
- Background send queue (currently synchronous)
- Per-org storage quotas for attachments
- Attachment extraction from Cloudflare Worker (currently text-only)
