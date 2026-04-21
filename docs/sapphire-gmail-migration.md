# Sapphire → Gmail Migration Playbook

> **Goal:** Move Sapphire's canonical mail store from Zoho + Cloudflare-managed-mode into a single Google Workspace seat, with full Zoho history preserved. QP stays the intelligence layer and reads from Gmail via OAuth.
>
> **Architecture decided (2026-04-15):** ONE paid Workspace seat (`brian@sapphire-pools.com`). All other addresses are **aliases** on that seat. "Who did what" accountability is tracked by QP's audit trail (AgentMessage/AgentAction), not by Gmail account separation. Both Brian and Kim work customer triage inside QP; underlying Gmail is a pipe.
>
> **Workspace origin:** Converted from Brian's personal `sapphpools@gmail.com` Gmail account (not created fresh). The Workspace `brian@sapphire-pools.com` user and the old `sapphpools@gmail.com` share the same underlying mailbox. Expect legacy cruft in Settings (old Bluehost-SMTP send-as entries, Zoho POP3 pullers, filters). This is why `sapphpools@gmail.com` is un-deletable from the Send-mail-as list — Google treats it as a managed secondary alias of the converted account.
>
> **Alias list (finalized 2026-04-21, 9 aliases):**
> - Employees: `kim`, `chance`, `shane`
> - Functional: `contact`, `accounting` (covers billing), `info`, `sales`, `support`
> - Reserved ownership only, not for active use: `noreply`
> - Auto-created by Google, not in the user's alias list: `postmaster`, `abuse`
>
> **Removal note:** Delete this doc once migration is complete and Zoho is decommissioned.

---

## State as of 2026-04-15

| Item | Value |
|---|---|
| Workspace org | Created, admin login = `sapphpools@gmail.com` (super-admin identity, not a mailbox) |
| Workspace plan | **Business Plus** — must downgrade to **Business Starter** before 2026-04-24 |
| Custom domain | `sapphire-pools.com` attached (verification status: confirm in admin) |
| Current MX | Cloudflare Email Routing (`route1/2/3.mx.cloudflare.net`) — still live |
| Current SPF | `v=spf1 include:spf.mtasv.net include:_spf.mx.cloudflare.net ~all` |
| Current DKIM | Zoho selector `zmail` removed from DNS ✅; `default` selector still referenced in DMARC report, verify cleanup |
| DMARC | `p=none`, reports to Brian |
| Postmark | Active for QP transactional outbound — **keep** |
| Cloudflare Worker `sapphire-pools-email` | Active, handling managed-mode inbound — to be disabled |
| Zoho | Active, three mailboxes: `brian@` (has send-as aliases contact@/accounting@/billing@) + `kim@` + `chance@` (confirmed 2026-04-21) |
| Zoho history scope | Brian: 245 inbound + 86 sent, 2025-02-23 → 2026-03-22 (already exported to `~/Downloads`). Kim: not yet exported. Chance: not yet exported. |
| Personal Gmail POP3 pullers | `brian@sapphire-pools.com` (working) + `contact@sapphire-pools.com` (broken since 2024-10-21) — to be deleted post-migration |
| QP Gmail OAuth integration | Connected to `sapphpools@gmail.com` personal account — will be **reconnected** to Workspace `brian@` after cutover |

## Target state

- Paid seats: 1 × Business Starter ($8.40/mo), user = `brian@sapphire-pools.com`
- Aliases on that seat (free): see alias list at top
- All 13 months of Zoho mail (both mailboxes) imported into the Workspace `brian@` mailbox with labels `Zoho-Brian` and `Zoho-Kim`
- MX: Google (`ASPMX.L.GOOGLE.COM` etc.), managed mode disabled
- SPF: Google + Postmark (`v=spf1 include:_spf.google.com include:spf.mtasv.net ~all`)
- DKIM: Google selector published
- QP reads from Workspace `brian@` via Gmail OAuth — single connected mailbox, both humans triage in QP
  - QP handles alias inbound automatically via `Delivered-To` header parsing (`orchestrator._extract_recipient_address`). No alias list is stored in the app; aliases are discovered per-message from the RFC headers.
  - QP outbound From-address is a single `organizations.agent_from_email`. Per-alias or per-user from-address is a future feature, not part of this migration.

---

## Step-by-step plan

Work through in order. Check off as completed.

