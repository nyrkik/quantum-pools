# Billing Infrastructure — DORMANT

> **Status (2026-04-13):** Built but not in use. APScheduler jobs are commented out. No customer has a card on file. No real Stripe account is configured. **Do NOT re-enable without Brian's explicit approval** — see "Why dormant" below.

---

## What's Wired Up

A complete card-on-file + recurring billing + autopay system was built across two prior sessions. Inventory:

### Models
- **Customer** (`app/src/models/customer.py`)
  - Stripe: `stripe_customer_id`, `stripe_payment_method_id`, `stripe_card_last4`, `stripe_card_brand`, `stripe_card_exp_month`, `stripe_card_exp_year`
  - Billing cycle: `billing_day_of_month`, `next_billing_date`, `last_billed_at`, `billing_frequency`
  - Autopay: `autopay_enabled`, `autopay_failure_count`, `autopay_last_failed_at`, `card_setup_token`
- **Invoice** (`app/src/models/invoice.py`)
  - Recurring: `is_recurring`, `generation_source` (manual/recurring/autopay), `billing_period_start/end`
  - Stripe: `stripe_payment_intent_id`
  - Public pay link: `payment_token`
- **Payment** (`app/src/models/payment.py`)
  - Stripe: `stripe_payment_intent_id`, `stripe_charge_id`
  - `is_autopay` flag
- **AutopayAttempt** (`app/src/models/autopay_attempt.py`)
  - Audit trail per charge attempt with retry schedule

### Services
- **StripeService** (`app/src/services/stripe_service.py`)
  - `create_checkout_session()` — one-time Stripe Checkout
  - `create_setup_intent()` — generates SetupIntent + `card_setup_token`
  - `save_payment_method()`, `detach_payment_method()`
  - `charge_autopay()` — off-session charge with retry
  - Webhook handlers: `handle_checkout_completed`, `handle_payment_intent_succeeded`, `handle_payment_intent_failed`, `handle_setup_intent_succeeded`, `handle_charge_refunded`
- **BillingService** (`app/src/services/billing_service.py`)
  - `generate_recurring_invoices(org_id)` — daily job, generates invoices + attempts autopay
  - `retry_failed_payments(org_id)` — retries failed attempts per schedule
  - Reporting: `get_upcoming_billing()`, `get_failed_payments()`, `get_billing_stats()`
- **PaymentService** (`app/src/services/payment_service.py`)
  - Manual payment recording

### API endpoints
- **`/api/v1/billing/*`** (owner/admin only) — stats, upcoming, failed-payments, manual generate/retry triggers
- **`/api/v1/payments/*`** — list, record manual payments
- **`/api/v1/invoices/*`** — full CRUD, send, void, write-off, approve estimates
- **`/api/v1/customers/{id}/setup-intent`** — generate card setup token
- **`/api/v1/customers/{id}/payment-method`** (DELETE) — remove card
- **`/api/v1/public/invoice/{token}`** — public pay page (no auth)
- **`/api/v1/public/card/{token}`** — public card setup page (no auth)
- **`/api/v1/public/stripe/webhook`** — Stripe event receiver (signature-verified if `STRIPE_WEBHOOK_SECRET` set)

### Frontend
- **`/card/[token]/page.tsx`** — public card setup page using Stripe Elements
- **`components/customers/tiles/billing-tile.tsx`** — billing tile on customer detail (autopay toggle, send setup link, remove card)
- Stripe.js + `@stripe/react-stripe-js` in `package.json`

### APScheduler jobs (currently DISABLED in `app/app.py`)
```python
# scheduler.add_job(_run_billing_cycle, CronTrigger(hour=6, minute=0), id="billing_cycle")
# scheduler.add_job(_run_payment_retries, CronTrigger(hour=10, minute=0), id="payment_retries")
```

### Migrations
- `b92531d2ea61` — initial invoices/payments + Stripe columns on customer
- `23323b58b603` — autopay_attempts table + dunning columns

