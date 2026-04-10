# Email Strategy

## Vision

QuantumPools is **an email-aware customer system**, not an email server. Each organization has its own existing email infrastructure (Gmail, Outlook, custom domain) and QP integrates with that infrastructure to provide AI-powered customer intelligence on top of it.

The unifying concept: **emails create `AgentMessage` records in the database, regardless of where they originally came from**. Cases, jobs, threads, customer history all link to `AgentMessage` records — they don't care about the source. This means we can support multiple email integration modes per organization without breaking the data model.

## Why this matters

Building an email server is a years-long engineering effort. Spam filtering alone is solved by Gmail and Microsoft using ML trained on billions of inboxes. We can't replicate it. We shouldn't try.

Instead, we let the customer's existing email provider do what it does well (filtering, mobile apps, search, deliverability) and we layer customer intelligence on top: AI matching, case linking, action extraction, team collaboration, role-based visibility.

This is exactly how **Front, Help Scout, HubSpot, Missive, Zendesk, Intercom** all work. None of them are email servers. All of them integrate with whatever the customer already has.

## The product positioning

**For users who want a one-stop shop:** QP becomes their full email client. They open QP and see everything — full email management, plus AI customer intelligence, plus job creation, plus case tracking. No need to switch between QP and Gmail.

**For users who want to keep their existing email client:** QP shows only customer-related emails alongside customer records. They keep using Gmail/Outlook for general email, and QP shows them the customer-relevant subset with rich context.

**Same data model, two UI modes.** User picks per-account preference.

## Multi-mode email architecture

Each organization picks an integration mode during onboarding:

| Mode | Who it's for | Inbound | Outbound | Status |
|------|-------------|---------|----------|--------|
| **Gmail / Workspace** | Most small businesses | Gmail API + Pub/Sub push | Gmail API (appears in user's Sent folder) | Planned |
| **Outlook / Microsoft 365** | Larger orgs, professional services | MS Graph API + webhooks | MS Graph API | Planned |
| **Forwarding** | Anyone with any email provider | Customer sets forwarding rule to `org-{id}@inbound.quantumpoolspro.com` | Postmark with verified sender domain | Built (foundation) |
| **Managed (we host)** | New businesses, no existing email | Cloudflare Email Routing → Workers → webhook | Postmark | Built (Sapphire Pools is on this) |
| **Manual** | No email integration desired | None — manual entry only | None | Trivial |

## Why each mode exists

- **Gmail/MS Graph modes** — covers 90%+ of business email users. OAuth-based, two-way sync, full read/write. Best UX, best deliverability (their reputation), no spam handling needed.

- **Forwarding mode** — universal fallback for customers on weird setups (Zoho, FastMail, custom IMAP servers, white-label hosts). Set-and-forget for the customer. Works with any mail provider that supports server-side forwarding.

- **Managed mode** — for new businesses without existing infrastructure, or as an upsell ("we handle your email"). Includes the full pipeline: DNS setup, MX, DKIM, Postmark sending, Cloudflare Workers receiving. Sapphire Pools currently runs on this.

- **Manual mode** — for customers who don't want any email integration and just want to use QP for cases/jobs.

## What stays the same regardless of mode

- `AgentMessage` model (source-agnostic)
- `AgentThread` model
- `AgentAction` (jobs)
- `ServiceCase` linkage
- Customer matching pipeline
- AI classification and triage
- Permission-based inbox visibility
- DeepBlue context awareness
- Real-time updates via WebSocket
- Routing rules (`inbox_routing_rules`)
- Postmark for **transactional** outbound (invoices, estimates, notifications) regardless of mode

## What changes per mode

- **Inbound source**: webhook (Cloudflare/Postmark/Forwarding) vs Gmail API vs MS Graph
- **Outbound destination**: Postmark vs Gmail API vs MS Graph (for replies — transactional always Postmark)
- **Read state sync**: managed = local only, Gmail/MS = bidirectional
- **Storage**: Gmail/MS = lazy fetch (snippets cached, full body on demand), managed = full body in DB

## Permissions (role-based inbox visibility)

The permission system already supports per-address visibility. Each `AgentThread` is stamped with a `visibility_permission` slug based on routing rules. Users only see threads matching their permissions. Owners always see everything.

**Example for Sapphire Pools (or any org with multiple addresses):**

| Email address | Visible to |
|--------------|------------|
| `contact@sapphire-pools.com` | All staff (general inbox) |
| `accounting@sapphire-pools.com` | Owner, Admin, Bookkeeper only |
| `billing@sapphire-pools.com` | Owner, Admin, Bookkeeper only |
| `kim@sapphire-pools.com` | Owner, Kim only (personal) |
| `chance@sapphire-pools.com` | Owner, Chance only (personal) |

This works identically across all integration modes — the routing rules are stored in the DB and applied at thread creation time.

## SaaS implications

- **Pricing tiers**: managed mode costs us ~$15/month per org (Postmark). Gmail/MS modes cost us $0. SaaS pricing should reflect: managed mode is a paid add-on or premium tier feature.
- **Onboarding wizard**: new orgs pick their email mode during signup. Different setup flows per mode.
- **DNS verification per org**: for orgs that want to send from their own domain via Postmark (forwarding/managed modes), we need a DNS verification flow.
- **OAuth scopes**: Gmail/MS require OAuth. We need a clear privacy policy explaining what we access (read/send email, marked read, applied labels).
- **Compliance**: accessing user email is sensitive. We need security review, encryption at rest for tokens, audit logging, ability to disconnect.

## What we lost by going self-hosted (Sapphire Pools today)

- Gmail's spam filtering (ML across billions of inboxes)
- Phishing/malware detection
- Mobile push notifications (Gmail apps)
- Industry-leading search
- Calendar integration
- Drafts, scheduled send, snooze, undo send, vacation responder
- Backup & archival (15+ years on Gmail)
- Multi-device sync
- Compliance certifications

These are why we want Gmail mode for Sapphire Pools, even though the managed mode works.

## Decision log

- **2026-04-09**: Migrated Sapphire Pools off Gmail to Cloudflare Workers + Postmark. Solved the silent IMAP failures, gained Postmark deliverability for outbound, but lost Gmail's filtering. Marked as "managed mode" — one of several supported modes.
- **2026-04-10**: Decided to add Gmail API integration (and eventually MS Graph) so customers can keep their existing email client AND get QP's customer intelligence. Sapphire Pools will switch to Gmail mode when built.
