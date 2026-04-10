# Sapphire Pools — Gmail Hybrid Setup (Phase 0)

This document walks through getting Sapphire Pools onto a hybrid email setup: emails go to BOTH Gmail (for spam filtering, mobile, search) AND the QuantumPools webhook (for AI processing, customer linking, case management).

## Why this is a hybrid

- **Inbound**: Cloudflare receives emails and dispatches them to TWO destinations: Gmail (`sapphpools@gmail.com`) and our QP webhook
- **Outbound**: Postmark continues to handle outbound from QP. If you send via Gmail directly, that email won't be tracked by QP (acceptable tradeoff for now)
- **Read state**: Marking read in Gmail does NOT mark read in QP, and vice versa. Two separate UIs.

## What you gain

- Gmail's spam filtering (huge — biggest gap in current setup)
- Gmail's mobile apps with push notifications
- Gmail's search
- Gmail's calendar integration
- Gmail's offline access
- Gmail's drafts, scheduled send, snooze, undo send
- Gmail's backup (15+ years)
- Gmail's compliance certifications

## What you give up (vs full Gmail integration)

- Two-way read sync (Phase 2 will fix this)
- Replies sent from Gmail bypass QP outbound logic (no signature, no tracking, no AgentMessage record)
- Replies sent from QP don't appear in Gmail Sent folder (Phase 2 will fix this)
- Two inboxes to check during transition (Phase 3 redesign will eliminate this)

## What stays exactly the same

- Postmark continues to send all transactional outbound (invoices, estimates, notifications, AI replies from QP)
- All AI processing, customer matching, case linking, action extraction continues
- All routing rules and visibility permissions continue
- All current automations continue

## Setup steps

### Step 1: Update Cloudflare Email Routing rules

Currently each rule sends to the worker only. We need to add Gmail as a second destination.

**Cloudflare → Email → Email Routing → Routing rules**

For each of these rules:
- `contact@sapphire-pools.com`
- `brian@sapphire-pools.com`
- `kim@sapphire-pools.com`
- `chance@sapphire-pools.com`
- Catch-all

Edit each rule:
1. Click **Edit**
2. Click **Add Action**
3. Select **Send to an email**
4. Enter `sapphpools@gmail.com`
5. Save

After this, each rule has TWO actions: send to worker AND send to Gmail.

### Step 2: Verify in Gmail

1. Open `sapphpools@gmail.com`
2. Send a test email from a different account to `contact@sapphire-pools.com`
3. Verify it arrives in Gmail
4. Verify it ALSO appears in QP inbox

### Step 3: Re-enable Gmail filters (optional)

Gmail's smart features (spam, important, categories) work automatically. If you had any custom Gmail filters before, re-enable them now.

### Step 4: Update team workflow

Tell the team:
- **Customer-facing emails (replies, drafts)**: still use QP — keeps tracking, signature, customer linking
- **Personal/internal emails**: use Gmail directly
- **Spam check**: Gmail will catch most of it; QP inbox will get the cleaned set
- **Mobile**: use Gmail app for notifications, switch to QP web for customer context

## Alternative: Worker-side fan-out

Instead of changing Cloudflare routing rules, we could modify the Cloudflare Worker to forward to Gmail after POSTing to the webhook. This keeps the routing config simpler but adds code complexity.

**Pros:**
- Single routing rule per address (simpler config)
- Worker can apply business logic before forwarding (e.g., suppress auto-replies)

**Cons:**
- Worker code becomes responsible for forwarding reliability
- Cloudflare's routing handles delivery retries automatically

**Recommendation:** use the routing-rule approach (Step 1 above) for simplicity.

## When to remove this hybrid

Once Phase 2 (Gmail API integration) is complete:

1. Connect Sapphire's Gmail account via OAuth in QP
2. Initial sync pulls all email into AgentMessage records
3. Switch to Gmail mode in EmailIntegration settings
4. Remove the Cloudflare worker forwarding rules
5. Cloudflare MX → Google MX (point directly to Google's mail servers)
6. Disable Cloudflare Email Routing entirely

At that point Gmail is the underlying source, QP reads/writes via Gmail API, and the user gets a unified experience.

## Rollback plan

If anything breaks during the hybrid setup:
1. Cloudflare → Email Routing → Routing rules
2. Remove the worker actions, keep only the Gmail actions
3. Result: emails go to Gmail only, QP stops receiving new emails
4. QP's existing data is unchanged — you just stop ingesting new email
5. We can re-enable the worker actions whenever ready

The DNS, MX, DKIM, SPF, and Postmark setup all stay in place — they're correct as-is.

## DNS state during hybrid

No DNS changes needed. Current state is correct:
- MX → Cloudflare's mail routes (route1/2/3.mx.cloudflare.net)
- DKIM (Postmark + Cloudflare): for outbound signing
- SPF: includes both Postmark and Cloudflare
- DMARC: monitor mode (`p=none`)

This stays the same throughout the hybrid period.
