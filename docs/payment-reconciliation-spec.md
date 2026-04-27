# Payment Reconciliation — Phase 1 (Entrata)

> Refinement spec. Phase 1 of a multi-phase build that automates the
> third-party-payment-processor → QP-invoice match. Remove this file
> when Phase 1 ships + archives.

## 1. Purpose

Brian's current process: scan the accounting folder + bank statements,
manually match each notification to a QP invoice, mark paid. High
miss rate, prone to error, mixes payments across properties when a
processor sends them in one threaded email. Per dogfood feedback
2026-04-27: "I miss payments."

Phase 1 ships the architecture (plugin parsers, structured
`parsed_payments` table, matcher with auto-mark logic, reconciliation
view) + the first parser (Entrata — highest-signal, simplest format).
Phases 2–5 add more parsers; the architecture doesn't change.

## 2. DNA alignment

- **Less work for the user** (rule 6): collapses a manual-scan workflow
  into a 1-click reconciliation surface.
- **Build for the 1,000th customer** (rule 1): plugin pattern means
  every new processor is one module + one test file, not architectural
  refactor.
- **AI never commits to customer** (rule 5): non-applicable here —
  payment reconciliation is internal state, not customer-facing.
  Auto-mark on unambiguous matches is the right default.
- **Data capture is king**: parsed payment data persists separately
  from the AgentMessage so re-running parsers (when logic improves)
  re-enriches without re-fetching mail.
- **Every agent learns** (rule 2): not directly applicable in v1 — the
  parsers are deterministic regex/structured-text extractors. If we
  later add LLM fallback for unparseable formats, those go through
  AgentLearningService.

## 3. Architecture

### 3.1 New table: `parsed_payments`

```sql
CREATE TABLE parsed_payments (
  id                  uuid PRIMARY KEY,
  organization_id     varchar(36) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  agent_message_id    varchar(36) NOT NULL REFERENCES agent_messages(id) ON DELETE CASCADE,
  processor           varchar(40) NOT NULL,         -- "entrata" | "yardi" | "appfolio" | ...
  amount              numeric(12, 2),               -- NULL when processor doesn't include amount (Coupa)
  payer_name          varchar(255),                 -- "Pointe on Bell" or "AIR COMMUNITIES"
  property_hint       varchar(255),                 -- Entrata "Property" field, etc.
  invoice_hint        varchar(100),                 -- their invoice # (NOT necessarily QP's)
  payment_method      varchar(20),                  -- check | ach | credit_card | other
  payment_date        date,                         -- when the payment was processed by them
  reference_number    varchar(100),                 -- their payment/transaction #
  raw_block           text,                         -- the chunk of email body parsed (audit)
  match_status        varchar(20) NOT NULL,         -- unmatched | auto_matched | proposed | manual_matched | ignored
  matched_invoice_id  varchar(36) REFERENCES invoices(id) ON DELETE SET NULL,
  payment_id          varchar(36) REFERENCES payments(id) ON DELETE SET NULL,
  match_confidence    real,                         -- 0.0 – 1.0
  match_reasoning     text,                         -- "exact invoice# + amount + customer"
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_parsed_payments_org_status ON parsed_payments (organization_id, match_status);
CREATE INDEX ix_parsed_payments_message ON parsed_payments (agent_message_id);
CREATE INDEX ix_parsed_payments_processor ON parsed_payments (processor);
```

Why a separate table (vs. JSONB on `agent_messages`):
- One email can produce N parsed payments (Yardi remittances are
  tabular). JSONB would require array shape from day 1.
- Indexable by status — the reconciliation queue is a `WHERE
  match_status='unmatched'` query.
- Re-parseable: deleting + re-inserting parsed_payments rows for a
  message is safe; the source email stays untouched.

### 3.2 New column: `payments.source_message_id`

```sql
ALTER TABLE payments ADD COLUMN source_message_id varchar(36)
  REFERENCES agent_messages(id) ON DELETE SET NULL;
CREATE INDEX ix_payments_source_message ON payments (source_message_id);
```

