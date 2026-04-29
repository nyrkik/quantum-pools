# Billing & Payments — May Launch Plan

This is the detailed build plan to get QP billing live for the May 2026 go-live. See `docs/billing-dormant.md` for the inventory of what's already wired, `memory/stripe-setup-state.md` for credential status, and CLAUDE.md "Business Context" for the entity distinction (Sapphire is a customer, QP is the product).

The shape of the recommendation comes from a 2026-04-28 competitive + best-practice review (Skimmer, Pool Brain, Pool Office Manager, Jobber, Housecall Pro, ServiceTitan, Service Fusion + Stripe Connect docs + dunning research + CA tax law). Headline findings:

- **VVG LLC holds the platform Stripe** (decision locked 2026-04-28). Bluevine for payouts. QP LLC migration deferred until product/marketing direction settles.
- **No second org in May** → **Stripe Connect deferred** until org #2 is on the horizon. Single-tenant Stripe under VVG is the May 1 architecture. Connect remains the right answer when multi-tenant onboarding becomes real.
- **Architectural discipline**: `_stripe_request(org, ...)` dispatch shim built from day one so Connect is a one-field, one-branch addition later, not a rewrite.
- **Existing `.env` Stripe keys belong to PSS** (legacy single-tenant pool app), not QP. They must be replaced with new VVG-owned keys.
- **No Sapphire carve-out**: all 74 Sapphire customers have `stripe_customer_id IS NULL` — nothing to migrate. Clean slate.
- **ACH is table-stakes** — every competitor has it; economics push every party toward it (1% capped at $10 vs 2.9% + 30¢).
- **Consolidated multi-property billing** is QP's clearest competitive wedge — only Skimmer offers it cleanly, and it's the exact Sapphire commercial scenario.
- **CA bans card surcharging** (SB 478, July 2024). Use cash-discount messaging instead.
- **Never auto-suspend pool service** for non-payment — algae/mosquito/pH burns are real liability. Generate a service-at-risk flag for human review (workflow_observer pattern).

## Current state (as of 2026-04-28)

- **Stripe Checkout** for one-time invoice payments — `/pay/{token}` page lives.
- **Card-on-file**: SetupIntent + public `/card/{token}` page using Stripe Elements (SAQ A — lowest PCI scope).
- **Models**: `Customer` has `stripe_customer_id`, `stripe_payment_method_id`, autopay fields, billing-cycle fields. `Invoice` has `is_recurring`, `generation_source`, `billing_period_start/end`, `payment_token`, `stripe_payment_intent_id`. `Payment` has `stripe_payment_intent_id`, `stripe_charge_id`, `is_autopay`. `AutopayAttempt` audit table exists.
- **Services**: `StripeService` (checkout, setup-intent, save/detach PM, charge_autopay, webhook handlers). `BillingService.generate_recurring_invoices` + `retry_failed_payments`. `PaymentService` for manual entry.
- **Endpoints**: `/v1/billing/*`, `/v1/payments/*`, `/v1/invoices/*` (CRUD, send, void, write-off), `/v1/customers/{id}/setup-intent`, `/v1/public/{invoice,card,stripe/webhook}`.
- **APScheduler jobs DISABLED** in `app/app.py` (`_run_billing_cycle`, `_run_payment_retries` commented out).
- **Stripe credentials**: dev test keys in `.env`. `STRIPE_WEBHOOK_SECRET` not set.
- **Single-account architecture**: `StripeService` reads `settings.stripe_secret_key` — only works for one tenant. **No Stripe Connect.**
- **Payment Reconciliation Phase 1** (shipped 2026-04-27): `parsed_payments` table + Entrata remittance parser + `/billing/reconciliation` page. Independent of recurring billing — covers the commercial-AP inbound side.
- **Customer portal**: does not exist. Customers see invoices only via tokenized public links.

## Phase 0: Stand up VVG-owned Stripe account (decision LOCKED 2026-04-28)

**Decision (locked):** VVG LLC holds the platform Stripe account. Bluevine business account receives payouts. QP LLC has not been formed and any future migration is deferred — it's a separate question tied to the broader product/marketing direction.

