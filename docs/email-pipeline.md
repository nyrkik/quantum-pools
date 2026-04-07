# Email Pipeline — Architecture

The email pipeline handles all inbound and outbound email for QuantumPools. It ingests customer emails via IMAP polling or inbound webhooks, classifies them with AI, matches senders to customers, threads conversations, extracts action items, drafts responses, and tracks outbound replies sent through the app or directly from Gmail.

## Data flow

```
                                   INBOUND
                                   -------

  Gmail IMAP                    Postmark/SendGrid/Mailgun
  (poll_inbox)                  (POST /v1/inbound-email/webhook/{org_slug})
       |                                    |
       v                                    v
  mail_agent.py                   inbound_email_service.py
  (fetch, parse,                  (parse provider payload,
   strip quoted                    build EmailMessage,
   replies)                        resolve org by slug)
       |                                    |
       +------------------------------------+
       |
       v
  orchestrator.py :: process_incoming_email()
       |
       |--- 1. Reply loop check (_is_own_email, INTERNAL_PATTERNS)
       |--- 2. DB block rules (inbox_routing_service.check_sender_blocked)
       |--- 3. Dedup check (AgentMessage.email_uid unique)
       |--- 4. Routing rule match (Delivered-To -> visibility_permission)
       |--- 5. Thread: get_or_create_thread() (thread_manager.py)
       |--- 6. Customer match (customer_matcher.py, 7-layer cascade)
       |--- 7. AI triage (triage_agent.py — "does this need a response?")
       |        |
       |        +--- No + not a customer --> save as "handled/no_response", done
       |        +--- No + IS a customer  --> override, proceed to classification
       |
       |--- 8. AI classification + draft (classifier.py)
       |        |
       |        +--- spam/auto_reply/no_response (non-customer) --> save as "ignored", done
       |        +--- spam/auto_reply from customer --> override to "pending"
       |
       |--- 9. Save AgentMessage (status=pending)
       |--- 10. Extract action items (max 3, dedup via word overlap)
       |--- 11. Create AgentAction records
       |--- 12. Send approval SMS (business hours + throttle) OR auto-send
       |--- 13. Publish SSE event (THREAD_NEW / THREAD_MESSAGE_NEW)
       |--- 14. Post-verify customer match (verify_customer_match)
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
       |--- Resolve from_address (org default or Delivered-To override)
       v
  EmailProvider (interface)
       |
       +--- PostmarkProvider (if POSTMARK_SERVER_TOKEN set)
       +--- SmtpProvider (Gmail SMTP fallback)
       Auto-fallback: if Postmark fails, retries via SMTP.
       If Postmark returns "pending approval", switches to
       SMTP for the remainder of the session (no more wasted
       Postmark attempts in batch sends).
       v
  AgentMessage (direction=outbound, status=sent)
  update_thread_status()


                               SENT TRACKING
                               -------------

  Gmail [Sent Mail]
       |
       v
  sent_tracker.py :: process_sent_emails()
       |
       |--- Fetch from [Gmail]/Sent Mail (not labeled QP-Processed)
       |--- Match to existing thread by recipient + subject similarity
       |--- Record as AgentMessage (direction=outbound)
       |--- Post comment on linked open jobs
       |--- Mark thread as handled
       |--- Label message QP-Processed
```

## Components

### agent_poller.py (systemd entry point)
The `quantumpools-agent` systemd service. Runs `run_poll_cycle()` every 60 seconds. Also checks estimate reminders hourly (3-day and 7-day stale estimate emails) and internal message escalations every 5 minutes. Heartbeat logged every 30 cycles (~30 min).

### orchestrator.py (main pipeline)
Ties all agents together. `process_incoming_email()` is the central function that takes a raw email message and runs the full inbound pipeline: loop detection, block rules, dedup, routing, threading, customer matching, triage, classification, action extraction, approval dispatch, and SSE event publishing. Also exposes `run_poll_cycle()` which calls `poll_inbox()`, processes each email, then runs sent folder tracking and auto-close of stale visits (every 30 min).

