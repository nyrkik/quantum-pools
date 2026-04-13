# Sapphire → Gmail Migration Playbook

> **Goal:** Move Sapphire's inbound email from managed mode (Cloudflare Workers → Postmark → QP) to **Gmail as the canonical store**. QP becomes the intelligence layer that syncs from Gmail.
>
> **Why:** Mail currently sent to `accounting@sapphire-pools.com`, `contact@sapphire-pools.com`, etc., lives ONLY in QP's database (and Postmark's 45-day archive). If QP is wiped, those emails are unrecoverable. Gmail keeps them durably.
>
> **Removal note:** Delete this doc once migration is complete and verified.

---

## Current State (verified 2026-04-13)

| Item | Value |
|---|---|
| DNS | Cloudflare (newt.ns.cloudflare.com, sarah.ns.cloudflare.com) |
| MX records | Cloudflare Email Workers (route1/2/3.mx.cloudflare.net) |
| SPF | `v=spf1 include:spf.mtasv.net include:_spf.mx.cloudflare.net ~all` |
| Inbound flow | Sender → Cloudflare MX → CF Worker → Postmark webhook → QP |
| Gmail account | `sapphpools@gmail.com` (Gmail Workspace, primary inbox) |
| QP integration | OAuth Gmail integration connected, syncing `sapphpools@gmail.com` only |
| Custom addresses | `accounting@`, `contact@` exist; route via managed mode (NOT Gmail) |

## Target State

| Item | Value |
|---|---|
| MX records | Google Workspace (`ASPMX.L.GOOGLE.COM` etc.) |
| SPF | `v=spf1 include:_spf.google.com ~all` |
| Inbound flow | Sender → Google MX → Gmail (sapphpools@gmail.com via aliases) → QP syncs from Gmail |
| All Sapphire addresses | Aliases for `sapphpools@gmail.com`: `accounting@`, `contact@`, `info@`, etc. |
| Cloudflare Workers | Decommissioned (kept dormant 7 days as fallback, then removed) |
| Postmark | Outbound only (transactional sending if needed); no inbound |

---

## Migration Steps

### Pre-flight (do BEFORE any DNS changes)

**1. Verify domain in Google Workspace**
- Sign in to admin.google.com as a Workspace admin
- Account → Domains → Add domain → enter `sapphire-pools.com`
- Verify ownership via TXT record (Google provides it)
- Add the TXT record in Cloudflare DNS, wait for verification

**2. Set up email aliases**
- Admin console → Users → click `sapphpools@gmail.com` user
- User information → Email aliases → Add aliases:
  - `accounting@sapphire-pools.com`
  - `contact@sapphire-pools.com`
  - `billing@sapphire-pools.com` (if needed)
  - any other addresses you use
- Wait ~5 minutes for aliases to propagate

**3. Lower MX TTL** (24 hours before cutover)
- Cloudflare DNS dashboard → sapphire-pools.com → MX records
- Change TTL on each MX record from `Auto` to `1 hour` (3600 seconds)
- Save. Wait at least 24 hours before next step. This shortens the window where mail could double-route.

### Cutover (the actual switch)

**4. Update MX records**
- Cloudflare DNS → MX records
- Delete the three Cloudflare MX entries (route1/2/3.mx.cloudflare.net)
- Add Google MX records:

| Priority | Mail Server |
|---|---|
| 1 | ASPMX.L.GOOGLE.COM |
| 5 | ALT1.ASPMX.L.GOOGLE.COM |
| 5 | ALT2.ASPMX.L.GOOGLE.COM |
| 10 | ALT3.ASPMX.L.GOOGLE.COM |
| 10 | ALT4.ASPMX.L.GOOGLE.COM |

- Set TTL to `Auto` (default) once verified working

**5. Update SPF record**
- Cloudflare DNS → TXT records
- Find existing SPF: `v=spf1 include:spf.mtasv.net include:_spf.mx.cloudflare.net ~all`
- If you still send transactional via Postmark (invoices, etc.), keep `spf.mtasv.net`. Otherwise drop it.
- Add Google: `v=spf1 include:_spf.google.com include:spf.mtasv.net ~all`
  - (Drop `_spf.mx.cloudflare.net` — no longer routing through CF for inbound)

