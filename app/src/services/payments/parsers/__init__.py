"""Parser registry for Phase 1 payment reconciliation.

Each parser registers via the `PARSERS` list. The orchestrator hook
(see `payments/ingest.py`) iterates this list per billing-category
email; the first parser whose `matches()` returns True is run, and
its `parse()` output becomes parsed_payments rows.

Phase 1 ships Entrata only. Phases 2-5 append YardiParser,
AppFolioParser, CoupaParser, StripeEmailParser.
"""

from __future__ import annotations

from src.services.payments.parsers.base import (
    ParsedPaymentDraft,
    Parser,
)
from src.services.payments.parsers.entrata import EntrataParser


PARSERS: list[Parser] = [
    EntrataParser(),
]


__all__ = ["PARSERS", "Parser", "ParsedPaymentDraft", "EntrataParser"]