**Critical scope change driven by this decision:** Brian is not onboarding any second org in May. Sapphire is the only org that will bill via QP for the foreseeable future. **Stripe Connect is not needed for May 1.** Single-tenant Stripe under VVG is sufficient. Connect becomes a "do it before org #2 lands" task, not a launch task.

**Architectural discipline preserved:** even though Connect is deferred, all Stripe calls are routed through a `_stripe_request(org, ...)` dispatch shim from day one. When org #2 lands, Connect is one field on `Organization` + one branch in the shim — not a rewrite. Builds for the 1,000th customer without pre-building infrastructure for a customer that doesn't exist yet.

**Existing PSS keys must come out:** the `.env` Stripe credentials belong to PSS (legacy single-tenant pool app), not QP. They cannot be reused.

**Done when:**
- New Stripe account created under VVG LLC (test mode first)
- Bluevine bank account configured for payouts in Stripe dashboard
- Webhook endpoint registered: `https://app.quantumpoolspro.com/api/v1/public/stripe/webhook` with required events (see Phase 1, even though Connect onboarding is deferred — `payment_intent.succeeded`, `payment_intent.payment_failed`, `setup_intent.succeeded`, `checkout.session.completed`, `charge.refunded` are all needed)
- New `STRIPE_SECRET_KEY` / `STRIPE_PUBLISHABLE_KEY` / `STRIPE_WEBHOOK_SECRET` in `.env`
- Old PSS-owned keys removed from `.env` and `.env.example`

## Phase 1: Stripe Connect Standard foundation — DEFERRED until org #2

**Status (2026-04-28):** Deferred. Brian is not onboarding a second org in May. Sapphire bills directly through VVG-owned platform Stripe (single-tenant). This phase ships when org #2 is on the horizon.

**When this phase comes back online**, the model + service shape below is still right. The dispatch shim in Phase 0 makes wiring it a small change, not a rewrite.

**Goal:** Multi-tenant Stripe. New orgs onboard via Stripe-hosted Connect flow; charges + payouts flow to their bank; QP takes an `application_fee_amount` per transaction.

**Backend:**
- Add to `Organization`:
  ```
  stripe_connected_account_id (acct_...)
  stripe_onboarding_status (not_started | in_progress | complete | restricted)
  stripe_charges_enabled (bool)
  stripe_payouts_enabled (bool)
  application_fee_pct (decimal, default 0 for now — revenue model TBD)
  ```
- New service: `StripeConnectService`
  - `create_account(org)` — Stripe `accounts.create({type: "standard"})`
  - `create_onboarding_link(org)` — returns Connect Onboarding URL
  - `refresh_account_status(org)` — pulls account state, updates flags
  - Webhook: `account.updated` → refresh status, transition `stripe_onboarding_status`
- Refactor `StripeService`: every Stripe call includes `Stripe-Account: acct_xxx` header + `application_fee_amount`. Single dispatch shim: `_stripe_request(org, method, **kwargs)` — every service method routes through this.
- Update all webhook handlers to look up org via `connected_account_id` (Connect events arrive on the platform endpoint with `account` field set).

**Frontend:**
- Settings → Billing → "Connect Stripe" wizard (owner only, gated on permission)
- Status display: not connected / pending verification / restricted (with reason) / connected
- "Open Stripe Dashboard" deep link (Connect Standard accounts get a real dashboard)
- Disconnect flow with confirmation (rare, but needed for onboarding errors)

**Configuration:**
- Stripe Connect must be enabled in QP's Stripe account (one-time dashboard toggle).
- Webhook endpoint must subscribe to: `account.updated`, `payment_intent.succeeded`, `payment_intent.payment_failed`, `setup_intent.succeeded`, `charge.refunded`, `payout.paid`, `payout.failed` (for tenant visibility into payouts).

**Done when:** A new org can sign up, click "Connect Stripe," complete the hosted onboarding, and have `stripe_charges_enabled=true`. A test charge to that org's connected account succeeds, with QP taking the application fee.

## Phase 2: ACH bank-debit support

**Goal:** Customers can pay via ACH (bank account) in addition to card. ~60% processing-fee savings on average invoice.