### Phase 1 — Workspace setup

- [x] **1.1** ~~Downgrade plan~~ — Done 2026-04-15. Business Starter active, Flexible Plan, paid service starts in 8 days (free trial window).
- [x] **1.2** ~~Confirm domain verified~~ — Done 2026-04-15 via the "Create your custom email address" wizard on admin home. Domain auto-verified (no TXT step needed — Google likely used an existing verification signal from the zone).
- [x] **1.3** ~~Create the paid user~~ — Done 2026-04-15 via the same wizard (username `brian`). `brian@sapphire-pools.com` Active, super-admin, Business Starter license, 0 GB usage.
- [x] **1.3a** ~~Fix display name~~ — Done 2026-04-21. `brian@` user now "Brian Parrotte".
- [x] **1.4** ~~Add aliases to the brian@ user~~ — Done 2026-04-21. 9 aliases added: `kim`, `chance`, `shane`, `contact`, `accounting`, `info`, `sales`, `support`, `noreply`. Google UI labels this section "Alternate email addresses (email alias)". `billing` merged into `accounting` (same concern). `postmaster` + `abuse` are Google-reserved, auto-route to super-admin.
- [x] **1.5** ~~Configure Gmail "Send mail as" for each alias~~ — Done 2026-04-21. All 8 active aliases set with "Treat as alias" ✅: `kim`, `chance`, `shane`, `contact`, `accounting`, `info`, `sales`, `support`. `noreply` skipped (reserved, not for sending).
- [x] **1.6** ~~DO NOT click orange "Activate Gmail" banner~~ — Acknowledged; will defer MX changes to Phase 4.

### Phase 2 — Zoho pre-migration checks

- [x] **2.1** ~~Verify IMAP on Zoho `brian@`~~ — Done 2026-04-21. IMAP already enabled. Server `imappro.zoho.com:993/SSL`. 142 MB mailbox. `Include Archived emails` enabled on cleanup pass. No 2FA → regular mailbox password works.
- [x] **2.2** ~~Zoho `kim@` IMAP~~ — Done 2026-04-21. IMAP + Include Archived enabled; password recorded.
- [x] **2.2a** ~~Zoho `chance@` IMAP~~ — Done 2026-04-21. IMAP + Include Archived enabled; password recorded.
- [ ] **2.3** (Optional) Kim and Chance export Inbox + Sent from Zoho as a backup — DMS will pull via IMAP anyway, but a zip in `~/Downloads` is good insurance against DMS failure. Skipped by default; add backup zips only if a DMS run fails partway.
- [x] **2.4** ~~Confirm Zoho user list~~ — Done 2026-04-21. Three Zoho mailboxes total: `brian@`, `kim@`, `chance@`. Shane has no Zoho mailbox. No others.

### Phase 3 — Data migration (Zoho history → Workspace)