### mail_agent.py (IMAP polling)
Gmail IMAP client using `imapclient`. Fetches up to 10 unprocessed emails from INBOX (Gmail search: `-label:QP-Processed newer_than:2d`). Also fetches from `[Gmail]/Sent Mail` for outbound tracking. After processing, labels messages `QP-Processed` to prevent reprocessing. Includes `strip_quoted_reply()` (5 patterns: "On ... wrote:", "Sent from my iPhone", Outlook headers, forwarded markers, `>` quoting) and `strip_email_signature()` (standard sig separator, sign-off lines, confidentiality disclaimers). HTML-to-text fallback via `_clean_html()`.

### classifier.py (AI classification + draft)
Calls Claude (Haiku) with a detailed system prompt including tone rules, category definitions, and action extraction guidelines. Input: sender email, subject, body (2000 chars). Output: JSON with category, urgency, confidence, customer_name, summary, needs_approval, draft_response, internal_note, and actions array. Injects customer context from `match_customer()`, correction history from `get_correction_history()`, and lessons from `AgentLearningService`. Categories: `schedule`, `complaint`, `billing`, `gate_code`, `service_request`, `general`, `spam`, `auto_reply`, `no_response`. Confidence levels: `high`, `medium`, `low`. Action types: `follow_up`, `bid`, `schedule_change`, `site_visit`, `callback`, `repair`, `equipment`, `invoice`, `other`.

### customer_matcher.py (7-layer customer matching)
Matches inbound emails to customers in the database. Layers, in order:

1. **Direct email** — exact match on `customers.email` (comma-separated)
2. **Contact email** — match on `customer_contacts.email`
3. **Previous match** — reuse `matched_customer_id` from prior `AgentMessage` with same sender
4. **Domain match** — non-free domain `@company.com` matched to customers; single match = fallback, multiple = disambiguation list for Claude
5. **Sender name** — extract display name from From header or email prefix, match first+last against `customers`
6. **Text search (scored)** — search subject/body for display names, company names, property names, street addresses. Scoring: subject match = 3x, body match = 2x. Must have 2x lead over second candidate.
7. **Last name search** — word-boundary regex match on last names >= 4 chars, excluding 150+ common English words

Fuzzy matches (layers 4-7) are verified by Claude Haiku ("Does this email appear to be about this customer? yes/no"). Trusted methods (`email`, `contact_email`, `previous_match`, `sender_name`) skip verification. Post-processing `verify_customer_match()` auto-fixes missed direct matches and notifies admins.

### triage_agent.py (AI triage)
Quick Claude Haiku call (~200ms): "Does this email require a response?" Returns boolean. Says no for thank-yous, acknowledgments, informational status updates, automated notifications, marketing, FYI forwards, one-word affirmatives. Says yes for questions, service requests, complaints, information requests, callback requests. Defaults to yes on error or missing API key.

### thread_manager.py (thread lifecycle)
Groups emails into conversation threads via `thread_key` = `normalized_subject|contact_email`. Subject normalization strips Re:/Fwd: prefixes and trailing whitespace. `get_or_create_thread()` has two fallback strategies for existing customers: (1) subject similarity match on customer's recent threads (14 days), (2) single active thread within 7 days. New threads get routing fields (visibility_permission, delivered_to, routing_rule_id). `update_thread_status()` recalculates denormalized fields: message_count, has_pending, status (pending/handled/ignored), last_message_at, last_direction, last_snippet, urgency (highest from all messages), category (latest inbound), has_open_actions.

### command_executor.py (job commands)
Executes commands from `@DeepBlue` mentions in job comments. Sub-intents: `draft_email` (AI-generated reply with thread + job context), `create_estimate` (AI-generated line items), `assign` (reassign job + notification), `update_status`, `mark_done` (with task count update), `schedule`, `notify` (send notification to team member). Results posted as `AgentActionComment` records. Draft emails use `[DRAFT_EMAIL]` prefix for frontend detection.