**6. Add DKIM** (Google Workspace)
- Admin console → Apps → Google Workspace → Gmail → Authenticate Email
- Generate DKIM key for `sapphire-pools.com`
- Copy the DNS record Google shows
- Add it as TXT record in Cloudflare DNS (host: `google._domainkey`)
- Wait 1 hour, then click "Start Authentication" in Workspace

**7. Add DMARC** (recommended)
- Cloudflare DNS → TXT record
- Host: `_dmarc.sapphire-pools.com`
- Value: `v=DMARC1; p=none; rua=mailto:dmarc@sapphire-pools.com; pct=100`
- Start with `p=none` for monitoring, raise to `quarantine` then `reject` once SPF/DKIM are verified working over a few weeks

### Verification (within 1 hour of MX cutover)

**8. Test inbound**
- From a personal email, send to `accounting@sapphire-pools.com`
- Should appear in `sapphpools@gmail.com` within 1 minute
- Check Gmail "Show original" → confirm "Received from Google" headers (not Cloudflare)

**9. Test other aliases**
- Send to `contact@sapphire-pools.com`, etc. — each should land in the same inbox
- Reply from Gmail and verify the from-address is the alias the recipient sent to

**10. QP confirms sync**
- In QP: Settings → Email → click Sync on the Sapphire Gmail integration
- New emails to alias addresses should appear in QP's inbox within minutes
- Verify they're tagged correctly (Stripe → billing folder, etc.)

### Cleanup (after 7 days of stable operation)

**11. Decommission Cloudflare Workers**
- Cloudflare dashboard → Email → Email Routing
- Disable any custom routing rules for sapphire-pools.com
- Optionally: delete the Worker scripts entirely

**12. Update QP EmailIntegration**
- The managed-mode `inbox-sapphire@mail.quantumpoolspro.com` integration is now unused
- Settings → Email → click trash on the managed-mode entry to remove it
- Gmail integration becomes the only inbound path

**13. Postmark inbound webhook**
- If only Sapphire was using inbound webhooks, the Postmark inbound stream is no longer needed
- Either disable the inbound webhook or leave dormant (no harm)

---

## Rollback Plan

If something breaks after MX cutover:
1. Cloudflare DNS → MX records → revert to Cloudflare entries (route1/2/3.mx.cloudflare.net)
2. Verify Cloudflare Email Workers are still running
3. Wait for TTL (1 hour with the lowered TTL) — mail flow returns to QP via managed mode
4. Investigate what broke before retrying

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Mail bounce during cutover | Lower TTL 24h ahead; keep CF Workers running 7 days as fallback |
| Aliases not configured before cutover | Verify all aliases work in Google admin before changing MX |
| QP loses sync of past emails | Past emails stay in QP DB (not deleted by migration) |
| SPF/DKIM misconfiguration → outbound bounces | Test outbound from Gmail to external domain after DKIM setup |
| Lost Cloudflare-routed mail history | Past inbound is already in QP DB. Nothing in CF Workers (stateless) |

---

## What Lives Where After Migration

| Email | Source of truth | Backup |
|---|---|---|
| All inbound `*@sapphire-pools.com` | Gmail | Google Vault (if enabled) + QP DB synced copy |
| Outbound from Gmail | Gmail Sent folder | QP DB synced copy |
| Outbound from QP via Postmark (transactional) | QP DB | Postmark archive (45 days default) |

If QP is wiped: reconnect Gmail OAuth, hit Backfill, mail history returns. Only AI metadata (classifications, tags, folders, customer matching) is lost.

---

## Future: Multi-Customer Pattern

This Sapphire migration establishes the pattern for every future QP customer:

- Every customer org connects their own email provider (Gmail/Workspace, MS365, IMAP)
- Their email lives in their own infrastructure
- QP is the intelligence layer, never the canonical store
- Customer can leave QP at any time without losing email history

Managed mode (Cloudflare Workers + Postmark webhook) becomes a fallback for customers without their own email infrastructure, NOT the default.
