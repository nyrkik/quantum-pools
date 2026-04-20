"""Dev fixture — stage a throwaway job proposal for Phase 4 testing.

Creates a sentinel customer + thread + message + `ai_summary_payload`
(that references the new proposal) + the staged proposal itself, all
tagged with the `__DEV__` prefix so they're unmistakably fake. The
proposal surfaces in the inbox like any other, so the post-accept
`next_step` UI (Phase 4) can be exercised end-to-end without touching
real customer data.

Typical dogfood loop:

    ./venv/bin/python app/scripts/dev_phase4_proposal.py seed
    # → prints a thread URL; open it, accept the proposal, walk the
    #   inline step, verify handler.applied lands in platform_events.

    ./venv/bin/python app/scripts/dev_phase4_proposal.py status
    # → lists all __DEV__-tagged rows so you can see what's outstanding.

    ./venv/bin/python app/scripts/dev_phase4_proposal.py cleanup
    # → hard-deletes every __DEV__-tagged row (customer, thread,
    #   message, proposal, any AgentAction created by accept). Safe
    #   to re-run; idempotent.

Scope: Sapphire by default (the dogfood org). `--org-name` overrides.
Re-run `seed` as many times as you want — each run creates a fresh
thread + proposal so you can try different handlers.

`platform_events` rows emitted during the test (job.created,
proposal.accepted, handler.applied, etc.) are NOT deleted — they're
immutable audit history, and leaving them lets you verify the event
stream worked correctly. Their entity_refs will point at deleted
rows after cleanup; that's expected and harmless.

Intentionally lives in dev tooling, not the test suite — this exists
to seed the UI, not to assert behavior.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
)

from sqlalchemy import delete, select, text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from src.core.database import get_engine, get_session_maker  # noqa: E402
from src.models.agent_action import AgentAction  # noqa: E402
from src.models.agent_message import AgentMessage  # noqa: E402
from src.models.agent_proposal import AgentProposal  # noqa: E402
from src.models.agent_thread import AgentThread  # noqa: E402
from src.models.customer import Customer  # noqa: E402
from src.models.organization import Organization  # noqa: E402


DEV_PREFIX = "__DEV__"
DEFAULT_ORG_NAME = "Sapphire Pool Service"
DEV_EMAIL = "__dev__@phase4-test.local"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _find_org(db: AsyncSession, org_name: str) -> Organization:
    row = (await db.execute(
        select(Organization).where(Organization.name == org_name)
    )).scalar_one_or_none()
    if row is None:
        raise SystemExit(f"Org '{org_name}' not found")
    return row


async def _get_or_create_dev_customer(
    db: AsyncSession, org_id: str,
) -> Customer:
    existing = (await db.execute(
        select(Customer).where(
            Customer.organization_id == org_id,
            Customer.first_name == DEV_PREFIX,
        )
    )).scalar_one_or_none()
    if existing:
        return existing

    c = Customer(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        first_name=DEV_PREFIX,
        last_name="Phase4 Customer",
        email=DEV_EMAIL,
        phone="555-0100",
        billing_address="1 Dev Lane",
        billing_city="Sacramento",
        billing_state="CA",
        billing_zip="95814",
        monthly_rate=0.0,
        payment_terms_days=30,
        balance=0.0,
        difficulty_rating=1,
        notes=f"{DEV_PREFIX} auto-created by dev_phase4_proposal.py — safe to delete.",
    )
    db.add(c)
    await db.flush()
    return c


def _format_inbox_url(host: str) -> str:
    return f"{host}/inbox"


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------


async def cmd_seed(org_name: str, host: str) -> None:
    engine = get_engine()
    Session = get_session_maker()
    async with Session() as db:
        org = await _find_org(db, org_name)
        customer = await _get_or_create_dev_customer(db, org.id)

        now = datetime.now(timezone.utc)
        run_tag = now.strftime("%H%M%S")

        # Thread (fresh each time — so the user can test multiple
        # accepts without the prior one's state getting in the way).
        thread = AgentThread(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            thread_key=f"{DEV_PREFIX}|phase4|{uuid.uuid4().hex[:8]}",
            contact_email=DEV_EMAIL,
            subject=f"{DEV_PREFIX} Phase4 Test — Pump won't prime ({run_tag})",
            matched_customer_id=customer.id,
            customer_name=f"{customer.first_name} {customer.last_name}",
            property_address=f"{customer.billing_address}, {customer.billing_city}",
            status="pending",
            category="repair",
            urgency="medium",
            message_count=1,
            last_message_at=now,
            last_direction="inbound",
            last_snippet=f"{DEV_PREFIX} test — pump won't prime, need a repair visit.",
            has_pending=True,
        )
        db.add(thread)
        await db.flush()

        msg = AgentMessage(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            direction="inbound",
            from_email=DEV_EMAIL,
            to_email="support@sapphire-pools.com",
            subject=thread.subject,
            body=(
                f"{DEV_PREFIX} Synthetic test message.\n\n"
                "Hi team, the pump at our property won't prime since Saturday. "
                "Can you send someone out to take a look? Thanks."
            ),
            category="repair",
            urgency="medium",
            status="pending",
            matched_customer_id=customer.id,
            customer_name=thread.customer_name,
            property_address=thread.property_address,
            thread_id=thread.id,
            received_at=now,
        )
        db.add(msg)
        await db.flush()

        proposal = AgentProposal(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            agent_type="inbox_summarizer",
            entity_type="job",
            source_type="agent_thread",
            source_id=thread.id,
            proposed_payload={
                "action_type": "repair",
                "description": "Diagnose pump prime failure at __DEV__ site",
                "customer_id": customer.id,
                "customer_name": thread.customer_name,
                "thread_id": thread.id,
                "property_address": thread.property_address,
                "job_path": "internal",
                "notes": f"{DEV_PREFIX} test proposal — safe to accept/reject.",
            },
            confidence=0.9,
            status="staged",
        )
        db.add(proposal)
        await db.flush()

        # ai_summary_payload so the inbox row's right-side card
        # shows the staged proposal as a ProposalCardMini.
        thread.ai_summary_payload = {
            "version": 1,
            "ask": "Customer wants a repair visit.",
            "state": "awaiting triage",
            "open_items": [
                "Pump won't prime — diagnose cause",
            ],
            "red_flags": [],
            "linked_refs": [
                {"type": "customer", "id": customer.id,
                 "label": thread.customer_name},
            ],
            "confidence": 0.9,
            "proposal_ids": [proposal.id],
        }
        thread.ai_summary_generated_at = now
        thread.ai_summary_version = 1

        await db.commit()

    print("=" * 60)
    print(f"Seeded __DEV__ Phase 4 proposal for org '{org_name}'")
    print("=" * 60)
    print(f"  Customer:  {customer.first_name} {customer.last_name}  ({customer.id})")
    print(f"  Thread:    {thread.subject}")
    print(f"  Thread id: {thread.id}")
    print(f"  Proposal:  {proposal.id}  (entity_type=job, status=staged)")
    print()
    print(f"  Open inbox: {_format_inbox_url(host)}")
    print()
    print("  The ProposalCardMini lives in the Phase 3 hover panel, NOT the")
    print("  thread detail page. To test:")
    print("  1. Open /inbox (the list, not the thread).")
    print(f"  2. Find the row with subject '{DEV_PREFIX} Phase4 Test — Pump won't prime'.")
    print("  3. Hover the row (desktop) or tap the info icon (mobile)")
    print("     → hover panel shows the mini card with Accept/Reject.")
    print("  4. Click Accept → the Phase 4 step renders inline, driven by")
    print("     your /settings/workflows handler choice.")
    print("  5. Save or Skip → check /admin/platform/events for")
    print("     `handler.applied` / `handler.abandoned`.")
    print()
    print("  Re-run `seed` to create another fresh test thread+proposal.")
    print("  Run `cleanup` to nuke all __DEV__ rows when done.")

    await engine.dispose()


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


async def cmd_cleanup(org_name: str) -> None:
    engine = get_engine()
    Session = get_session_maker()
    async with Session() as db:
        org = await _find_org(db, org_name)

        # Find the dev customer(s) — should be one, but be defensive.
        dev_customer_ids = [
            r[0] for r in (await db.execute(
                select(Customer.id).where(
                    Customer.organization_id == org.id,
                    Customer.first_name == DEV_PREFIX,
                )
            )).all()
        ]

        # Threads matching the dev email OR matched to a dev customer.
        dev_thread_ids = [
            r[0] for r in (await db.execute(
                select(AgentThread.id).where(
                    AgentThread.organization_id == org.id,
                    (AgentThread.matched_customer_id.in_(dev_customer_ids)
                     if dev_customer_ids else False)
                    | AgentThread.contact_email.like(DEV_EMAIL)
                    | AgentThread.subject.like(f"{DEV_PREFIX}%"),
                )
            )).all()
        ]

        # Proposals sourced from dev threads. Captures proposals whose
        # outcome_entity_id points at a dev AgentAction too (rare, but
        # catches the case where the source thread got deleted first).
        dev_proposal_ids = [
            r[0] for r in (await db.execute(
                select(AgentProposal.id).where(
                    AgentProposal.organization_id == org.id,
                    (AgentProposal.source_id.in_(dev_thread_ids)
                     if dev_thread_ids else False)
                    | (AgentProposal.proposed_payload["customer_id"].astext.in_(
                        dev_customer_ids,
                    ) if dev_customer_ids else False),
                )
            )).all()
        ]

        # AgentActions created by accepting a dev proposal (linked via
        # outcome_entity_id on the proposal) OR directly tagged via
        # customer_id / thread_id.
        dev_action_ids = [
            r[0] for r in (await db.execute(
                select(AgentAction.id).where(
                    AgentAction.organization_id == org.id,
                    (AgentAction.customer_id.in_(dev_customer_ids)
                     if dev_customer_ids else False)
                    | (AgentAction.thread_id.in_(dev_thread_ids)
                       if dev_thread_ids else False),
                )
            )).all()
        ]

        counts = {
            "customers": len(dev_customer_ids),
            "threads": len(dev_thread_ids),
            "proposals": len(dev_proposal_ids),
            "agent_actions": len(dev_action_ids),
        }

        if not any(counts.values()):
            print(f"No {DEV_PREFIX} rows found in '{org_name}'. Nothing to clean.")
            await engine.dispose()
            return

        print(f"About to delete from '{org_name}':")
        for label, n in counts.items():
            print(f"  {label}: {n}")

        # Delete in dependency order (children before parents). We hit
        # a few join tables (service_cases carry case_id FK on jobs;
        # agent_action_tasks cascade via ORM; messages cascade via
        # thread FK). Use raw DELETE for speed + to bypass any model-
        # level cascades that might miss rows.
        if dev_action_ids:
            await db.execute(
                text("DELETE FROM agent_action_tasks WHERE action_id = ANY(:ids)"),
                {"ids": dev_action_ids},
            )
            await db.execute(
                delete(AgentAction).where(AgentAction.id.in_(dev_action_ids))
            )
        if dev_proposal_ids:
            await db.execute(
                delete(AgentProposal).where(AgentProposal.id.in_(dev_proposal_ids))
            )
        if dev_thread_ids:
            await db.execute(
                delete(AgentMessage).where(AgentMessage.thread_id.in_(dev_thread_ids))
            )
            await db.execute(
                delete(AgentThread).where(AgentThread.id.in_(dev_thread_ids))
            )
        if dev_customer_ids:
            await db.execute(
                delete(Customer).where(Customer.id.in_(dev_customer_ids))
            )

        await db.commit()

    print(f"Cleaned up {sum(counts.values())} {DEV_PREFIX} rows.")
    print(
        "Note: related platform_events rows were NOT deleted — they are\n"
        "      immutable audit history. Their entity_refs now point at\n"
        "      deleted rows; that's expected.",
    )

    await engine.dispose()


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


async def cmd_status(org_name: str) -> None:
    engine = get_engine()
    Session = get_session_maker()
    async with Session() as db:
        org = await _find_org(db, org_name)

        customers = (await db.execute(
            select(Customer.id, Customer.first_name, Customer.last_name).where(
                Customer.organization_id == org.id,
                Customer.first_name == DEV_PREFIX,
            )
        )).all()

        threads = (await db.execute(
            select(AgentThread.id, AgentThread.subject, AgentThread.status).where(
                AgentThread.organization_id == org.id,
                AgentThread.subject.like(f"{DEV_PREFIX}%"),
            )
        )).all()

        proposals = (await db.execute(
            select(AgentProposal.id, AgentProposal.status,
                   AgentProposal.entity_type, AgentProposal.created_at)
            .where(
                AgentProposal.organization_id == org.id,
                AgentProposal.source_id.in_([t[0] for t in threads]) if threads else False,
            )
        )).all()

        print(f"Dev fixtures in '{org_name}':")
        print(f"  Customers ({len(customers)}):")
        for cid, fn, ln in customers:
            print(f"    {cid}  {fn} {ln}")
        print(f"  Threads ({len(threads)}):")
        for tid, subj, st in threads:
            print(f"    {tid}  [{st}]  {subj}")
        print(f"  Proposals ({len(proposals)}):")
        for pid, st, et, created in proposals:
            print(f"    {pid}  {et}  [{st}]  {created}")

    await engine.dispose()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "cmd",
        choices=("seed", "cleanup", "status"),
        help="Which action to take.",
    )
    p.add_argument(
        "--org-name", default=DEFAULT_ORG_NAME,
        help=f"Organization name (default: {DEFAULT_ORG_NAME!r}).",
    )
    p.add_argument(
        "--host", default="https://quantumpoolspro.com",
        help="Frontend host for the 'open in UI' link.",
    )
    args = p.parse_args()

    if args.cmd == "seed":
        asyncio.run(cmd_seed(args.org_name, args.host))
    elif args.cmd == "cleanup":
        asyncio.run(cmd_cleanup(args.org_name))
    elif args.cmd == "status":
        asyncio.run(cmd_status(args.org_name))


if __name__ == "__main__":
    main()