### sent_tracker.py (outbound tracking)
Tracks emails sent directly from Gmail (not through the app). Polls `[Gmail]/Sent Mail` for messages from org addresses, matches to existing threads by recipient + subject similarity, records as outbound `AgentMessage`, posts comments on linked open jobs, and labels `QP-Processed`. Does not create new threads for sent emails.

### email_service.py (provider-agnostic sending)
Provider interface with two implementations: `PostmarkProvider` (HTTP API, preferred when `POSTMARK_SERVER_TOKEN` is set) and `SmtpProvider` (Gmail SMTP fallback via `aiosmtplib`). `EmailService` is the central class that loads org config (from_email, from_name) and delegates to the active provider. Single exit point for customer email: `send_agent_reply()` handles signature assembly, Re: prefix, from_address override. Also provides typed methods: `send_team_invite()`, `send_invoice_email()`, `send_estimate_email()`, `send_notification_email()`. Standalone `send_scraper_alert()` for EMD scraper notifications.

### email_compose_service.py (compose + AI drafts)
Handles outbound email composition from the UI. `compose_and_send()`: resolves FROM address (uses thread's `delivered_to` when replying from a job), creates `AgentMessage` + `AgentThread` records (status=queued before send), loads file attachments (max 5), sends via `EmailService.send_agent_reply()`, updates status to sent/failed. `generate_draft()`: AI-assisted draft generation with full customer context (properties, water features, open invoices, balance, recent threads, open jobs, contacts). Injects correction lessons from `AgentLearningService`.

### inbound_email_service.py (webhook processing)
Provider-agnostic inbound email processing for Postmark, SendGrid, Mailgun, and generic webhooks. Resolves org by slug, parses provider-specific payload into `ParsedEmail`, checks block rules, builds a stdlib `EmailMessage`, and feeds it into `process_incoming_email()` — the same function used by the IMAP poller.

### inbox_routing_service.py (routing rules)
Two functions: `match_routing_rule()` matches `Delivered-To` address against active rules with `match_field='to'` (priority-ordered, first match wins), returning visibility permission and optional category. `check_sender_blocked()` matches sender against rules with `match_field='from'` and `action='block'`. Match types: `exact` and `contains`. `extract_delivered_to()` pulls the address from `Delivered-To` header or falls back to `To` header parsing.

### broadcast_service.py (bulk email)
Creates and sends bulk emails to filtered customer lists. Filter types: `all_active`, `commercial`, `residential`, `custom` (specific customer IDs), `test` (single arbitrary address). Sends synchronously via `EmailComposeService.compose_and_send()` (creates thread + message records for each recipient). Records sent/failed counts on `BroadcastEmail`.

### agent_thread_service.py (thread operations)
Service layer for inbox UI operations: approve (edit draft + send), dismiss, archive, delete, assign thread, save/revise drafts, send follow-ups, draft follow-ups (AI), change visibility, create case/job from thread, draft estimate from thread, contact learning prompts (suggest saving unknown sender as customer contact).

### agent_action_service.py (job operations)
Service layer for jobs (action items). CRUD with rich behavior: create (with optional case auto-creation and customer-path draft estimate), update (with reassignment notifications, equipment change detection on completion, auto-invoice from approved estimate, AI follow-up suggestions), add comment (with `@DeepBlue` AI pipeline and `@{name}` mention notifications), AI-generated invoice drafts, task management (create/update/delete with denormalized counts).

### agent_learning_service.py (correction learning)
Records human corrections (`edit`, `rejection`, `acceptance`) for 8 agent types. Retrieves relevant lessons for prompt injection: prioritizes same-customer corrections, then same-category, then general. 90-day window, max 10 lessons, edits and rejections only. `build_lessons_prompt()` formats corrections into a ready-to-inject prompt section. Updates `applied_count` and `last_applied_at` for tracking effectiveness. Non-blocking — learning failures never break primary operations.

## Models

### AgentThread (`agent_threads`)
Groups related emails into a conversation. Key fields: `thread_key` (unique, `normalized_subject|contact_email`), `contact_email`, `subject`, `matched_customer_id` (FK customers), `status` (pending/handled/ignored), `urgency`, `category`, `message_count`, `last_message_at`, `last_direction`, `last_snippet`, `has_pending`, `has_open_actions`, `case_id` (FK service_cases), `visibility_permission`, `delivered_to`, `routing_rule_id`, `assigned_to_user_id`, `assigned_to_name`.

### AgentMessage (`agent_messages`)
Individual email records. Key fields: `email_uid` (unique, dedup key), `direction` (inbound/outbound), `from_email`, `to_email`, `subject`, `body`, `category`, `urgency`, `draft_response`, `final_response`, `status` (pending/approved/sent/auto_sent/rejected/ignored/handled/queued/failed), `approved_by`, `matched_customer_id`, `match_method` (email/contact_email/previous_match/domain/sender_name/body_name/display_name_subject/etc.), `delivered_to`, `thread_id`, `received_at`.

### AgentAction (`agent_actions`)
Job/action items extracted from emails or created manually. Key fields: `agent_message_id`, `thread_id`, `customer_id`, `case_id`, `parent_action_id` (for follow-up chains), `action_type` (follow_up/bid/schedule_change/site_visit/callback/repair/equipment/invoice/other), `description`, `assigned_to`, `due_date`, `job_path` (internal/customer), `status` (open/in_progress/done/suggested/cancelled/pending_approval/approved), `is_suggested`, `suggestion_confidence`, `created_by`, `task_count`, `tasks_completed`. Has child relationships: `AgentActionComment`, `AgentActionTask`.

### AgentActionComment (`agent_action_comments`)
Comments on jobs. `author` (user name or "DeepBlue"), `text`. `@DeepBlue` prefix triggers AI pipeline. `[DRAFT_EMAIL]` prefix marks AI-generated email drafts.

### AgentActionTask (`agent_action_tasks`)
Subtasks within a job. `title`, `assigned_to`, `status` (open/done/cancelled), `sort_order`, `completed_at`, `completed_by`.

### AgentCorrection (`agent_corrections`)
Records of human corrections to AI outputs. `agent_type` (8 types), `correction_type` (edit/rejection/acceptance), `original_output`, `corrected_output`, `input_context`, `category`, `customer_id`, `applied_count`, `last_applied_at`.

### BroadcastEmail (`broadcast_emails`)
Tracks bulk email sends. `subject`, `body`, `filter_type`, `filter_data`, `recipient_count`, `sent_count`, `failed_count`, `status` (sending/completed), `created_by`, `completed_at`.

### InboxRoutingRule (`inbox_routing_rules`)
Configurable routing and blocking rules. `match_field` (from/to), `match_type` (exact/contains), `address_pattern`, `action` (route/block), `priority`, `required_permission`, `category`.

### MessageAttachment (`message_attachments`)
File attachments on outbound emails. `source_type`, `source_id`, `filename`, `stored_filename`, `mime_type`, `file_size`.

## Relationships

```
Organization
    |
    +---> AgentThread (many)
    |         |
    |         +---> AgentMessage (many, ordered by received_at)
    |         +---> AgentAction (many)
    |         +---> ServiceCase (optional FK)
    |         +---> InboxRoutingRule (optional FK)
    |         +---> User (assigned_to)
    |
    +---> AgentAction (many)
    |         |
    |         +---> AgentActionComment (many)
    |         +---> AgentActionTask (many)
    |         +---> AgentMessage (optional FK, source email)
    |         +---> AgentAction (parent_action_id, follow-up chain)
    |         +---> ServiceCase (optional FK)
    |         +---> Customer (optional FK)
    |
    +---> AgentCorrection (many)
    +---> BroadcastEmail (many)
    +---> InboxRoutingRule (many)
```

## API endpoints

### Threads (`/v1/admin/agent-threads`)
- `GET /` — list threads (with filtering, search, pagination)
- `GET /stats` — thread counts by status
- `GET /{id}` — thread detail with messages
- `POST /{id}/approve` — edit draft and send reply
- `POST /{id}/dismiss` — mark thread as handled without reply
- `POST /{id}/archive` — archive thread
- `DELETE /{id}` — delete thread
- `POST /{id}/assign` — assign thread to user
- `POST /{id}/save-draft` — save draft response
- `POST /{id}/send-followup` — send follow-up email
- `POST /{id}/revise-draft` — AI revise existing draft
- `POST /{id}/draft-followup` — AI generate follow-up draft
- `PATCH /{id}/visibility` — change thread visibility permission
- `POST /{id}/create-case` — create ServiceCase from thread
- `POST /{id}/create-job` — create AgentAction from thread
- `POST /{id}/draft-estimate` — AI draft estimate from thread
- `GET /{id}/contact-prompt` — get contact learning suggestion
- `POST /{id}/save-contact` — save sender as customer contact
- `GET /client-search` — search customers for manual matching
- `PUT /contact-learning` — update contact learning settings
- `GET /contact-learning` — get contact learning settings
- `POST /dismiss-contact-prompt` — dismiss contact suggestion

### Messages (`/v1/admin/agent-messages`)
- `GET /` — list messages (with filtering)
- `GET /agent-stats` — message counts and category breakdown
- `GET /{id}` — message detail
- `POST /{id}/approve` — approve and send draft
- `POST /{id}/reject` — reject message
- `POST /{id}/dismiss` — dismiss message
- `DELETE /{id}` — delete message
- `POST /{id}/draft-followup` — AI draft follow-up
- `POST /{id}/send-followup` — send follow-up email
- `POST /{id}/revise-draft` — AI revise draft

### Jobs (`/v1/admin/agent-actions`)
- `GET /` — list jobs (with status/type/assignee/customer filters)
- `POST /` — create job (supports customer-path with auto estimate)
- `POST /{id}/send-estimate` — send estimate email to customer
- `PUT /{id}` — update job (status, assignment, description, notes)
- `POST /{id}/link-invoice` — link invoice/estimate to job
- `DELETE /{id}/link-invoice/{invoice_id}` — unlink invoice
- `GET /{id}` — job detail with comments, tasks, related jobs
- `POST /{id}/comments` — add comment (triggers @DeepBlue AI pipeline)
- `POST /{id}/approve-suggestion` — approve AI-suggested follow-up
- `POST /{id}/dismiss-suggestion` — dismiss AI-suggested follow-up
- `POST /{id}/draft-invoice` — AI-generate invoice line items
- `GET /{id}/tasks` — list subtasks
- `POST /{id}/tasks` — create subtask
- `PUT /{id}/tasks/{task_id}` — update subtask
- `DELETE /{id}/tasks/{task_id}` — delete subtask

### Email compose (`/v1/email`)
- `POST /compose` — compose and send new email
- `POST /draft` — AI generate draft
- `GET /customer-context/{id}` — customer context for compose
- `POST /draft-correction` — record draft correction for learning
- `GET /templates` — list email templates
- `GET /templates/all` — list all templates
- `POST /templates` — create template
- `PUT /templates/{id}` — update template
- `DELETE /templates/{id}` — delete template

### Inbound webhooks (`/v1/inbound-email`)
- `POST /webhook/{org_slug}` — receive inbound email from any provider

### Inbox routing (`/v1/inbox-routing`)
- `GET /` — list routing rules
- `POST /` — create rule
- `PUT /{id}` — update rule
- `DELETE /{id}` — delete rule

## Agent learning

Every AI agent in the pipeline learns from human corrections via `AgentLearningService`:

1. **Before generating**: `build_lessons_prompt()` injects up to 8 relevant past corrections into the system prompt. Prioritization: same customer > same category > general. 90-day window.
2. **After human action**: corrections are recorded:
   - `edit` — human modified the AI draft before sending
   - `rejection` — human dismissed the AI output
   - `acceptance` — human approved unchanged (low signal, only recorded with category)
3. **Agent types**: `email_classifier`, `email_drafter`, `deepblue_responder`, `command_executor`, `job_evaluator`, `estimate_generator`, `customer_matcher`, `equipment_resolver`
4. **Effectiveness tracking**: `applied_count` and `last_applied_at` on each correction record

The classifier also has its own inline correction history via `get_correction_history()`: it loads edited drafts (where `final_response != draft_response`), rejected messages, and past exchanges with the same sender.

## Broadcasting

Bulk email via `BroadcastService`:

1. Filter customers: `all_active`, `commercial`, `residential`, `custom` (specific IDs), `test` (arbitrary address)
2. For each recipient, `EmailComposeService.compose_and_send()` creates full tracking records (AgentMessage + AgentThread)
3. Sends synchronously (no background queue yet)
4. Records sent/failed counts on `BroadcastEmail`
5. Also available via DeepBlue's `draft_broadcast_email` tool (preview + confirm flow)

## Configuration

### Environment variables

| Variable | Purpose |
|----------|---------|
| `AGENT_GMAIL_USER` | Gmail address for IMAP polling |
| `AGENT_GMAIL_PASSWORD` | Gmail app password |
| `AGENT_IMAP_HOST` | IMAP server (default: imap.gmail.com) |
| `AGENT_SMTP_HOST` | SMTP server (default: smtp.gmail.com) |
| `AGENT_SMTP_PORT` | SMTP port (default: 587) |
| `AGENT_FROM_EMAIL` | Default sender address |
| `AGENT_FROM_NAME` | Default sender display name |
| `AGENT_LOCATION` | Company location for classifier context |
| `ANTHROPIC_API_KEY` | Claude API key for all AI agents |
| `POSTMARK_SERVER_TOKEN` | Postmark API token (if set, overrides SMTP) |

### Organization-level config

| Field | Purpose |
|-------|---------|
| `agent_enabled` | Enable email polling for this org |
| `agent_from_email` | Org-specific sender address |
| `agent_from_name` | Org-specific sender name |
| `agent_signature` | Org email signature block |
| `agent_tone_rules` | Custom tone guidelines for AI drafts |

### Routing rules (DB-configurable)

Rules are stored in `inbox_routing_rules` and evaluated at email ingestion time:
- **Block rules** (`match_field='from'`, `action='block'`): silently drop emails from matching senders/domains
- **Route rules** (`match_field='to'`): set `visibility_permission` on new threads based on the `Delivered-To` address, controlling who can see the thread in the inbox

### Safety mechanisms

- **Reply loop prevention**: own addresses, no-reply patterns, internal team patterns
- **Flood protection**: SMS alert cooldown (10 min per sender)
- **Business hours**: SMS alerts suppressed outside 7 AM - 8 PM Pacific, weekdays only
- **Customer override**: emails from known customers are never auto-ignored, even if classified as spam/no_response
- **Action dedup**: word overlap > 50% or same address+type skips duplicate action creation
- **Max 3 actions per email**: hard cap on extracted action items
- **Fuzzy match verification**: Claude Haiku QC check on non-trusted customer match methods

## Systemd services

- `quantumpools-agent.service` — runs `agent_poller.py`, polls every 60s, heartbeat every 30 cycles
- Also handles: estimate reminders (hourly), internal message escalations (every 5 min), stale visit auto-close (every 30 min)

## Planned enhancements

See `docs/ai-agents-plan.md` and memory files:
- Postmark inbound webhooks (replacing IMAP polling) — `memory/plan-postmark-migration.md`
- CC capture on inbound emails
- Multi-sender thread handling
- Background send queue (currently synchronous)
- Per-org storage quotas for attachments
