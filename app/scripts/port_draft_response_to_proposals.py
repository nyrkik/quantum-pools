"""Port pre-Phase-5 `AgentMessage.draft_response` rows into `agent_proposals`
+ `agent_corrections`. Phase 5 Step 4. One-shot, idempotent.

For every inbound `AgentMessage` with `draft_response IS NOT NULL`:
- Derive final proposal status + correction_type from `(status, final_response, draft_response)`.
- Synthesize one `agent_proposals` row with `agent_type='email_drafter'`,
  `entity_type='email_reply'`, `source_type='agent_message'`, `source_id=msg.id`.
- Synthesize one `agent_corrections` row (when applicable) pointing back to the
  proposal so `AgentLearningService.build_lessons_prompt` picks it up via the
  canonical query. This replaces `classifier.get_correction_history`.

Idempotent: re-running skips messages whose proposal already exists (matched by
`source_type='agent_message' AND source_id=msg.id AND agent_type='email_drafter'`).

Status derivation (grounded in 2026-04-23 Sapphire snapshot):

  | msg.status  | final_response   | proposal.status | correction_type |
  |-------------|------------------|-----------------|-----------------|
  | sent        | = draft          | accepted        | acceptance      |
  | sent        | != draft, !NULL  | edited          | edit            |
  | sent        | NULL             | expired         | (none)          |
  | auto_sent   | = draft (or NULL)| accepted        | acceptance      |
  | handled     | = draft          | accepted        | acceptance      |
  | handled     | NULL             | rejected        | rejection       |
  | ignored     | *                | rejected        | rejection       |
  | dismissed   | *                | rejected        | rejection       |
  | rejected    | *                | rejected        | rejection       |
  | pending     | NULL             | staged          | (none)          |
  | other       | *                | expired         | (none)          |

Edits: `user_delta` is a minimal RFC 6902 patch (replace /body) so the learning
path can diff draft vs. final if it wants to.

Usage:
    python app/scripts/port_draft_response_to_proposals.py --dry-run
    python app/scripts/port_draft_response_to_proposals.py --org <uuid>
    python app/scripts/port_draft_response_to_proposals.py           # full run

Exits non-zero if parity assertion fails
(`COUNT(draft_response IS NOT NULL) != COUNT(ported agent_proposals)`).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
)

from sqlalchemy import and_, func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from src.core.database import get_engine, get_session_maker  # noqa: E402
from src.models.agent_correction import AgentCorrection  # noqa: E402
from src.models.agent_message import AgentMessage  # noqa: E402
from src.models.agent_proposal import (  # noqa: E402
    STATUS_ACCEPTED,
    STATUS_EDITED,
    STATUS_EXPIRED,
    STATUS_REJECTED,
    STATUS_STAGED,
    AgentProposal,
)


AGENT_TYPE = "email_drafter"
ENTITY_TYPE = "email_reply"
SOURCE_TYPE = "message"  # matches orchestrator's stage() call — keyed on AgentMessage.id


def _derive(msg: AgentMessage) -> tuple[str, Optional[str]]:
    """Return (proposal_status, correction_type|None) for this message."""
    s = msg.status
    fr = msg.final_response
    dr = msg.draft_response

    if s == "sent":
        if fr is None:
            return STATUS_EXPIRED, None
        return (STATUS_ACCEPTED, "acceptance") if fr == dr else (STATUS_EDITED, "edit")
    if s == "auto_sent":
        return STATUS_ACCEPTED, "acceptance"
    if s == "handled":
        if fr is not None and fr == dr:
            return STATUS_ACCEPTED, "acceptance"
        return STATUS_REJECTED, "rejection"
    if s in ("ignored", "dismissed", "rejected"):
        return STATUS_REJECTED, "rejection"
    if s == "pending":
        return STATUS_STAGED, None
    return STATUS_EXPIRED, None


def _resolved_at(msg: AgentMessage) -> datetime:
    """Best-effort: when did the human resolve this draft?"""
    for attr in ("approved_at", "sent_at", "updated_at", "received_at"):
        v = getattr(msg, attr, None)
        if v is not None:
            return v
    return datetime.now(timezone.utc)


def _build_payload(msg: AgentMessage, body: str) -> dict:
    """Mimic the shape EmailReplyProposalPayload accepts so a re-accept (if ever
    needed) round-trips cleanly. `to` is the inbound sender (we reply to them)."""
    return {
        "thread_id": msg.thread_id,
        "reply_to_message_id": msg.id,
        "to": msg.from_email or "",
        "subject": msg.subject or "",
        "body": body,
        "customer_id": msg.matched_customer_id,
    }


async def _find_outbound_after(
    db: AsyncSession, thread_id: str, resolved_at: datetime,
) -> Optional[str]:
    """Best-effort join to the outbound AgentMessage that actually got sent.
    Matches by same thread + direction=outbound + received_at within 1h window
    of resolve time. Returns the outbound id or None."""
    if thread_id is None:
        return None
    lo = resolved_at - timedelta(hours=1)
    hi = resolved_at + timedelta(hours=1)
    row = (await db.execute(
        select(AgentMessage.id).where(
            AgentMessage.thread_id == thread_id,
            AgentMessage.direction == "outbound",
            AgentMessage.received_at >= lo,
            AgentMessage.received_at <= hi,
        ).order_by(AgentMessage.received_at.asc()).limit(1)
    )).scalar_one_or_none()
    return row


async def _existing_proposal_id(db: AsyncSession, msg_id: str) -> Optional[str]:
    return (await db.execute(
        select(AgentProposal.id).where(
            AgentProposal.agent_type == AGENT_TYPE,
            AgentProposal.source_type == SOURCE_TYPE,
            AgentProposal.source_id == msg_id,
        )
    )).scalar_one_or_none()


async def port(db: AsyncSession, *, org_id: Optional[str], dry_run: bool) -> dict:
    q = select(AgentMessage).where(AgentMessage.draft_response.isnot(None))
    if org_id:
        q = q.where(AgentMessage.organization_id == org_id)
    q = q.order_by(AgentMessage.received_at.asc())
    rows = (await db.execute(q)).scalars().all()

    counts: dict[str, int] = {
        "total": len(rows),
        "skipped_already_ported": 0,
        "created_proposal": 0,
        "created_correction": 0,
        "by_proposal_status": {},
        "by_correction_type": {},
    }
    samples: list[dict] = []
    SAMPLE_CAP = 5

    for msg in rows:
        existing = await _existing_proposal_id(db, msg.id)
        if existing:
            counts["skipped_already_ported"] += 1
            continue

        proposal_status, correction_type = _derive(msg)
        resolved_at = _resolved_at(msg)
        proposed_payload = _build_payload(msg, msg.draft_response)

        user_delta = None
        edited_payload = None
        if proposal_status == STATUS_EDITED:
            edited_payload = _build_payload(msg, msg.final_response)
            user_delta = [
                {"op": "replace", "path": "/body", "value": msg.final_response},
            ]

        outcome_entity_id = None
        outcome_entity_type = None
        if proposal_status in (STATUS_ACCEPTED, STATUS_EDITED):
            outcome_entity_id = await _find_outbound_after(db, msg.thread_id, resolved_at)
            outcome_entity_type = ENTITY_TYPE

        # Don't pass JSONB columns as kwarg when None — asyncpg stores Python
        # None as JSON scalar `null` instead of SQL NULL, which divergs from
        # the runtime path (ProposalService.stage leaves user_delta unset).
        proposal_kwargs: dict = dict(
            id=str(uuid.uuid4()),
            organization_id=msg.organization_id,
            agent_type=AGENT_TYPE,
            entity_type=ENTITY_TYPE,
            source_type=SOURCE_TYPE,
            source_id=msg.id,
            proposed_payload=proposed_payload,
            status=proposal_status,
            rejected_permanently=False,
            resolution_note="ported_from_draft_response",
            created_at=msg.received_at or resolved_at,
        )
        if outcome_entity_type:
            proposal_kwargs["outcome_entity_type"] = outcome_entity_type
        if outcome_entity_id:
            proposal_kwargs["outcome_entity_id"] = outcome_entity_id
        if user_delta is not None:
            proposal_kwargs["user_delta"] = user_delta
        if proposal_status != STATUS_STAGED:
            proposal_kwargs["resolved_at"] = resolved_at
        proposal = AgentProposal(**proposal_kwargs)
        counts["by_proposal_status"][proposal_status] = counts["by_proposal_status"].get(proposal_status, 0) + 1
        counts["created_proposal"] += 1

        correction = None
        if correction_type:
            original_payload = proposed_payload
            corrected_payload = edited_payload  # None on acceptance/rejection
            correction = AgentCorrection(
                id=str(uuid.uuid4()),
                organization_id=msg.organization_id,
                agent_type=AGENT_TYPE,
                correction_type=correction_type,
                category=msg.category,
                customer_id=msg.matched_customer_id,
                input_context=(
                    f"[backfill] subject={msg.subject!r} "
                    f"from={msg.from_email!r}"
                ),
                original_output=json.dumps(original_payload),
                corrected_output=json.dumps(corrected_payload) if corrected_payload else None,
                source_id=proposal.id,
                source_type="agent_proposal",
                applied_count=0,
                created_at=resolved_at,
            )
            counts["by_correction_type"][correction_type] = counts["by_correction_type"].get(correction_type, 0) + 1
            counts["created_correction"] += 1

        if len(samples) < SAMPLE_CAP:
            samples.append({
                "msg_id": msg.id,
                "msg_status": msg.status,
                "draft_len": len(msg.draft_response or ""),
                "final_len": len(msg.final_response or "") if msg.final_response else 0,
                "derived_status": proposal_status,
                "derived_correction": correction_type,
                "outcome_entity_id": outcome_entity_id,
            })

        if not dry_run:
            db.add(proposal)
            if correction is not None:
                db.add(correction)

    if not dry_run:
        await db.commit()

    # Parity assertion — over the same scope we queried.
    base = select(func.count(AgentMessage.id)).where(AgentMessage.draft_response.isnot(None))
    if org_id:
        base = base.where(AgentMessage.organization_id == org_id)
    expected = (await db.execute(base)).scalar() or 0

    ported_q = select(func.count(AgentProposal.id)).where(
        AgentProposal.agent_type == AGENT_TYPE,
        AgentProposal.source_type == SOURCE_TYPE,
    )
    if org_id:
        ported_q = ported_q.where(AgentProposal.organization_id == org_id)
    actual = (await db.execute(ported_q)).scalar() or 0

    counts["parity_expected"] = expected
    counts["parity_actual"] = actual if not dry_run else expected  # dry run: no rows written
    counts["parity_ok"] = (actual == expected) if not dry_run else True
    counts["samples"] = samples
    return counts


async def main(org_id: Optional[str], dry_run: bool) -> None:
    engine = get_engine()
    Session = get_session_maker()
    async with Session() as db:
        result = await port(db, org_id=org_id, dry_run=dry_run)

    print("=" * 70)
    print(f"Port draft_response → agent_proposals ({'DRY RUN' if dry_run else 'LIVE'})")
    print("=" * 70)
    print(f"Total draft_response rows:      {result['total']}")
    print(f"Skipped (already ported):       {result['skipped_already_ported']}")
    print(f"Proposals {'would be ' if dry_run else ''}created:    {result['created_proposal']}")
    print(f"Corrections {'would be ' if dry_run else ''}created:  {result['created_correction']}")
    print()
    print("By proposal status:")
    for k in sorted(result["by_proposal_status"]):
        print(f"  {k:<12} {result['by_proposal_status'][k]}")
    print()
    print("By correction type:")
    for k in sorted(result["by_correction_type"]):
        print(f"  {k:<12} {result['by_correction_type'][k]}")
    print()
    print(f"Parity: expected={result['parity_expected']}  actual={result['parity_actual']}  ok={result['parity_ok']}")
    print()
    if result["samples"]:
        print("Samples (first 5):")
        for s in result["samples"]:
            print(f"  {s['msg_id'][:8]}.. msg_status={s['msg_status']:<10} "
                  f"drafts={s['draft_len']:>4} final={s['final_len']:>4}  "
                  f"→ proposal.{s['derived_status']}  corr={s['derived_correction']}  "
                  f"outbound={s['outcome_entity_id'][:8] + '..' if s['outcome_entity_id'] else 'None'}")

    await engine.dispose()
    if not dry_run and not result["parity_ok"]:
        sys.exit(1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="Compute but don't write.")
    ap.add_argument("--org", dest="org_id", help="Scope to one organization_id.")
    args = ap.parse_args()
    asyncio.run(main(org_id=args.org_id, dry_run=args.dry_run))
