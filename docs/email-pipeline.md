# Email Pipeline — Architecture

The email pipeline handles all inbound and outbound email for QuantumPools. **Multi-mode:** inbound arrives via Gmail API sync (OAuth-connected orgs) or Cloudflare Email Workers (managed mode). Outbound dispatches to Gmail API (connected orgs, appears in user's Sent folder) with Postmark as fallback. The pipeline classifies emails with AI, matches senders to customers, threads conversations, extracts action items, drafts responses, tracks delivery status, and monitors auto-sends for trust calibration.

**Safety layers** (3-deep, see "Auto-Send Safety" below):
- Org flag `email_auto_send_enabled` (default false) gates all auto-replies
- Commitment phrase guard blocks drafts with "follow up", "get back", "look into", etc.
- First-contact ntfy alert when AI auto-sends to a new sender

**Organization:** Threads live in folders (Inbox/Sent/Spam + custom). Senders can be tagged (billing/vendor/notification/personal/etc.) with optional auto-folder routing. Domain patterns supported (`*@scppool.com`). `rfc_message_id` prevents cross-source duplicates.

**Rendering:** HTML bodies stored alongside stripped text, rendered client-side in a sandboxed iframe (no script execution, CSS isolated). Quoted text auto-detected and collapsed. Attachments render as image grid + type-colored file cards.

**Deliverability:** Postmark webhook (`/api/v1/admin/postmark-webhook`) receives Delivery/Bounce/Open/SpamComplaint events. Outbound messages show status chips (Delivered, Opened Nx, Bounced, Spam). "Failed" filter surfaces bounced/errored sends across all folders.

**Auto-send monitoring:** Threads with auto-sent replies get a sky-blue "Auto-Sent" chip. Reading pane shows a feedback banner (Yes/No — owner/admin only) that records `AgentCorrection` for learning. Weekly digest email to org owner summarizes auto-sends. First-contact auto-sends trigger ntfy push alert.

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
Deploy: `CLOUDFLARE_API_KEY=... CLOUDFLARE_EMAIL=... npx wrangler deploy` from `email-worker/` dir

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
       |--- 3. Routing rule match (Delivered-To → visibility_permission)
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
       |--- 11. Send approval SMS (business hours + throttle) OR auto-send
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
       v
  Gmail API (if connected)                    PostmarkProvider (fallback)
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
Postmark is the only provider. `PostmarkProvider` sends via HTTP API. No SMTP fallback — failures are logged and reported via Sentry/ntfy, not silently swallowed. `EmailService` loads org config (from_email, from_name) and delegates to PostmarkProvider. Single exit point for customer email: `send_agent_reply()` handles signature assembly, Re: prefix, from_address (always org config, never delivered_to). Returns `EmailResult` with `message_id` (Postmark MessageID). Also provides: `send_team_invite()`, `send_invoice_email()`, `send_estimate_email()`, `send_notification_email()`, `send_payment_failed_email()`, `send_autopay_receipt()`.

### email_compose_service.py (compose + AI drafts)
Handles outbound email composition from the UI. `compose_and_send()`: FROM address uses org config (Postmark-verified), creates `AgentMessage` + `AgentThread` records (status=queued before send), loads file attachments (max 5), sends via `EmailService.send_agent_reply()`, stores `postmark_message_id`, updates status to sent/failed. `generate_draft()`: AI-assisted draft generation with full customer context.

### classifier.py (AI classification + draft)
Calls Claude (Haiku) with system prompt including tone rules, category definitions, and action extraction guidelines. Categories: `schedule`, `complaint`, `billing`, `gate_code`, `service_request`, `general`, `spam`, `auto_reply`, `no_response`. All categories are visible in inbox — no category auto-hides emails.

### customer_matcher.py (7-layer customer matching)
Matches inbound emails to customers. Layers: direct email, contact email, previous match, domain match, sender name, text search (scored), last name search. Fuzzy matches verified by Claude Haiku.

### triage_agent.py (AI triage)
Quick Claude Haiku call: "Does this email require a response?" Returns boolean. Used for categorization but does NOT hide emails from inbox. All emails remain visible regardless of triage result.

### thread_manager.py (thread lifecycle)
Groups emails into conversation threads via `thread_key` = `normalized_subject|contact_email`. `update_thread_status()` recalculates: message_count, has_pending, status, last_message_at, last_direction, last_snippet.

### sent_tracker.py (DEPRECATED)
Previously tracked emails sent directly from Gmail's Sent folder. No longer called — all outbound sends go through the app and are tracked via `AgentMessage` records with `postmark_message_id`.

## Models

### AgentMessage (`agent_messages`)
Individual email records. Key fields: `email_uid` (unique, dedup key — `pm-{hash}` for webhook emails), `direction` (inbound/outbound), `from_email`, `to_email`, `subject`, `body`, `category`, `urgency`, `draft_response`, `final_response`, `status` (pending/approved/sent/auto_sent/rejected/handled/queued/failed/bounced/delivered), `postmark_message_id` (Postmark tracking), `delivery_error` (bounce reason), `delivered_to`, `thread_id`, `received_at`.

### AgentThread (`agent_threads`)
Groups related emails into a conversation. Key fields: `thread_key`, `contact_email`, `subject`, `matched_customer_id`, `status` (pending/handled/archived), `last_direction`, `has_pending`, `visibility_permission`, `delivered_to`, `assigned_to_user_id`.

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
| `agent_signature` | Org email signature block |
| `agent_tone_rules` | Custom tone guidelines for AI drafts |

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
