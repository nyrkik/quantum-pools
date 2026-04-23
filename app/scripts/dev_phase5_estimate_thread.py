"""Dev fixture — seed a realistic thread + case so the Phase 5 estimate
flow can be exercised end-to-end without touching real customer data.

Creates a `__DEV__`-tagged customer, thread with 3 messages of actual
service-request conversation, and a linked case. The user then clicks
"Draft Estimate" on the thread → the AI generates line items → the
staged proposal surfaces in:
  - the inbox row hover panel,
  - the inbox summary card,
  - the case detail page's "Pending AI Drafts" section.

Accepting the proposal should materialize an Invoice + job link (via
the existing estimate creator's thread-aware branch). Edit-and-accept
records an `agent_corrections` row.

Typical dogfood loop:

    ./venv/bin/python app/scripts/dev_phase5_estimate_thread.py seed
    # → prints thread + case URLs. Open thread, click Draft Estimate,
    #   navigate to case to accept.

    ./venv/bin/python app/scripts/dev_phase5_estimate_thread.py status
    # → lists __DEV__ rows + any staged/accepted estimates for audit.

    ./venv/bin/python app/scripts/dev_phase5_estimate_thread.py cleanup
    # → hard-deletes every __DEV__-tagged row plus any proposals,
    #   invoices, and jobs created from them during testing.

Scope: Sapphire by default. Mirrors `dev_phase4_proposal.py` but with
no pre-staged proposal — the point is to exercise the drafter end-to-end.

Future Phase 5 expansions (as we migrate more agents) should add modes
to this same script so we have ONE fixture surface for Phase 5 testing:
  - `--topic email_reply`   → seeds inbound-message scenario for
                                email_drafter migration.
  - `--topic match_low`     → seeds an unmatched inbound that should
                                trigger a low-confidence customer_match
                                proposal.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

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
from src.models.invoice import Invoice  # noqa: E402
from src.models.job_invoice import JobInvoice  # noqa: E402
from src.models.organization import Organization  # noqa: E402
from src.models.service_case import ServiceCase  # noqa: E402


DEV_PREFIX = "__DEV__"
DEFAULT_ORG_NAME = "Sapphire Pool Service"
DEV_EMAIL = "__dev__@phase5-estimate.local"


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
            Customer.email == DEV_EMAIL,
        )
    )).scalar_one_or_none()
    if existing:
        return existing

    c = Customer(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        first_name=DEV_PREFIX,
        last_name="Phase5 Customer",
        email=DEV_EMAIL,
        phone="555-0200",
        billing_address="2 Dev Lane",
        billing_city="Sacramento",
        billing_state="CA",
        billing_zip="95814",
        monthly_rate=0.0,
        payment_terms_days=30,
        balance=0.0,
        difficulty_rating=1,
        notes=f"{DEV_PREFIX} auto-created by dev_phase5_estimate_thread.py — safe to delete.",
    )
    db.add(c)
    await db.flush()
    return c


def _format_thread_url(host: str) -> str:
    return f"{host}/inbox"


def _format_case_url(host: str, case_id: str) -> str:
    return f"{host}/cases/{case_id}"


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

        # Case first — thread binds to it.
        case = ServiceCase(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            case_number=f"{DEV_PREFIX}-SC-{run_tag}",
            title=f"{DEV_PREFIX} Pump replacement quote ({run_tag})",
            status="new",
            priority="normal",
            customer_id=customer.id,
            source="test",
        )
        db.add(case)
        await db.flush()

        # Thread — 3 messages of realistic back-and-forth so the Claude
        # estimator has enough context to produce useful line items.
        thread = AgentThread(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            thread_key=f"{DEV_PREFIX}|phase5|{uuid.uuid4().hex[:8]}",
            contact_email=DEV_EMAIL,
            subject=f"{DEV_PREFIX} Phase5 — Pump making loud noises, needs replacement ({run_tag})",
            matched_customer_id=customer.id,
            customer_name=f"{customer.first_name} {customer.last_name}",
            property_address=f"{customer.billing_address}, {customer.billing_city}",
            case_id=case.id,
            status="pending",
            category="service_request",
            urgency="medium",
            message_count=3,
            last_message_at=now,
            last_direction="inbound",
            last_snippet=f"{DEV_PREFIX} test — pump replacement quote requested.",
            has_pending=True,
        )
        db.add(thread)
        await db.flush()

        # Three messages: customer asks → we ask for details → customer
        # gives enough info for a quote.
        msgs = [
            AgentMessage(
                id=str(uuid.uuid4()),
                organization_id=org.id,
                direction="inbound",
                from_email=DEV_EMAIL,
                to_email="support@sapphire-pools.com",
                subject=thread.subject,
                body=(
                    f"{DEV_PREFIX} Synthetic test message.\n\n"
                    "Hi — the pool pump has been making a loud grinding noise for the last few days "
                    "and now it's barely circulating water. I think the motor is going. "
                    "Can you come out and give me a quote for replacement? "
                    "It's a 1.5HP variable-speed pump, probably 8 years old."
                ),
                category="service_request",
                urgency="medium",
                status="resolved",
                matched_customer_id=customer.id,
                customer_name=thread.customer_name,
                property_address=thread.property_address,
                thread_id=thread.id,
                received_at=now - timedelta(hours=3),
            ),
            AgentMessage(
                id=str(uuid.uuid4()),
                organization_id=org.id,
                direction="outbound",
                from_email="support@sapphire-pools.com",
                to_email=DEV_EMAIL,
                subject=f"Re: {thread.subject}",
                body=(
                    f"{DEV_PREFIX} Synthetic reply.\n\n"
                    "Thanks for reaching out. To put together an accurate quote, can you confirm: "
                    "1) the current pump make/model if you know it, 2) whether the plumbing is 2\" or 1.5\", "
                    "and 3) whether you want single-speed or variable-speed on the replacement?"
                ),
                category="service_request",
                status="sent",
                matched_customer_id=customer.id,
                customer_name=thread.customer_name,
                thread_id=thread.id,
                received_at=now - timedelta(hours=2),
                sent_at=now - timedelta(hours=2),
            ),
            AgentMessage(
                id=str(uuid.uuid4()),
                organization_id=org.id,
                direction="inbound",
                from_email=DEV_EMAIL,
                to_email="support@sapphire-pools.com",
                subject=f"Re: {thread.subject}",
                body=(
                    f"{DEV_PREFIX} Synthetic reply back.\n\n"
                    "It's a Pentair IntelliFlo VSF, 2\" plumbing, and I'd like another variable-speed "
                    "since it's saved us a ton on power bills. The wiring's already set up for it. "
                    "I figure you'll need to drain down, swap the pump, re-plumb the unions, and "
                    "re-prime the system. Let me know what it'll run. Thanks."
                ),
                category="service_request",
                urgency="medium",
                status="pending",
                matched_customer_id=customer.id,
                customer_name=thread.customer_name,
                property_address=thread.property_address,
                thread_id=thread.id,
                received_at=now,
            ),
        ]
        for m in msgs:
            db.add(m)
        await db.flush()

        await db.commit()

    print("=" * 60)
    print(f"Seeded __DEV__ Phase 5 estimate thread for org '{org_name}'")
    print("=" * 60)
    print(f"  Customer:    {customer.first_name} {customer.last_name}  ({customer.id})")
    print(f"  Case:        {case.case_number}  ({case.id})")
    print(f"  Thread:      {thread.subject}")
    print(f"  Thread id:   {thread.id}")
    print(f"  Messages:    {len(msgs)} (2 inbound, 1 outbound)")
    print()
    print(f"  Case URL:    {_format_case_url(host, case.id)}")
    print(f"  Inbox URL:   {_format_thread_url(host)}")
    print()
    print("  To exercise the Phase 5 estimate flow:")
    print(f"  1. Open /inbox, find '{DEV_PREFIX} Phase5 — Pump making loud noises...'")
    print("  2. Click the thread → thread detail sheet opens.")
    print("  3. Click 'Draft Estimate' ($ icon).")
    print("     → Backend stages an `estimate` proposal. Sheet closes.")
    print(f"  4. Navigate to the case: {_format_case_url(host, case.id)}")
    print("     → 'Pending AI Drafts' section at top shows the ProposalCard.")
    print("  5. Click Accept → Invoice + job link materialize atomically.")
    print("     Toast offers 'View invoice →' to jump to the invoice page.")
    print()
    print("  To exercise the learning signal:")
    print("  - Re-run `seed` for a fresh thread.")
    print("  - Draft estimate → click the edit (pencil) affordance on the card.")
    print("  - Tweak a line-item price → Save / Edit & Accept.")
    print("  - Check DB: `SELECT * FROM agent_corrections WHERE agent_type='estimate_generator'`")
    print()
    print("  Re-run `seed` for another independent test case.")
    print("  Run `cleanup` to nuke all __DEV__ rows from this script.")

    await engine.dispose()


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


async def cmd_cleanup(org_name: str) -> None:
    engine = get_engine()
    Session = get_session_maker()
    async with Session() as db:
        org = await _find_org(db, org_name)

        # Dev customer by email (stable across runs).
        dev_customer_ids = [
            r[0] for r in (await db.execute(
                select(Customer.id).where(
                    Customer.organization_id == org.id,
                    Customer.email == DEV_EMAIL,
                )
            )).all()
        ]

        # Dev threads — bound to dev customer OR carrying the dev prefix in the
        # subject / contact_email. Covers both seed runs and any post-seed
        # edits that retained the tag.
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

        # Dev cases — bound to dev customer OR carrying the dev prefix in the
        # case_number or title.
        dev_case_ids = [
            r[0] for r in (await db.execute(
                select(ServiceCase.id).where(
                    ServiceCase.organization_id == org.id,
                    (ServiceCase.customer_id.in_(dev_customer_ids)
                     if dev_customer_ids else False)
                    | ServiceCase.case_number.like(f"{DEV_PREFIX}%")
                    | ServiceCase.title.like(f"{DEV_PREFIX}%"),
                )
            )).all()
        ]

        # Proposals sourced from dev threads (covers all three Phase 5 agents).
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

        # Invoices created from accepting dev proposals (via case_id or customer_id).
        dev_invoice_ids = [
            r[0] for r in (await db.execute(
                select(Invoice.id).where(
                    Invoice.organization_id == org.id,
                    (Invoice.case_id.in_(dev_case_ids)
                     if dev_case_ids else False)
                    | (Invoice.customer_id.in_(dev_customer_ids)
                       if dev_customer_ids else False),
                )
            )).all()
        ]

        # AgentActions (jobs) tied to dev threads, cases, or customers.
        dev_action_ids = [
            r[0] for r in (await db.execute(
                select(AgentAction.id).where(
                    AgentAction.organization_id == org.id,
                    (AgentAction.customer_id.in_(dev_customer_ids)
                     if dev_customer_ids else False)
                    | (AgentAction.thread_id.in_(dev_thread_ids)
                       if dev_thread_ids else False)
                    | (AgentAction.case_id.in_(dev_case_ids)
                       if dev_case_ids else False),
                )
            )).all()
        ]

        counts = {
            "customers": len(dev_customer_ids),
            "cases": len(dev_case_ids),
            "threads": len(dev_thread_ids),
            "proposals": len(dev_proposal_ids),
            "invoices": len(dev_invoice_ids),
            "agent_actions": len(dev_action_ids),
        }

        if not any(counts.values()):
            print(f"No {DEV_PREFIX} Phase 5 rows found in '{org_name}'. Nothing to clean.")
            await engine.dispose()
            return

        print(f"About to delete from '{org_name}':")
        for label, n in counts.items():
            print(f"  {label}: {n}")

        # Delete children before parents. Use raw DELETE for speed and to
        # bypass ORM cascades that might miss rows.
        if dev_action_ids:
            await db.execute(
                text("DELETE FROM agent_action_tasks WHERE action_id = ANY(:ids)"),
                {"ids": dev_action_ids},
            )
            await db.execute(
                text("DELETE FROM job_invoices WHERE action_id = ANY(:ids)"),
                {"ids": dev_action_ids},
            )
        if dev_invoice_ids:
            await db.execute(
                text("DELETE FROM job_invoices WHERE invoice_id = ANY(:ids)"),
                {"ids": dev_invoice_ids},
            )
            await db.execute(
                text("DELETE FROM invoice_line_items WHERE invoice_id = ANY(:ids)"),
                {"ids": dev_invoice_ids},
            )
            await db.execute(
                delete(Invoice).where(Invoice.id.in_(dev_invoice_ids))
            )
        if dev_action_ids:
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
        if dev_case_ids:
            await db.execute(
                delete(ServiceCase).where(ServiceCase.id.in_(dev_case_ids))
            )
        if dev_customer_ids:
            await db.execute(
                delete(Customer).where(Customer.id.in_(dev_customer_ids))
            )

        await db.commit()

    print(f"Cleaned up {sum(counts.values())} {DEV_PREFIX} Phase 5 rows.")
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
            select(Customer.id, Customer.first_name, Customer.last_name, Customer.email).where(
                Customer.organization_id == org.id,
                Customer.email == DEV_EMAIL,
            )
        )).all()
        customer_ids = [c[0] for c in customers]

        threads = (await db.execute(
            select(AgentThread.id, AgentThread.subject, AgentThread.status).where(
                AgentThread.organization_id == org.id,
                AgentThread.subject.like(f"{DEV_PREFIX}%"),
            )
        )).all()

        cases = (await db.execute(
            select(ServiceCase.id, ServiceCase.case_number, ServiceCase.title, ServiceCase.status).where(
                ServiceCase.organization_id == org.id,
                ServiceCase.case_number.like(f"{DEV_PREFIX}%"),
            )
        )).all()

        proposals = (await db.execute(
            select(AgentProposal.id, AgentProposal.agent_type, AgentProposal.entity_type,
                   AgentProposal.status, AgentProposal.created_at)
            .where(
                AgentProposal.organization_id == org.id,
                AgentProposal.source_id.in_([t[0] for t in threads]) if threads else False,
            )
        )).all()

        invoices = (await db.execute(
            select(Invoice.id, Invoice.invoice_number, Invoice.subject,
                   Invoice.status, Invoice.total).where(
                Invoice.organization_id == org.id,
                Invoice.customer_id.in_(customer_ids) if customer_ids else False,
            )
        )).all()

        print(f"Phase 5 dev fixtures in '{org_name}':")
        print(f"  Customers ({len(customers)}):")
        for cid, fn, ln, em in customers:
            print(f"    {cid}  {fn} {ln}  <{em}>")
        print(f"  Cases ({len(cases)}):")
        for cid, num, title, st in cases:
            print(f"    {cid}  {num}  [{st}]  {title}")
        print(f"  Threads ({len(threads)}):")
        for tid, subj, st in threads:
            print(f"    {tid}  [{st}]  {subj}")
        print(f"  Proposals ({len(proposals)}):")
        for pid, agent, et, st, created in proposals:
            print(f"    {pid}  {agent}/{et}  [{st}]  {created}")
        print(f"  Invoices ({len(invoices)}):")
        for iid, num, subj, st, total in invoices:
            print(f"    {iid}  {num}  [{st}]  ${float(total or 0):.2f}  {subj}")

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