- [ ] **3.1** admin.google.com → Data migration → Set up data migration.
- [ ] **3.2** Migration source: **IMAP** (other provider). Server: `imappro.zoho.com` (paid Zoho Mail/Workplace — NOT `imap.zoho.com` which is the free tier), Port: `993`, SSL: Yes.
- [x] **3.3** ~~Run #1 — Brian~~ — Done 2026-04-21. 841 emails imported, 0 failures. Label `Zoho-Brian` applied post-hoc (~750 conversations after Gmail threading) using search `(to:sapphire-pools.com OR from:sapphire-pools.com) before:2026/04/09 -label:QP-Processed`. Tier 1 + Tier 2 junk cleanup already run.
- [x] **3.4** ~~Run #2 — Kim~~ — Done 2026-04-21. 2,572 emails imported, 0 failures. **Label pass + cleanup NOT YET DONE** (pending resume).
- [x] **3.4a** ~~Run #3 — Chance~~ — Done 2026-04-21. 546 emails imported. **Label pass + cleanup NOT YET DONE.**
- [ ] **3.5** Monitor progress in Data migration dashboard. Each shows per-user status; wait for **Completed** on all three.
- [ ] **3.6** Post-DMS cleanup workflow **per mailbox** (apply in order: Zoho-Brian ✅, Zoho-Kim ⏸, Zoho-Chance ⏸):
    - Label pass (use search tailored to exclude already-labeled mail):
      - Kim: `(to:sapphire-pools.com OR from:sapphire-pools.com) before:2026/04/09 -label:QP-Processed -label:Zoho-Brian` → bulk-apply `Zoho-Kim`.
      - Chance: `(to:sapphire-pools.com OR from:sapphire-pools.com) before:2026/04/09 -label:QP-Processed -label:Zoho-Brian -label:Zoho-Kim` → bulk-apply `Zoho-Chance`.
    - Tier 1 junk (safe bulk-trash): `label:Zoho-<User> -label:Sapphire (has:list-unsubscribe OR from:(noreply OR no-reply OR donotreply) OR category:promotions)`
    - Tier 2 junk (review then trash): `label:Zoho-<User> -label:Sapphire from:(stripe.com OR paypal.com OR intuit.com OR quickbooks.com OR godaddy.com OR namecheap.com OR bluehost.com OR cloudflare.com)`
    - Post-hoc dedup (brian@ only, deferred to task #10 script): find DMS-imports with `QP-Processed` twin → merge labels onto QP-Processed copy, delete DMS dupe.

### Phase 4 — DNS cutover (MX + SPF + DKIM)

> Claude can do all Cloudflare DNS changes via API if Brian confirms the API key from `memory/sapphire-recovery-in-progress.md` still works.

- [ ] **4.1** Lower MX TTL on current Cloudflare MX records to 3600 (1 hour) via Cloudflare API. Wait ≥24h before cutover to shorten the dual-routing window.
- [ ] **4.2** Generate Google DKIM: admin.google.com → Apps → Google Workspace → Gmail → Authenticate email → Generate new record (2048-bit). Copy the TXT value.
- [ ] **4.3** Publish DKIM in Cloudflare: TXT record host `google._domainkey`, value from step 4.2. Wait 1 hour, then click **Start authentication** in Workspace.
- [ ] **4.4** Update SPF in Cloudflare: replace `v=spf1 include:spf.mtasv.net include:_spf.mx.cloudflare.net ~all` with `v=spf1 include:_spf.google.com include:spf.mtasv.net ~all`.
- [ ] **4.5** Cutover MX in Cloudflare: delete the three `route*.mx.cloudflare.net` records; add Google MX:

    | Priority | Mail server |
    |---|---|
    | 1 | ASPMX.L.GOOGLE.COM |
    | 5 | ALT1.ASPMX.L.GOOGLE.COM |
    | 5 | ALT2.ASPMX.L.GOOGLE.COM |
    | 10 | ALT3.ASPMX.L.GOOGLE.COM |
    | 10 | ALT4.ASPMX.L.GOOGLE.COM |

- [ ] **4.6** Disable Cloudflare Email Routing on the zone (dashboard or API) — stops the managed-mode path.
- [ ] **4.7** DMARC stays at `p=none` for now. Revisit after 2 weeks of clean reports.

### Phase 5 — Verify new inbound flow

- [ ] **5.1** From a personal account, send a test to `contact@sapphire-pools.com`. Should land in Workspace `brian@` Gmail inbox within 1–2 minutes. "Show original" → confirm Received-from Google, DKIM pass, SPF pass.
- [ ] **5.2** Repeat test to each alias — `kim@`, `chance@`, `shane@`, `accounting@`, `info@`, `sales@`, `support@`, `brian@`. All should land in the same inbox. (Skip `noreply@` — reserved, not in use.)
- [ ] **5.3** Reply from Gmail using the "Send mail as" dropdown — verify the recipient sees the correct from-address (not `brian@`).
- [ ] **5.4** External delivery check: send from Gmail to a personal account on a different provider. Confirm DKIM + SPF pass at the recipient side (check "Show original").

### Phase 6 — Reconnect QP to the new mailbox

- [ ] **6.1** QP → Inbox → Integrations (`/inbox/integrations`) → remove the existing Gmail OAuth integration pointed at `sapphpools@gmail.com`.
- [ ] **6.2** Add a new Gmail integration. Authorize as `brian@sapphire-pools.com` (Workspace). Confirm OAuth scopes approved.
- [ ] **6.3** Trigger initial sync / backfill. QP should pull recent inbound (new mail landing since MX cutover) plus whatever backfill window QP uses. Historical Zoho mail stays in Gmail under labels — QP may or may not ingest it depending on backfill window; fine either way since QP can search Gmail directly via future features if needed.
- [ ] **6.4** Remove the QP managed-mode integration entry (`inbox-sapphire@mail.quantumpoolspro.com` or similar) if it still exists. Managed mode is now off.
- [ ] **6.5** End-to-end test: customer sends to `contact@sapphire-pools.com` → lands in Workspace Gmail → QP ingests within polling window → draft is generated → send reply from QP → verify the reply appears in Gmail Sent folder and reaches the customer.

### Phase 7 — Decommission Zoho and old pullers

- [ ] **7.1** **Legacy-cruft cleanup inside the converted Workspace mailbox** (brian@sapphire-pools.com Gmail = old sapphpools@gmail.com). This account is a 10+ year personal Gmail that got Workspace-ified; every Gmail surface below needs an audit pass, not just Accounts. Settings → :
    - **Accounts → Check mail from other accounts**: delete the `brian@sapphire-pools.com` POP3 puller. (Phase 4 cutover makes it redundant — Zoho is being shut down.) Kept running until Phase 4 as a safety net per 2026-04-21 decision.
    - **Accounts → Send mail as**: should end up with only the 8 Phase-1.5 aliases (`kim`, `chance`, `shane`, `contact`, `accounting`, `info`, `sales`, `support`) + the un-deletable legacy `sapphpools@gmail.com` entry. Delete anything else. `sapphpools@gmail.com` is Google-managed and un-deletable via Gmail settings.
    - **Filters and Blocked Addresses**: review every filter. Delete any referencing Zoho (`mx.zoho.com`, `imap.zoho.com`), Bluehost (`bluehost.com`, `box5721`), old POP3 puller labels, or otherwise-obsolete routing. Keep only filters that will still be valid post-migration.
    - **Forwarding and POP/IMAP**: confirm no automatic forwarding is enabled (would leak mail + cause loops once QP is reading). Disable POP and IMAP access unless a use case exists — QP uses OAuth API, not IMAP.
    - **General → Signature**: either clear (if signature comes from QP) or update to match QP's branding signature so manual Gmail replies look consistent. Vacation responder: off unless actually needed.
    - **Labels**: remove old labels from the personal-Gmail era that are now meaningless (e.g., any "Zoho-", Bluehost-era labels after DMS labels are confirmed present).
    - (On 2026-04-21 cleanup pass, the obsolete Bluehost-SMTP send-as entries for `contact@` and `shane@` + the broken `contact@` POP3 puller were already deleted, and the `sapphpools@gmail.com` send-as display name was renamed from "Sapphire Pools" to "Brian (Personal)" for clarity.)
- [ ] **7.1a** **Cleanup audit** (final verification, don't skip): take a fresh screenshot of Settings → Accounts + Filters + Forwarding. Compare against expected end state (no Zoho/Bluehost references, 8 aliases + legacy sapphpools@, no POP pullers, no forwarding). Anything unexpected → investigate before declaring Phase 7 complete.
- [ ] **7.2** Verify for 3–5 days that all expected mail is flowing: customers replying, vendor notifications, Stripe receipts, insurance, etc.
- [ ] **7.3** mailadmin.zoho.com → Domains → `sapphire-pools.com` → Remove domain. (Or close the whole Zoho org if Sapphire is its only domain.)
- [ ] **7.4** Zoho One apps — if the org uses any: CRM, Campaigns, Bookings, Desk, Sign, SalesIQ, etc. Remove domain from each, or close the Zoho One account outright.
- [ ] **7.5** Revoke any remaining Zoho app passwords / OAuth tokens tied to Sapphire addresses.
- [ ] **7.6** Disable the `sapphire-pools-email` Cloudflare Worker (leave deployed, just disabled — removes active reference without deleting code). Clear any Postmark inbound webhook URL config pointing at it. **Do NOT** touch the Postmark outbound sender token; QP transactional still uses it.

### Phase 8 — Confirm and document

- [ ] **8.1** Monitor the next DMARC aggregate report (24–48h after Zoho teardown). Confirm zero records from Zoho IP ranges (`136.143.x.x`, `165.22.x.x`, `204.141.32.0/21`).
- [ ] **8.1a** **Identify + resolve the failing senders before tightening DMARC.** Multiple DMARC reports (MS 2026-04-13, Google 2026-04-17) show low-volume outbound traffic from `35.89.44.{33,35,39}` + `44.202.169.39`, all DKIM-fail-on-`default`-selector + SPF-softfail, to `conam.us` (ConAm Management, a Sapphire customer). Reverse-DNS resolved on 2026-04-21 — these are **NOT mystery AWS workloads**; they're `omta##.*.cloudfilter.net` = OpenSRS / Bluehost / Tucows shared-hosting mail-relay infrastructure. The likely cause is a still-active Bluehost (or OpenSRS-reseller) mailbox on `@sapphire-pools.com` that Brian has somewhere. Under `p=none` it's noise; under `p=quarantine`/`p=reject` the mail gets filtered or bounced.
    - Investigate: active Bluehost hosting account with a sapphire-pools.com mailbox still configured? Automated integration with cached Bluehost SMTP creds (CRM, invoicing, property-mgmt portal)? Third-party service relaying on Sapphire's behalf?
    - Search Brian's ~10y converted Workspace mailbox + billing records for "Bluehost" or "OpenSRS" activity. Log into any legacy Bluehost/hosting cPanel accounts, disable sapphire-pools.com email hosting.
    - Once source is shut down OR added to SPF (if legitimate), DMARC reports should go clean within 1-2 aggregate cycles.
- [ ] **8.2** After 2 weeks of clean DMARC reports **AND** step 8.1a resolved: raise DMARC to `p=quarantine` (can do `p=reject` after another 2 weeks if still clean).
- [ ] **8.3** Update memory: delete `sapphire-recovery-in-progress.md` and `sapphire-workspace-downgrade-reminder.md`, replace with a short completion note (or the migration plan's final-state section suffices).
- [ ] **8.4** Update `docs/sapphire-recovery-plan.md` with completion status or supersede.
- [ ] **8.5** Delete this doc and remove from `CLAUDE.md` Documentation Index in the same commit.

---

## Reference info

### Cloudflare API
Credentials live only in the local memory file `memory/sapphire-recovery-in-progress.md` — never commit them to this repo (GitHub secret scanning blocks the push). Zone ID for `sapphire-pools.com` is `db6544f9fe0a50648957ded4e26758c2`. Verify access before Phase 4 DNS edits:

```
curl -s -H "X-Auth-Email: <email>" \
     -H "X-Auth-Key: <global-api-key>" \
     "https://api.cloudflare.com/client/v4/zones?name=sapphire-pools.com"
```

### Zoho IMAP endpoints (Zoho Mail Pro / Workplace — paid tier)
- Host: `imappro.zoho.com` (NOT `imap.zoho.com`; that's the free tier)
- Port: `993` (SSL)
- Username: full email address (e.g., `brian@sapphire-pools.com`)
- Password: mailbox password, or app-specific password if 2FA is on (create at `accounts.zoho.com` → Security → App Passwords)

### What NOT to touch
- Postmark sender token for QP transactional outbound — **leave alone**
- Cloudflare Worker code (`sapphire-pools-email`) — disable, don't delete, so it's available as reference
- QP EmailIntegration model code — no changes needed; this is a config-only migration

---

## Rollback

If MX cutover breaks something:
1. Cloudflare DNS → revert to the three `route*.mx.cloudflare.net` MX records
2. Re-enable Cloudflare Email Routing on the zone
3. TTL was lowered to 1h ahead of time → mail flow returns to managed mode within 1h
4. Zoho still has all the mail (domain not yet removed from Zoho at this point) — nothing lost

## Risks

| Risk | Mitigation |
|---|---|
| DMS fails silently on Kim's mailbox | Kim's own Zoho export zip is the backup; IMAP-import if needed |
| Aliases not set up before MX cutover | Phase 1.4 + 5.2 cover this — test every alias after setup |
| contact@ post-2024-10-21 gap doesn't migrate | 3.6 specifically spot-checks this; re-run DMS scoped to that date range if missed |
| SPF/DKIM breaks outbound | Keep Postmark include in SPF; test external delivery at 5.4 |
| QP sync stops during the MX switch | Expected — QP will resume reading from new mailbox after 6.2. No data loss; history is in Gmail |
| Workspace bills Business Plus while decision is pending | Downgrade deadline 2026-04-24 — Phase 1.1 must be done first |
| Unidentified AWS senders get filtered when DMARC tightens | Step 8.1a identifies them first; don't skip it. The 2026-04-13 report flagged 3 IPs sending to `conam.us` — could be a legitimate integration or spoofing, must be resolved before `p=quarantine` |