Audit trail: the Payment knows which email it came from. Reconciliation
UI links the Payment row → the source email thread.

### 3.3 Pending vs completed lifecycle

`PaymentStatus` enum currently has: `completed`, `pending`, `failed`,
`refunded`. Phase 1 uses:
- `completed`: funds confirmed received (ACH/online/Stripe — auto on
  parser output; or check after Brian clicks "received").
- `pending`: parser saw a check-mailed notification; check hasn't
  arrived yet. Lives in the reconciliation "Pending checks" tab.

When the parser sets `payment_method=check`, the matcher creates the
Payment as `pending`. All other methods → `completed` immediately.

### 3.4 Parser plugin pattern

```python
# app/src/services/payments/parsers/__init__.py
from .entrata import EntrataParser
PARSERS: list[Parser] = [EntrataParser()]   # Phase 2+ append here

# app/src/services/payments/parsers/base.py
class Parser(Protocol):
    processor_id: str
    def matches(self, msg: AgentMessage) -> bool: ...
    def parse(self, msg: AgentMessage) -> list[ParsedPaymentDraft]: ...

@dataclass
class ParsedPaymentDraft:
    amount: Decimal | None
    payer_name: str | None
    property_hint: str | None
    invoice_hint: str | None
    payment_method: str | None  # check | ach | credit_card | other
    payment_date: date | None
    reference_number: str | None
    raw_block: str
```

Each parser is responsible for:
- `matches(msg)` — quick check (sender domain, subject keywords) to
  decide whether to bother running `parse`. False = skip.
- `parse(msg)` — extract 0+ ParsedPaymentDraft records. Returning `[]`
  on a matched message is fine (e.g., a non-payment Stripe notification).

### 3.5 PaymentMatcher service