**Backend:**
- Extend `StripeService.create_setup_intent` to support `payment_method_types: ["card", "us_bank_account"]`.
- Public `/card/{token}` page renames to `/pay-method/{token}` (or keep URL, change copy) — show both card and ACH options.
- Add to `Customer`:
  ```
  stripe_bank_last4
  stripe_bank_name
  stripe_bank_account_type (checking | savings)
  default_payment_method_type (card | bank)
  ```
- Stripe Mandate object: store `mandate_id` per ACH PaymentMethod (Stripe handles NACHA-compliant authorization language).
- Webhook: `mandate.updated` — handle revocation (rare but possible).
- ACH charge timing: ACH settles in 4-5 business days. Update `Payment.status` lifecycle to include `pending_settlement` → `succeeded` | `failed` (currently assumes instant).
- Failed ACH (insufficient funds, account closed) hits `payment_intent.payment_failed` with specific failure codes — surface them in the customer-facing dunning email.

**Frontend:**
- Public payment-method setup page: tabbed Card / Bank
- Customer-detail billing tile: show both saved methods, change default
- Customer portal payment-methods tab (Phase 3): same UX
- "Save 1% — pay by bank" cash-discount messaging on the invoice and pay page (legal substitute for surcharging in CA)

**Done when:** A customer can save an ACH PaymentMethod via the public link, charge it, see the 4-5-day settlement window, and successfully be marked paid when settlement clears.

## Phase 3: Magic-link customer portal (V1)

**Goal:** Customers log in (passwordless) and see a 3-tab portal: Billing / Payment Methods / History. Replaces tokenized one-shot links for any ongoing relationship.

**Why magic link, not password:** Industry consensus (Jobber, Housecall Pro, Skimmer). Residential pool customers check the app monthly — password friction kills the autopay enrollment funnel. 15-minute link, 30-day session, refresh on activity.

**Backend:**
- New model: `CustomerPortalSession`
  ```
  customer_id (FK)
  contact_id (FK, nullable) — which CustomerContact this session belongs to
  token (UUID, indexed)
  created_at
  expires_at (created + 30d, refresh on activity)
  ip_address (last seen)
  ```
- New model: `CustomerMagicLink`
  ```
  contact_id (FK CustomerContact)
  token (UUID, indexed)
  created_at
  expires_at (created + 15min)
  consumed_at (nullable)
  ```
- Endpoints:
  - `POST /v1/portal/request-link` (public, rate-limited) → looks up CustomerContact by email, creates magic link, sends email
  - `GET /v1/portal/consume/{token}` → validates, creates session, sets HttpOnly cookie, redirects to `/portal`
  - `GET /v1/portal/me` → returns customer + linked properties + open invoices + saved methods
  - `GET /v1/portal/invoices` → paginated invoice history
  - `GET /v1/portal/invoices/{id}/pdf` → returns the same PDF as the admin invoice
  - `GET /v1/portal/payments` → payment history
  - `POST /v1/portal/setup-intent` → SetupIntent for adding new method
  - `DELETE /v1/portal/payment-methods/{id}` → detach
  - `PUT /v1/portal/payment-methods/{id}/default` → set default
  - `PUT /v1/portal/autopay` → toggle autopay (per-customer V1; per-property in Phase 6)
- Auth: portal session cookie scoped to `/portal/*` routes, HttpOnly, Secure, SameSite=Lax. Separate from staff JWT.

**Frontend:**
- New route: `/portal/login` — email entry, "Send me a link" button
- New route: `/portal/login/sent` — "Check your email"
- New route: `/portal` — 3-tab layout (Billing / Methods / History)
  - **Billing tab**: open invoices list, total due, pay-now button per invoice (uses Stripe Elements)
  - **Methods tab**: saved cards/banks, add new, set default, delete, autopay toggle
  - **History tab**: closed invoices + payments, downloadable PDFs
- Mobile-first responsive (residential customers almost never desktop-log-in).
- Org branding: org logo + name in header. No QP branding visible to end customer except a small "Powered by Quantum Pools" footer.

