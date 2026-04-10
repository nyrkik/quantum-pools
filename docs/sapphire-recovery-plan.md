# Sapphire Pool Service — Email Recovery Plan

## Context

Sapphire Pool Service is a DBA under BESC Enterprises Inc. Sapphire is a **customer** of Quantum Pools, not part of QP infrastructure. See CLAUDE.md "Business Context" for the entity distinction.

On 2026-04-09, in an attempt to fix silent IMAP polling failures, Sapphire's email was migrated to "managed mode" — Cloudflare Email Workers receiving inbound, Postmark sending outbound, MX records pointing to Cloudflare. This was a mistake in retrospect: Sapphire is a customer, and customers should run their own email through their own provider. The managed-mode infrastructure is reusable as a future QP product feature for customers without existing email, but Sapphire shouldn't be on it.

This document is the plan to revert Sapphire to a normal customer email setup (Google Workspace) and re-integrate with QP via the standard Gmail integration path (which is being built as Phase 5b.2).

## Decisions made (2026-04-10)

- **Approach**: Choice 1 — build Phase 5b.2 (Gmail OAuth + API integration) properly, no interim BCC hacks. Sapphire will be the first customer on Gmail mode.
- **Workspace plan**: Business Starter at $6/user/month, **3 paid seats** = $18/month
- **Users**: `brian@`, `kim@`, `chance@` as paid seats
- **Shared addresses**: Google Groups (free), routing to the appropriate users:
  - `contact@sapphire-pools.com` → brian + kim + chance
  - `accounting@sapphire-pools.com` → brian (+ bookkeeper later)
  - `billing@sapphire-pools.com` → brian (+ bookkeeper later)
- **Outbound strategy**: Option A — Postmark for QP-initiated transactional (invoices, estimates, AI replies, automated notifications), Workspace for human-initiated outbound. Both authorized via SPF + DKIM. After Phase 5b.2 ships, QP will also call Gmail API `messages.insert(labelIds: ['SENT'])` so QP-sent replies appear in user's Gmail Sent folder.
- **Gap period**: Between Workspace setup and Phase 5b.2 ship (~3 days), customer emails arrive in Workspace but do NOT auto-flow into QP. Brian uses Gmail as his email client. Manual case/job creation in QP for high-priority customer emails. No interim bridge built — keep architecture clean.
- **Phase 5b.2 timing**: This weekend (2026-04-12 or 2026-04-13). Detailed build plan to be laid out then.

## Goal

Sapphire's email runs entirely on Google Workspace, owned and operated by Sapphire (the BESC entity). QP integrates with Sapphire's Google Workspace via OAuth (Phase 5b.2), exactly as QP will integrate with every other customer's Gmail.

## Phases

### Phase A — Upgrade Sapphire to Google Workspace (Brian's action, ~30 min)

1. Sign up at workspace.google.com:
   - Business name: Sapphire Pool Service
   - Region: US
   - Existing email for contact: `sapphpools@gmail.com`
   - Domain: `sapphire-pools.com` (choose "I have a domain")
   - Primary username: `brian@sapphire-pools.com`
   - Plan: **Business Starter** ($6/user/month)