`app/src/services/payments/matcher.py`. After each parser run, the
matcher:
1. Loads open invoices for the org (`status IN ('sent', 'viewed', 'overdue')`).
2. For each ParsedPayment, computes a candidate score against each
   open invoice:
   - **Invoice number exact match**: 1.0 (only when parser produced
     `invoice_hint` AND it equals `invoices.invoice_number` — for
     Phase 1 the QP customer's invoice numbers don't match the third
     party's, so this rarely fires; useful for edge cases where a
     customer references QP's number directly).
   - **Amount exact + customer fuzzy ≥85**: 0.95 if single candidate,
     0.70 if multiple.
   - **Amount within $0.01 + property hint matches Property.name**:
     0.90 if single candidate.
   - **Amount only**: 0.50 — never auto-match on amount alone.
3. **Decision**:
   - confidence ≥0.90 AND only one candidate at that level → auto-match.
     Create Payment, set `Invoice.status` according to whether full
     amount paid, link via `parsed_payments.matched_invoice_id` +
     `payment_id`.
   - confidence in [0.50, 0.90) → `match_status="proposed"`. Stages
     a `payment_match` proposal (NEW entity_type). Brian reviews on
     the reconciliation page.
   - no candidates above 0.50 → `match_status="unmatched"`. Surfaces
     in the unmatched tab; Brian manually selects an invoice or
     dismisses.

### 3.6 New proposal entity type: `payment_match`

For ambiguous cases. Payload: `{parsed_payment_id, invoice_id}`. On
accept, the creator runs the same code path as auto-match: create
Payment, link, bump invoice status. On reject, mark
`parsed_payments.match_status="ignored"`.

Phase 1 wires this into the reconciliation page directly (not the
generic ProposalCard surface) — the page is purpose-built for this
workflow. Phase 2 may surface payment_match proposals on the
dashboard widget too.

### 3.7 Reconciliation page

`/billing/reconciliation`. Three tabs:

- **Pending checks**: `Payment.status='pending'`. Each row: payer,
  property, amount, parsed-from email date, "Mark received" button.
  One click → `Payment.status="completed"`, `Invoice.status="paid"`
  (if total amount), notification fired.
- **Needs review**: `parsed_payments.match_status='proposed'`. Each
  row: parsed amount + payer + property, candidate invoices
  (amount, date, customer) ranked by score. Accept = create Payment.
  Reject = `match_status="ignored"`.
- **Unmatched**: `parsed_payments.match_status='unmatched'`. Each row:
  parsed payment data + "Match to invoice" picker (search by
  customer/amount). Selecting an invoice creates Payment. Dismiss =
  `match_status="ignored"`.

Auto-matched payments don't appear here — they're invisible by
default. A "View recent auto-matches" link at the top opens a
read-only tab listing the last 30 days for audit.

### 3.8 Notification on auto-match

When the matcher auto-creates a Payment (high-confidence), fire ntfy:
"Auto-matched payment: $1,776.00 from Arbor Ridge 2 → INV-1234."
Keeps Brian in the loop without requiring him to check the
reconciliation surface daily.

## 4. Decisions made (no questions)

- **Permission gate**: `invoices.create`. Owner + admin + manager
  preset already have it; matches the existing surface for who can
  record payments.
- **Customer fuzzy match**: rapidfuzz (already in deps), token-set
  ratio, threshold 85. Property fuzzy match: same scorer.
- **Re-parsing**: out of Phase 1 (script + endpoint added in Phase 2
  when there are >1 parsers and a clear need to backfill). Phase 1's
  parser will only run on new mail.
- **Stripe email parser**: skipped in Phase 1. The webhook already
  records Stripe payments; the email parser would need to dedupe
  against webhook output. Worth solving once, in Phase 4.
- **Coupa**: skipped Phase 1 (no amount in email; their invoice # ≠
  QP's; needs manual-select assist UI). Phase 3.

## 5. Rollout steps (8)

1. Migration: `parsed_payments` table + `payments.source_message_id` column.
2. Models: `ParsedPayment` model + `Payment.source_message_id` mapped column.
3. Parser plugin pattern + `EntrataParser` + tests.
4. Orchestrator hook: after billing classification, run parsers, persist `ParsedPayment` rows. Tests.
5. `PaymentMatcher` service: scoring + auto-create + status lifecycle + tests.
6. New proposal entity_type `payment_match` + creator + tests (small).
7. Reconciliation API: 3 list endpoints + mark-received + manual-match. Tests.
8. Frontend `/billing/reconciliation` page with 3 tabs.

## 6. Definition of done

- [ ] Migration applied; both DDL changes verified.
- [ ] EntrataParser passes 5+ unit tests (single payment, check vs ACH, missing fields, malformed body, non-Entrata sender returns False from `matches`).
- [ ] Orchestrator runs parsers on billing-category messages; existing classification flow unchanged when no parser matches.
- [ ] Matcher tests cover: exact invoice#, amount+customer fuzzy single candidate (auto), amount+customer multiple candidates (proposed), amount only (unmatched).
- [ ] Auto-matched payments link via `Payment.source_message_id` + `parsed_payments.payment_id`.
- [ ] Pending check creates Payment with `status='pending'`; mark-received endpoint flips to `completed` and bumps invoice.
- [ ] Reconciliation page renders all three tabs; mark-received + accept-proposed + manual-match flows all work end-to-end on dev DB with synthetic data.
- [ ] Sapphire backfill: re-process the existing 5 Entrata billing emails in the dev DB; verify zero false auto-matches (the threshold should leave them in `unmatched` if no QP invoice exists for the property — which is the correct outcome v1 since QP doesn't yet store these PMs as Customers).
- [ ] R5 + R7 audits clean.
- [ ] Notification on auto-match fires (verify via ntfy log or Sentry breadcrumb).

## 7. Out of scope (future phases)

- Phase 2: YardiParser (multi-row table extraction).
- Phase 3: AppFolioParser, CoupaParser (manual-select assist).
- Phase 4: Stripe email parser (dedupe vs webhook).
- Phase 5: Bank CSV import (uses same matcher).
- Phase 6: LLM fallback parser for unrecognized billing-category mail.
- Re-parse script + endpoint (Phase 2).
- Per-customer "default invoice numbering match" — store the third
  party's invoice # on QP invoices when sent, enabling 1.0 match
  on Coupa-style notifications without manual intervention.