**Magic-link email:**
- Templated transactional (not AI-drafted). Subject: "Sign in to {{org.name}}". Body: single CTA, "This link expires in 15 minutes."
- Sent via tenant's outbound provider (`EmailService.send_agent_reply` already routes correctly).

**Done when:** A customer receives a magic link, logs in, pays an invoice, adds a bank as their default method, and toggles autopay — all without staff involvement.

## Phase 4: Dunning sequence (4 emails)

**Goal:** Recover failed payments via a researched email cadence. Industry recovery rates: 50–70% in the first 14 days; 4% by day 30.

**Cadence:**

| Day | Trigger | Email | Tone |
|-----|---------|-------|------|
| T+0 | Charge fails | "Your payment couldn't be processed" | Neutral, "probably a card thing." Includes specific failure reason if known ("card ending 4242 expired"). |
| T+3 | No card update | "Action required: update your payment" | Polite, direct link to portal. Single CTA. |
| T+7 | No card update | "Your service is at risk" | Escalating. Mentions next visit date if scheduled. |
| T+14 | No card update | "Final notice — service review pending" | Last chance. **Does NOT auto-suspend** (liability — see Cross-cutting). Generates a `service_at_risk` flag for the org owner to review. |

**Backend:**
- `BillingService.send_dunning_email(invoice_id, sequence_step)` — uses `EmailService.send_agent_reply` path (already routes via tenant provider).
- New scheduled job: `_run_dunning_sequence` — daily, checks `Invoice.status = 'past_due'` + last dunning sent, advances to next step.
- Dunning emails are **system-templated transactional**, not AI-drafted — they don't go through agent_proposals. (DNA rule #5 governs AI-drafted customer email; system transactional templates are out of scope for that rule.)
- New status on `Invoice`: `service_at_risk` (set after T+14, viewable in admin UI for owner action).
- Late fee application (Phase 8) hooks here.

**Frontend:**
- Dashboard widget for owner+admin: "Service-at-risk invoices" with one-click "Suspend service" / "Extend grace" actions.
- Per-invoice timeline view showing dunning history (T+0 sent / T+3 sent / etc.).

**Templates:**
- Tone tuning per org via AgentLearningService (corrections feed back to template variants — "shorter," "less formal," etc.). Default templates ship opinionated.
- Subject lines escalate: "Payment issue" → "Action required" → "Service at risk" → "Final notice."

**Done when:** A failed payment triggers the full 4-email sequence, the customer can update their card via the in-email link (uses Phase 3 portal), and the owner sees the service-at-risk widget on their dashboard.

## Phase 5: A/R aging report

**Goal:** Owner+admin can see at a glance who owes what, bucketed by age. Pool Brain users complain explicitly about not having this.

**Backend:**
- New endpoint: `GET /v1/billing/ar-aging` → returns array of `{customer_id, customer_name, current, days_30, days_60, days_90, days_over_90, total_owed}`.
- Computed live (no cache); query is `Invoice.status IN ('sent', 'past_due', 'service_at_risk')` grouped by customer, bucketed by `due_date`.

**Frontend:**
- New page: `/billing/ar-aging` (owner+admin gated)
- Table sorted by total owed descending; click customer → customer detail
- CSV export
- Per-bucket totals row

**Done when:** Owner can pull up the page, see the org's outstanding receivables in 30-day buckets, and click through to chase specific customers.

---

**Above this line: Must-have for May 1.** Below: Should-have by end of May.

---

## Phase 6: Consolidated multi-property billing

**Goal:** Commercial customers with N properties get **one invoice** per period, not N. The Sapphire commercial scenario; only Skimmer competes here.

**Backend:**
- Add to `Customer`:
  ```
  billing_mode (per_property | consolidated) — default per_property
  ```
- Refactor `BillingService.generate_recurring_invoices`:
  - For `per_property` customers: current behavior (one invoice per property per period).
  - For `consolidated` customers: one invoice grouping all property line-items, each line tagged with `property_id` and `service_period`.
- Extend `InvoiceLineItem`:
  ```
  property_id (FK, nullable — required for consolidated invoices)
  service_period_start (date, nullable)
  service_period_end (date, nullable)
  ```
- Property-level autopay toggle on `Property` (separate from customer-level). For consolidated customers, autopay is per-customer, not per-property (one charge for the whole invoice).

