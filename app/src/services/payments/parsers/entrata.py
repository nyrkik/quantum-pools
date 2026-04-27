"""Entrata parser — Phase 1 payment reconciliation.

Entrata sends one payment per email. The body has a fixed key:value
shape:

    PAYMENT FOR Sapphire Pool Service
    Processed

    Payment #  3151
    Property   Arbor Ridge 2
    Type       Check
    Amount     $1,776.00
    Date       04/24/2026

`Type` is "Check" or "ACH" (others possible but rare). The parser
extracts all fields and normalizes:
- amount → Decimal
- payment_method → check | ach | other
- payment_date → date(yyyy, mm, dd)
- reference_number → the Payment # (Entrata's, not QP's)

Because the email body comes through inscriptis-rendered HTML in
production, fields can be space-padded. The regex extractor tolerates
runs of whitespace.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from src.services.payments.parsers.base import ParsedPaymentDraft


# Each line: "  Key   Value  ". Capture them lenient on whitespace.
_KV_PATTERNS = {
    "payment_number": re.compile(
        r"Payment\s*#\s+(\S+)", re.IGNORECASE,
    ),
    "property": re.compile(
        r"Property\s+(.+?)\s{2,}", re.IGNORECASE,
    ),
    "type": re.compile(
        r"Type\s+(\S+)", re.IGNORECASE,
    ),
    "amount": re.compile(
        r"Amount\s+\$?([\d,]+\.\d{2})", re.IGNORECASE,
    ),
    "date": re.compile(
        r"Date\s+(\d{1,2}/\d{1,2}/\d{2,4})", re.IGNORECASE,
    ),
    "payer": re.compile(
        # "PAYMENT FOR Sapphire Pool Service" — the recipient is QP itself
        # in v1; Entrata's "from" is the property mgmt company implicit in
        # the Property field. We use Property as the payer hint.
        r"PAYMENT FOR\s+(.+?)\s{2,}", re.IGNORECASE,
    ),
}


_METHOD_NORMALIZATION = {
    "check": "check",
    "ach": "ach",
    "echeck": "ach",
    "card": "credit_card",
}


class EntrataParser:
    processor_id = "entrata"

    def matches(self, *, from_email: str, subject: str | None) -> bool:
        if not from_email:
            return False
        addr = from_email.lower()
        if "entrata" in addr:
            return True
        # Subject fallback for forwarded mail or alias domains.
        if subject and "powered by entrata" in subject.lower():
            return True
        return False

    def parse(self, *, body: str) -> list[ParsedPaymentDraft]:
        if not body:
            return []
        # Single-payment shape. Either we extract enough fields or we
        # bail with []. Enough = amount + payment_number + (property OR
        # date). Anything less makes the row useless for matching.
        fields: dict[str, str] = {}
        for key, pat in _KV_PATTERNS.items():
            m = pat.search(body)
            if m:
                fields[key] = m.group(1).strip()

        amount = _to_decimal(fields.get("amount"))
        if amount is None:
            return []
        payment_number = fields.get("payment_number")
        if not payment_number:
            return []
        property_hint = fields.get("property")
        payment_date = _to_date(fields.get("date"))
        if not property_hint and not payment_date:
            return []

        method_raw = (fields.get("type") or "").lower()
        method = _METHOD_NORMALIZATION.get(method_raw, "other" if method_raw else None)

        return [ParsedPaymentDraft(
            amount=amount,
            payer_name=property_hint,  # Entrata uses property name as the payer surface
            property_hint=property_hint,
            invoice_hint=None,  # Entrata payment # ≠ QP invoice #
            payment_method=method,
            payment_date=payment_date,
            reference_number=payment_number,
            raw_block=body[:2000],
        )]


def _to_decimal(raw: str | None) -> Decimal | None:
    if not raw:
        return None
    cleaned = raw.replace(",", "").strip()
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _to_date(raw: str | None) -> date | None:
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None
