"""Payment ingestion — runs parsers against billing-category emails
and persists the structured output as parsed_payments rows.

Called from the orchestrator after classification. Wrapped in
try/except at the call site so a parser failure never breaks email
ingest.

Design:
- Iterate the parser registry (src/services/payments/parsers).
- First parser whose `matches()` returns True wins. Run its `parse()`.
- For each ParsedPaymentDraft, create a parsed_payments row in
  match_status='unmatched' (the matcher service will score + flip
  status downstream).
- The matcher runs synchronously here too — same transaction. Auto-
  matches create Payments + bump invoice status. Ambiguous → status
  'proposed'. No candidates → leave 'unmatched' for the reconciliation
  surface.
"""

from __future__ import annotations

import logging
import uuid
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.agent_message import AgentMessage
from src.models.parsed_payment import ParsedPayment, ParsedPaymentStatus
from src.services.payments.parsers import PARSERS
from src.services.payments.parsers.base import Parser

logger = logging.getLogger(__name__)


async def ingest_billing_message(
    db: AsyncSession,
    *,
    msg: AgentMessage,
    parsers: Iterable[Parser] | None = None,
) -> list[ParsedPayment]:
    """Run parsers against the message; persist parsed_payments rows.

    Returns the persisted rows for the caller (matcher) to act on.

    The orchestrator should ALWAYS wrap this call in try/except so a
    bad parser doesn't break email ingest. Inside this function we
    only catch per-parser failures so other parsers can still run.
    """
    if msg.category != "billing":
        return []
    if not msg.body:
        return []

    parser_list = list(parsers if parsers is not None else PARSERS)
    persisted: list[ParsedPayment] = []

    for parser in parser_list:
        try:
            if not parser.matches(
                from_email=msg.from_email or "",
                subject=msg.subject,
            ):
                continue
            drafts = parser.parse(body=msg.body or "")
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "payment parser %s failed for msg=%s: %s",
                getattr(parser, "processor_id", "?"), msg.id, e,
            )
            continue

        for draft in drafts:
            row = ParsedPayment(
                id=str(uuid.uuid4()),
                organization_id=msg.organization_id,
                agent_message_id=msg.id,
                processor=parser.processor_id,
                amount=draft.amount,
                payer_name=draft.payer_name,
                property_hint=draft.property_hint,
                invoice_hint=draft.invoice_hint,
                payment_method=draft.payment_method,
                payment_date=draft.payment_date,
                reference_number=draft.reference_number,
                raw_block=draft.raw_block,
                match_status=ParsedPaymentStatus.unmatched.value,
            )
            db.add(row)
            persisted.append(row)

        if drafts:
            # First matching parser wins. Don't double-process the same
            # email with two parsers — they should be mutually exclusive
            # by sender, but defensive break.
            break

    if persisted:
        await db.flush()
        logger.info(
            "payment_ingest: msg=%s persisted=%d processor=%s",
            msg.id, len(persisted),
            persisted[0].processor if persisted else "?",
        )
    return persisted