**Frontend:**
- Customer detail → billing tile: toggle `billing_mode`. When toggled to consolidated, show preview: "Next invoice will combine charges from {{N}} properties: {{list}}".
- Invoice detail: line items grouped by property header for consolidated invoices.
- Customer portal billing tab: invoice line items show property name per line.

**Done when:** A commercial customer with 5 properties is set to `consolidated`, the next billing cycle produces a single invoice with 5 line items grouped by property, and the customer can pay it (or autopay it) as one charge.

## Phase 7: Statements (PDF download)

**Goal:** Commercial customers can download a true rolled-up monthly statement (separate from individual invoices) for AP reconciliation.

**Backend:**
- New service: `StatementService.generate(customer_id, period_start, period_end)` → returns PDF bytes.
- Statement format: starting balance + invoices issued in period + payments received in period + ending balance, sorted by date.
- New endpoint: `GET /v1/customers/{id}/statements/{year}/{month}` (admin) and `GET /v1/portal/statements/{year}/{month}` (customer portal).
- New table: `customer_statements` (caches generated PDFs; includes `period_start`, `period_end`, `pdf_url`, `generated_at`). Regenerated on demand if customer or admin requests; cached for portal display.

**Frontend:**
- Customer detail → "Statements" section (admin): list by month, download.
- Customer portal History tab: "Download statement" link per month.