2. **Pause at the "verify your domain" step.** Google will provide a TXT record. Send the value to Claude — Claude will add it via Cloudflare API (don't try to add it manually in Cloudflare while routing rules are still in place).
3. After domain verified, **add 2 more paid users**:
   - `kim@sapphire-pools.com`
   - `chance@sapphire-pools.com`
   - (3 paid seats total = $18/month)
4. **Skip the MX setup step** Google offers — Claude will do that via Cloudflare API after Workspace is fully set up.
5. After all users are added, **create Google Groups** (free, no extra cost):
   - `contact@sapphire-pools.com` → brian + kim + chance
   - `accounting@sapphire-pools.com` → brian (bookkeeper added later)
   - `billing@sapphire-pools.com` → brian (bookkeeper added later)
6. Tell Claude when complete — Claude proceeds to Phase B.

### Phase B — Revert Sapphire DNS (Claude's action via Cloudflare API, ~10 min)

Once Workspace is active and Brian has added users + groups:

1. Disable Cloudflare Email Routing on `sapphire-pools.com` zone (delete-and-disable, since we're moving to Google entirely)
2. Delete the three Cloudflare MX records (`route1/2/3.mx.cloudflare.net`)
3. Add Google's MX record:
   ```
   MX  @  smtp.google.com.  priority 1
   ```
4. Add Google DKIM TXT record (Brian provides the `google._domainkey` value from Workspace admin → Apps → Gmail → Authenticate Email)
5. Update SPF to authorize Google (and KEEP Postmark for QP transactional outbound):
   ```
   v=spf1 include:_spf.google.com include:spf.mtasv.net ~all
   ```
6. Keep existing `_dmarc` at `p=none`
7. Verify with `dig MX sapphire-pools.com @8.8.8.8` and other resolvers
8. Send a test email to `brian@sapphire-pools.com` from another account, verify arrival in Workspace

### Phase C — Decommission QP-side Sapphire infrastructure (Claude's action, ~5 min)

1. Delete or disable `sapphire-pools-email` Cloudflare Worker (recommend: leave deployed but disabled, useful as managed-mode reference)
2. Clear Postmark inbound webhook URL config (won't fire without MX pointing to Postmark anyway, but clean up)
3. When Phase 5b.1 builds the `EmailIntegration` model: create Sapphire's record as `type='manual'` until Phase 5b.2 OAuth connects → upgrades to `type='gmail_api'`

### Phase D — Gap period (target: ~3 days, until Phase 5b.2 ships this weekend)

Between Workspace active and Gmail API integration available:

- Brian uses Gmail Workspace as his email client (full features: mobile, web, desktop, search, spam filtering)
- Customer emails do NOT automatically appear in QP's inbox (QP has no integration yet)
- For high-priority customer emails that need to be linked to a case/job in QP: manually create them in QP via the compose UI
- QP continues to send transactional outbound (invoices, estimates, automated emails) via Postmark — no change to that flow

**Decision (2026-04-10): no interim bridge.** No BCC hack, no Gmail filter forwarding, no temporary worker. Live with the manual gap for ~3 days. Reason: keeps the architecture clean, no throwaway code, no double migration when Phase 5b.2 ships.

### Phase E — Connect Gmail to QP via OAuth (Phase 5b.2 build, this weekend)

Phase 5b.2 build target: 2026-04-12 / 2026-04-13. After it ships:

1. Brian logs into QP → Settings → Email
2. Clicks "Connect Gmail" (OAuth flow)
3. Grants `gmail.modify` scope on `brian@sapphire-pools.com`
4. Initial sync pulls last 30 days of email into `AgentMessage` records
5. Real-time sync via Pub/Sub push notifications begins
6. **Two-way write enabled**: QP-sent replies use `messages.insert(labelIds: ['SENT'])` so they appear in Brian's Gmail Sent folder alongside his manually-sent emails
7. AI customer matching, case linking, action extraction all resume

After Phase E, Sapphire's setup is identical to what every other QP customer will have. The recovery is complete.

**Phase 5b.2 detailed build plan**: to be written when work begins. See `docs/email-integrations-plan.md` Phase 5b.2 section for the high-level scope.

## What QP keeps from the 2026-04-09 work

Even though Sapphire is being removed from managed mode, none of the code is wasted:

- `inbound_email_service.py` — provider-agnostic webhook ingestion. Will get a `_parse_gmail_api()` parser added in Phase 5b.2.
- Cloudflare Email Worker (`email-worker/`) — becomes the **managed mode** product feature for future customers without existing email. Stays deployed as reference.
- Postmark integration — continues for outbound transactional emails (invoices, estimates, notifications) on QP's own domain (`quantumpoolspro.com`) and any customer who chooses managed mode.
- `postmark_message_id` and `delivery_error` columns on `AgentMessage` — used by all modes.
- Sentry + ntfy monitoring — applies to all modes.
- Bounce/delivery webhook handlers — applies to all Postmark sending.

## Costs after Phase B

| Item | Cost | Owner |
|------|------|-------|
| Google Workspace Business Starter | $6/user/mo | Sapphire (BESC) |
| Postmark (outbound from QP product) | $15/mo (10k emails) | QP (eventually QP LLC) |
| Cloudflare DNS | Free | Sapphire owns sapphire-pools.com |
| Cloudflare Email Workers | Decommissioned | — |

## Open questions for Brian

1. How many Workspace seats does Sapphire need? (Brian + Kim + Chance + bookkeeper = 4 seats minimum)
2. Should `accounting@` and `billing@` be Google Groups (free) or full user accounts ($6 each)?
3. Should the Postmark account move from QP-as-VVG-LLC to QP-as-new-LLC during entity formation?
4. Does QP need its own Workspace for `@quantumpoolspro.com` (sales@, support@, billing@)? Likely yes — separate from Sapphire entirely.

## Order of operations recommendation

1. **Today**: Phase A (upgrade Sapphire Workspace) + Phase B (revert MX). Brian gets working email immediately.
2. **Today**: Phase C (clean up Cloudflare Worker rules so they don't dual-deliver).
3. **This week**: form Quantum Pools LLC (separate from VVG and BESC).
4. **Next week**: set up `@quantumpoolspro.com` Workspace under new LLC.
5. **Phase 5b.1-5b.2 build**: ~3 weeks of focused work.
6. **Phase E**: Sapphire connects via OAuth, recovery complete.