### Env vars
- `STRIPE_SECRET_KEY` — currently set to `sk_test_51TJ...` (orphan test key, **not** for any real Stripe account QP would use in production)
- `STRIPE_PUBLISHABLE_KEY` — `pk_test_51TJ...` (same)
- `STRIPE_WEBHOOK_SECRET` — **NOT SET** (webhook signatures bypassed in dev mode)

---

## Why Dormant

1. **No real Stripe account exists yet** for QP or Sapphire. The keys in `.env` belong to an unrelated test account from a prior session.
2. **No customer has a card on file** (`stripe_customer_id IS NULL` for all 74 customers).
3. **Brian was setting Stripe up for VVG** when prior sessions started wiring billing without discussion. The scope wasn't agreed.
4. **Multi-tenant gap**: current code uses `settings.stripe_secret_key` (single account for the whole app). For a real SaaS where multiple orgs collect from their own customers, each org needs its own **Stripe Connect** account (Standard or Express). The current architecture only works for one tenant.
5. **Webhook secret not set** — production-grade signature verification is bypassed.
6. **No active billing workflow** at Sapphire today — Brian doesn't currently bill through QP.

Disabling the scheduler prevents:
- Pointless daily DB queries
- Risk of accidentally charging once cards are added
- Future confusion about whether the system is "live"

---

## What Was Cleaned Up (2026-04-13)

- **APScheduler jobs commented out** in `app/app.py` (`_run_billing_cycle`, `_run_payment_retries`). Re-enable by uncommenting two lines.
- **Stale autopay flag cleared** for 21 customers that had `autopay_enabled=true` from the PSS CSV import but no card on file. They were misleading — code thought they were autopay customers.
- All billing code preserved. No deletes.

---

## To Re-Enable (when Brian's ready)

### Step 1: Decide tenancy model

**Option A — Single account (current architecture):**
- One Stripe account collects everyone's money (Sapphire + all future customers)
- Money flows to one bank account
- Workable only if QP is your business's billing tool, not a multi-tenant SaaS

**Option B — Stripe Connect (proper SaaS):**
- Each org has its own Stripe account, connects via OAuth
- Money flows to each org's bank account
- Required before onboarding any customer org other than Sapphire
- Code change: `StripeService` needs to read keys from `Organization.stripe_account_id` instead of env vars
- Plus all the Stripe Connect onboarding UI flows

### Step 2: Get Stripe credentials
- Create Stripe account (whoever the legal collecting entity is — VVG LLC currently, QP LLC eventually)
- Replace test keys in `.env`:
  ```
  STRIPE_SECRET_KEY=sk_test_<real test key>
  STRIPE_PUBLISHABLE_KEY=pk_test_<real test key>
  ```
- Add `STRIPE_WEBHOOK_SECRET=whsec_...` from Stripe dashboard

### Step 3: Configure Stripe dashboard
- Stripe → Developers → Webhooks → Add endpoint:
  `https://app.quantumpoolspro.com/api/v1/public/stripe/webhook`
- Subscribe to events: `checkout.session.completed`, `payment_intent.succeeded`, `payment_intent.payment_failed`, `setup_intent.succeeded`, `charge.refunded`

### Step 4: Re-enable scheduler
In `app/app.py`, uncomment:
```python
scheduler.add_job(_run_billing_cycle, CronTrigger(hour=6, minute=0), id="billing_cycle")
scheduler.add_job(_run_payment_retries, CronTrigger(hour=10, minute=0), id="payment_retries")
```

### Step 5: Pilot with one customer
- Pick a Sapphire customer Brian is OK testing with
- Set `monthly_rate`, `billing_frequency='monthly'`, `billing_day_of_month`, `next_billing_date`
- Send card setup link via the billing tile
- Verify card saves, verify next scheduled billing day generates an invoice and (if autopay) charges

### Step 6: Roll out gradually
- Add a few more customers
- Watch the failed-payments dashboard
- Verify dunning emails send correctly

### Step 7: Flip to live keys
- Once test mode is verified end-to-end, swap to `sk_live_` / `pk_live_` keys
- Re-add live webhook endpoint with new `whsec_` secret
- Done

---

## Removal Note

When billing is fully live and stable for 30+ days, delete this doc and remove the index entry from CLAUDE.md.