**Done when:** A commercial customer (Sapphire's Entrata-managed properties) can download a PDF statement for any past month showing their full account activity.

## Phase 8: Late fees + service holds — SHIPPED 2026-04-29

**Status:** Shipped manual-only (mirrors Phase 4 dunning posture). Auto-scheduler intentionally not wired — backlog needs a human review per run before any auto-fire is enabled. Tests in `app/tests/test_property_holds.py` + `app/tests/test_late_fees.py` cover idempotency, PSS exclusion, customer override, percent-with-minimum, hold inclusive boundaries, multi-property partial-hold logic.

**What landed:**
- 5 columns on `organizations` (`late_fee_enabled/type/amount/grace_days/minimum`) + 1 on `customers` (`late_fee_override_enabled`).
- New `property_holds` table (`PropertyHold` model) + `PropertyHoldService` with `is_property_held`, CRUD.
- `BillingService.{preview_late_fees, run_late_fees}` — idempotent application via `description LIKE 'Late fee%' AND service_id IS NULL` marker (no schema change to `invoice_line_items`). `_recalculate_totals` recomputes via `InvoiceService` for single-source-of-truth totals.
- `BillingService._all_properties_held` — recurring billing skips a customer iff EVERY active property has a hold covering the billing period start date. Single-property residential skips cleanly; multi-property partial-hold still bills (per-property line-item exclusion arrives with Phase 6 consolidated billing).
- T+14 dunning email mentions impending late fee when org has policy enabled (deterministic warning text matching what `run_late_fees` would actually charge).
- API: `GET/PUT /v1/billing/late-fee-config` (owner+admin/owner), `POST /v1/billing/late-fees/run?dry_run=` (owner-only, mirrors dunning), property-holds CRUD under `/v1/properties/{id}/holds` + `/v1/property-holds/{id}` (owner+admin+manager mutate).
- Frontend: Settings → Billing → "Late Fee Policy" card (distinct from existing legacy "Late Fee" estimate-boilerplate field — these are two different concepts), Invoices page 6th "Late fees" tab (LateFeePreview component), Customer detail "Service Holds" tile (Add hold dialog + per-row Trash button).

**Original spec (preserved for reference):**

**Goal:** Org-configurable late fees + winterization/vacation pause.

**Backend:**
- Add to `Organization`:
  ```
  late_fee_enabled (bool, default false)
  late_fee_type (flat | percent)
  late_fee_amount (decimal — flat amount or percent)
  late_fee_grace_days (int, default 30)
  late_fee_minimum (decimal, nullable — for percent type)
  ```
- Add to `Customer`:
  ```
  late_fee_override_enabled (bool, nullable) — null = inherit from org, true/false = override
  ```
- Late fee applied as a separate `InvoiceLineItem` on the past-due invoice (not a new invoice) at T+30.
- Hook into Phase 4 dunning sequence: T+14 email warns of upcoming late fee.

- New table: `property_holds`
  ```
  id, property_id (FK), start_date, end_date, reason (text), created_by, created_at
  ```
- Recurring billing skips properties with active holds during the billing period.

**Frontend:**
- Settings → Billing: late-fee config.
- Customer detail: late-fee override toggle.
- Property detail: "Add service hold" with date range + reason. Shows active/upcoming holds.
- Calendar view marks held properties differently.

**Done when:** Past-due invoices auto-add late fee (configurable, with customer override), and property service holds skip recurring billing for the held window.

## Phase 9: Partial payments + credit memos

**Goal:** Apply partial payments against invoices; issue credit memos for refunds/adjustments. Required for commercial accounts and audit-grade write-off accounting.

**Backend:**
- Refactor `Payment` to allow `amount < invoice.total`. Partial payments leave `Invoice.status = 'partial'` with `Invoice.balance_remaining` computed.
- New status: `partial` between `sent` and `paid`.
- One invoice can have multiple `Payment` records; sum-to-total logic moves to `Invoice.balance_remaining`.
- New model: `CreditMemo`
  ```
  id, customer_id, amount, reason (text), invoice_id (FK, nullable — applied vs unapplied), created_by, created_at, stripe_refund_id (nullable)
  ```
- Refund flow: admin issues credit memo → if `stripe_payment_intent_id` exists, creates Stripe refund + stores `stripe_refund_id`; otherwise pure bookkeeping entry.
- Credit application: applied credit memos reduce `Invoice.balance_remaining`. Unapplied credits sit on customer balance.

**Frontend:**
- Invoice detail: "Apply payment" supports partial amount; shows balance remaining.
- Customer detail: "Issue credit" button (admin); shows credit history.
- Customer portal billing tab: shows partial-paid invoices with remaining balance.
- A/R aging (Phase 5) uses `balance_remaining`, not `total`.

**Done when:** A customer can pay $50 of a $200 invoice, the remaining $150 carries on the A/R aging report, and an admin can issue a $25 credit memo that either refunds via Stripe or applies against the next invoice.

---

**Above this line: Should-have by end of May.** Below: Defer.

---

## Defer (do not build for May launch)

| Feature | Why defer |
|---------|-----------|
| **Stripe Tax integration** | CA pool-service labor is nontaxable (CDTFA Pub 108 — optional maintenance contract = customer's labor not taxed). Wire `tax_amount` + `tax_rate` columns on Invoice now; integrate Stripe Tax when first multi-state customer or parts-heavy customer signs up. |
| **Consumer financing (Sunbit/Wisetack)** | Skimmer + HCP have it for big repair jobs. Irrelevant for monthly recurring service. Revisit when QP has 100+ orgs and a repair-heavy customer. |
| **Card surcharging** | Illegal in California (SB 478, July 2024). Cash-discount messaging in the portal ("Save 1% — pay by bank") is the legal substitute. Skimmer offers surcharging — they may not be enforcing the CA rule per-tenant, putting CA tenants at risk. |
| **In-portal messaging** | Email-first is consensus. Don't build chat. |
| **Native mobile app** | PWA-shaped responsive portal sufficient. Pool Brain itself is mobile-web, not native. |
| **Payment plans (multi-installment scheduled)** | Outside MRR pattern. Defer to repair-job-heavy customers. |
| **Stripe Express/Custom Connect** | Only revisit if QP wants white-label payments or escrow. Standard covers V1. |
| **Billing-config settings page (30-knob UI)** | Per DNA rule #3, observe behavior and propose org-level defaults via `agent_proposals`. Don't build a config page unless one is unavoidable. |

## Cross-cutting concerns

### NACHA authorization for ACH autopay
Skimmer punted on owner-initiated ACH autopay because of authorization-collection complexity. **QP solves this by using Stripe's `mandate` object** — Stripe handles the legal boilerplate (timestamp, IP, language shown). The portal's autopay opt-in flow displays Stripe's mandate text inline; storing the `mandate_id` is sufficient legal record.

### Webhook reliability
Billing depends on `payment_intent.succeeded`. Connect adds `Stripe-Account` headers and per-tenant routing complexity. Test exhaustively before launch:
- Webhook signature verification (`STRIPE_WEBHOOK_SECRET` must be set in prod).
- Idempotent handlers (Stripe retries on 5xx; same event may arrive multiple times).
- Connect events arrive on the platform endpoint with `account` field set — handler must look up org by `connected_account_id`, not by org from URL.
- Add Sentry tag `stripe.event_type` to every webhook event for error grouping.

### Sapphire is org #1 on Connect (no special-case)
Sapphire onboards via Connect Standard exactly like every future org. No `stripe_mode` field, no carve-out code path. The legacy PSS Stripe account is never touched by QP code. All 74 Sapphire customers re-enter payment methods on first use because none exist on Stripe today — clean slate.

### PCI scope
Stripe Elements + SetupIntent keep QP at SAQ A (lowest tier — no card data touches QP servers). **Do not regress** by accepting card numbers via API or storing PANs anywhere.

### Service suspension
Pool service has health-and-safety implications (algae, mosquito breeding, chemical imbalances → pH burns). **Never auto-suspend service for non-payment.** Generate a `service_at_risk` flag at T+14 (Phase 4); owner reviews and decides. Suspension is a manual action, not a billing-engine action.

### Multi-tenant data leakage
Every billing query MUST filter by `org_id`. Connect adds another isolation boundary (Stripe-Account header) — verify in tests that an org cannot see another org's payments even if they guess an `invoice_id`.

### Refund accounting on Connect
Stripe refunds on a connected account: refund amount comes from the connected account's balance; `application_fee_amount` is also refunded by default (`refund_application_fee=true`). Document the org-facing impact: "When you refund a customer, both their charge and our service fee are returned."

## Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| Old PSS Stripe keys accidentally left in `.env` after Phase 0 | `.env.example` updated; deploy checklist asserts new keys |
| Platform Stripe entity changes (VVG → QP LLC) post-launch | Real risk: connected platform accounts can't be migrated between entities. If QP LLC ever holds the platform Stripe, Sapphire (and any other onboarded org) must re-enter PaymentMethods. Mitigate by deferring the entity question until product/marketing direction is settled — don't migrate without explicit re-decision. |
| Connect built later turns out to need a different shape than the dispatch shim assumes | Keep the shim minimal; revisit shape when Phase 1 actually ships. Don't over-fit. |
| Webhook secret not configured in prod | Pre-launch checklist; refuse to deploy if `STRIPE_WEBHOOK_SECRET` is unset in prod env |
| Connect onboarding fails mid-flow → org stuck | Status polling + "restart onboarding" button + Sentry alert on `account.updated` with `restricted` |
| ACH failure (NSF) → false-positive paid status | Lifecycle states `pending_settlement` → `succeeded`/`failed`; do not mark invoice paid until `succeeded` |
| Auto-suspended service → liability | **Do not auto-suspend.** Service-at-risk flag only. |
| Magic-link token leaked via screenshot/forward | 15-min expiry; consumed_at single-use; HttpOnly session cookie post-login |
| Customer portal abuse (spam request-link endpoint) | Rate limit per email + per IP; CAPTCHA if abuse detected |
| Late fees applied to commercial customers in negotiated arrangements | `Customer.late_fee_override_enabled` per-customer toggle |
| Consolidated invoice for huge property portfolio (50+ line items) → PDF render fails | Test with realistic Sapphire commercial data; paginate PDFs >20 properties |
| Dunning email sent in error after late payment | Idempotency check: query `Payment` table before sending each step; never send dunning if invoice is paid |

## Things easy to overlook

- **Receipts**: Stripe sends one automatically. Portal should also surface a QP-branded one. Don't double-send if Stripe receipt is enabled.
- **Refund window**: Stripe refunds work for 180 days post-charge. Older refunds need manual handling.
- **Disputes/chargebacks**: On Connect Standard, disputes go to the tenant's Stripe dashboard. They handle, not QP. Document this in onboarding so tenants know.
- **Payout schedule**: Standard accounts default to daily after 2-day rolling delay. Tenants can configure in their own dashboard. QP doesn't need UI for this.
- **Failed onboarding retries**: Connect onboarding can hit verification issues (KYC failure, bank rejection). Status webhook + clear retry path required.
- **ACH return codes**: NSF is one of ~20 ACH return codes. Surface the human-readable reason in the dunning email if known.
- **Currency**: Hard-code USD for V1. Multi-currency is a defer.
- **Invoice numbering across orgs**: Each org's invoices should have their own numbering sequence. Already separated via `org_id`; verify the numbering query is scoped.
- **Billing on the same day as service**: Customer pays autopay at 6 AM, tech does service at 10 AM, customer asks "did I pay for today?" Portal needs to clearly show "covers period {{X}} through {{Y}}".
- **Org switches Stripe mode**: Defined as **not supported** for V1. Document explicitly.
- **Migration from current single-tenant Stripe to Connect for new orgs**: Existing test PaymentMethods on the platform Stripe stay there; new orgs sign up clean. No data migration needed.
- **Test mode vs live mode**: Use Stripe test keys throughout development. Phase 0 includes deciding when to flip Sapphire (and only Sapphire) to live mode for a real first invoice.

## Open questions

- **Application fee model**: 0% for V1 (free) or charge a fee from day one? Recommend 0% for first 10 orgs to remove adoption friction; introduce % when Phase 1 of a SaaS-subscription model lands.
- **Per-org Postmark sender** for dunning emails vs shared QP Postmark: dunning emails go through `EmailService.send_agent_reply` which already routes per-org. Verify the sender domain reputation isn't affected by aggressive dunning sends.
- **Customer portal contact model**: V1 logs in by `CustomerContact.email`. What happens when one customer has multiple contacts (billing@ + ops@)? Recommend: each contact gets their own session; both see the same billing data scoped to the customer.
- **Statement period boundaries**: Calendar month (Jan 1 – Jan 31) or anniversary (signup-day + 30)? Recommend: calendar month (matches commercial AP cycles).
- **Refund-to-original-method vs credit-on-account**: Default behavior when admin issues a credit memo against a paid invoice? Recommend: ask in the dialog ("Refund to original payment method" / "Apply credit to next invoice") with refund as default.
- **Suspending dunning during a service hold**: If a customer is on vacation hold, does the prior period's past-due invoice still trigger dunning? Recommend: yes — the hold is for service, not for paying for service already rendered.

## Pre-launch checklist (final week before May 1)

- [ ] VVG-owned Stripe live keys configured (`STRIPE_SECRET_KEY=sk_live_...`, `STRIPE_PUBLISHABLE_KEY=pk_live_...`)
- [ ] `STRIPE_WEBHOOK_SECRET=whsec_...` set
- [ ] Webhook endpoint (`https://app.quantumpoolspro.com/api/v1/public/stripe/webhook`) registered in Stripe dashboard with required events subscribed
- [ ] Bluevine bank account confirmed as payout destination in Stripe dashboard
- [ ] APScheduler `_run_billing_cycle` and `_run_payment_retries` jobs uncommented in `app/app.py`
- [ ] `_run_dunning_sequence` job added to scheduler
- [ ] One Sapphire customer (Brian's choice) configured with a real card + a test invoice — full end-to-end charge succeeds, receipt arrives
- [ ] Magic-link email tested end-to-end on a real Gmail account
- [ ] Customer portal tested on iPhone + Android mobile browser
- [ ] Sentry tag `stripe.event_type` confirmed appearing on webhook events
- [ ] ntfy alerts wired for: failed dunning send, webhook signature failure
- [ ] `docs/billing-dormant.md` updated to mark billing as live; or deleted per its removal note

## Related docs

- `docs/billing-dormant.md` — inventory of pre-existing wiring (this plan extends it).
- `memory/payment_reconciliation.md` — Payment Reconciliation Phase 1 (already shipped, complementary).
- `memory/feedback_no_auto_send.md` — DNA rule #5 (AI never auto-sends; system-templated dunning is out of scope for this rule).
- `docs/build-plan.md` — Phase 3c (Invoicing) covers prior invoicing work.
