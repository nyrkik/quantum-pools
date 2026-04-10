# Sapphire Pool Service — Email Recovery Plan

## Context

Sapphire Pool Service is a DBA under BESC Enterprises Inc. Sapphire is a **customer** of Quantum Pools, not part of QP infrastructure. See CLAUDE.md "Business Context" for the entity distinction.

On 2026-04-09, in an attempt to fix silent IMAP polling failures, Sapphire's email was migrated to "managed mode" — Cloudflare Email Workers receiving inbound, Postmark sending outbound, MX records pointing to Cloudflare. This was a mistake in retrospect: Sapphire is a customer, and customers should run their own email through their own provider. The managed-mode infrastructure is reusable as a future QP product feature for customers without existing email, but Sapphire shouldn't be on it.

This document is the plan to revert Sapphire to a normal customer email setup (Google Workspace) and re-integrate with QP via the standard Gmail integration path (which is being built as Phase 5b.2).

## Goal

Sapphire's email runs entirely on Google Workspace, owned and operated by Sapphire (the BESC entity). QP integrates with Sapphire's Google Workspace via OAuth (Phase 5b.2), exactly as QP will integrate with every other customer's Gmail.

## Phases

### Phase A — Upgrade Sapphire to Google Workspace (immediate, ~30 min)

1. Sign up for Google Workspace at workspace.google.com using `sapphpools@gmail.com` as the recovery email
2. Choose Business Starter ($6/user/month per user — Brian, Kim, Chance, accounting, etc.)
3. Verify domain ownership — Google will provide a TXT record to add to Cloudflare DNS
4. Create user accounts:
   - `brian@sapphire-pools.com`
   - `kim@sapphire-pools.com`
   - `chance@sapphire-pools.com`
   - `contact@sapphire-pools.com` (or a Google Group routing to multiple users)
   - `accounting@sapphire-pools.com` (or a Google Group routing to bookkeeper + Brian)
   - `billing@sapphire-pools.com` (or a Google Group)
5. Configure each user's mailbox forwarding settings if needed (e.g., contact@ → all staff)

### Phase B — Revert Sapphire DNS to Google MX (~10 min)

Once Workspace is active:

1. **Cloudflare Email Routing → disable** (currently enabled with worker rules)
2. **Cloudflare DNS → MX records:** delete the three `route1/2/3.mx.cloudflare.net` MX records
3. **Cloudflare DNS → MX records:** add Google's MX records:
   ```
   MX  @  smtp.google.com.  priority 1
   ```
   (Workspace has simplified to a single MX target as of late 2023)
4. **Cloudflare DNS → DKIM:** Workspace will provide a DKIM record to add (TXT, `google._domainkey`)
5. **Cloudflare DNS → SPF:** update to include Google
   ```
   v=spf1 include:_spf.google.com include:spf.mtasv.net ~all
   ```
   (Keeping Postmark `spf.mtasv.net` for now if QP still sends on Sapphire's behalf during transition. Can remove later.)
6. **Cloudflare DNS → DMARC:** keep existing `_dmarc` record at `p=none`

### Phase C — Decommission QP-side Sapphire infrastructure (~5 min)

1. **Cloudflare Email Worker:** delete or disable `sapphire-pools-email` worker (or keep deployed for testing as managed-mode reference)
2. **Postmark webhook config:** clear the inbound webhook URL from the Postmark server (optional — won't fire without MX pointing to Postmark)
3. **QP `EmailIntegration` record for Sapphire org:** when Phase 5b.1 builds the model, Sapphire's record should be created as `type='manual'` until Phase 5b.2 connects Gmail OAuth

### Phase D — Interim period (until Phase 5b.2 ships)

Between Workspace active and Gmail API integration available:

- Brian uses Gmail/Workspace as his email client (mobile, web, desktop)
- Customer emails do NOT automatically appear in QP's inbox (QP has no integration yet)
- For high-priority customer emails that need to be tracked in QP: manually create `AgentMessage` records via the compose UI, OR set up a Gmail filter to forward customer-related emails to a temporary QP webhook address (see next section)

**Optional bridge: Gmail filter forwarding**

If having customer emails appear in QP during the gap is critical:

1. In Sapphire's Gmail Workspace, create a filter rule
2. Filter: emails from senders matching customer domains (or apply to all)
3. Action: forward to `org-sapphire@inbound.quantumpoolspro.com` (this address needs to be set up — Phase 5b.5 forwarding mode infrastructure)
4. Mark forwarded emails with a label so it's clear they're being captured

This is a stop-gap. Once Phase 5b.2 ships, OAuth integration replaces it.

### Phase E — Connect Gmail to QP via OAuth (Phase 5b.2 build)

Once Gmail API integration ships:

1. Brian logs into QP, goes to Settings → Email
2. Clicks "Connect Gmail" (the OAuth flow)
3. Grants `gmail.modify` scope on `brian@sapphire-pools.com`
4. Initial sync pulls the last 30 days of email into `AgentMessage` records
5. Real-time sync via Pub/Sub starts
6. Sapphire is now a normal QP customer with full Gmail integration

After Phase E, Sapphire's setup is identical to what every other QP customer will have. The recovery is complete.

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
