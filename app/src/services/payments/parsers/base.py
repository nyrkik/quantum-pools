"""Parser plugin pattern — Phase 1 payment reconciliation.

Each Parser knows ONE processor (Entrata, Yardi, AppFolio, ...).
`matches(msg)` is a quick pre-filter (sender domain, subject keywords)
that decides whether to bother running `parse`. `parse(msg)` extracts
0+ ParsedPaymentDraft records — Yardi can return many from a single
remittance email; Entrata returns 1; some matched messages return 0
when content turns out to be a non-payment notification.

Parsers are PURE: no DB access, no API calls. The orchestrator hook
(see `payments/ingest.py`) calls each parser in sequence and persists
the survivors as `parsed_payments` rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol


@dataclass
class ParsedPaymentDraft:
    """One parsed payment from one source email."""

    amount: Decimal | None
    payer_name: str | None
    property_hint: str | None
    invoice_hint: str | None
    payment_method: str | None  # check | ach | credit_card | other
    payment_date: date | None
    reference_number: str | None
    raw_block: str  # the chunk of email body the data came from


class Parser(Protocol):
    """Stable identifier (e.g. `"entrata"`) used as the
    `parsed_payments.processor` value and for parser registry lookups."""
    processor_id: str

    def matches(self, *, from_email: str, subject: str | None) -> bool:
        """Quick pre-filter. False means skip this parser for this email."""
        ...

    def parse(self, *, body: str) -> list[ParsedPaymentDraft]:
        """Extract zero or more payment drafts from the email body.
        Empty list = parser recognized the format but the email isn't
        a payment notification (returning [] is fine, not an error)."""
        ...
