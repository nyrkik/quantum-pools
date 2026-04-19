"""Phase 1 Step 9 — backfill historical platform_events rows from
existing QP tables.

With the PSS invoice+customer import done (see import_pss_invoices.py),
QP has ~20 months of real historical data. This script replays that
history into the event stream so Sonar + workflow-observer see a full
funnel instead of a month-old cold start.

What gets emitted, in what order (pass ordering matters so entity-create
events land before the activation pass and before "X per Y" queries run):

   1. customer.created       — one per customer
   2. customer.cancelled     — one per inactive customer (timestamp_is_approximate)
   3. property.created       — one per property
   4. water_feature.created  — one per water feature
   5. case.created / closed  — per service case (closed if already terminal)
   6. job.created            — per agent_action
   7. visit.completed        — per completed visit with actual_departure
   8. invoice.created        — per invoice
   9. invoice.sent           — per invoice with sent_at (invoices only)
  10. invoice.paid           — per invoice with paid_date + status=paid
  11. invoice.days_to_paid   — per paid invoice (derived analytics event)
  12. invoice.write_off      — per invoice with status=write_off
  13. invoice.voided         — per invoice with status=void
  14. activation.*           — 5 milestones, first-per-org-ever, clamped
                               to >= account_created so pre-QP data doesn't
                               produce negative funnel gaps

Idempotency: every event carries a deterministic client_emit_id like
"backfill:invoice.sent:<invoice-id>" so re-runs silently skip rows
that already exist.

Transaction discipline: emit writes share the session, commit at the
end of each entity type. Fail-soft emission is preserved (via the
shared PlatformEventService contract).

Usage:
  ./venv/bin/python app/scripts/backfill_platform_events.py            # dry-run
  ./venv/bin/python app/scripts/backfill_platform_events.py --commit   # actually write
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.customer import Customer  # noqa: E402
from src.models.invoice import Invoice  # noqa: E402
from src.models.organization import Organization  # noqa: E402
from src.models.payment import Payment  # noqa: E402
from src.services.events.activation_tracker import FUNNEL_ORDER  # noqa: E402
from src.services.events.platform_event_service import Actor, PlatformEventService  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

@dataclass
class BackfillReport:
    by_event_type: Counter = field(default_factory=Counter)
    already_exists: Counter = field(default_factory=Counter)
    activation_firsts: dict[str, tuple[datetime, str]] = field(default_factory=dict)  # event_type → (when, entity_ref)
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_BACKFILL_NAMESPACE = uuid.UUID("00000000-0000-5000-8000-000000000001")


def _emit_id(*parts: str) -> str:
    """Deterministic client_emit_id for backfill dedup.

    client_emit_id is VARCHAR(36) (UUID-sized) so we can't just
    concatenate a descriptive string like "backfill:customer.created:<id>".
    Instead, uuid5 over a fixed namespace + the descriptive string produces
    a deterministic 36-char UUID. Re-runs with the same source state yield
    identical IDs, so dedup still works.

    Descriptive-string → UUID is one-way, but that's fine — the dedup check
    only needs equality, not reverse lookup. If we need to ever see "which
    backfill event type did this row come from?" we also stamp
    payload.source="backfill" in _emit().
    """
    descriptive = "backfill:" + ":".join(parts)
    return str(uuid.uuid5(_BACKFILL_NAMESPACE, descriptive))


async def _already_emitted(db: AsyncSession, org_id: str, client_emit_id: str) -> bool:
    """True if an event with this client_emit_id already exists for this org."""
    result = await db.execute(
        text(
            "SELECT 1 FROM platform_events "
            "WHERE organization_id = :org AND client_emit_id = :cid LIMIT 1"
        ),
        {"org": org_id, "cid": client_emit_id},
    )
    return result.first() is not None


async def _emit(
    db: AsyncSession,
    *,
    event_type: str,
    org_id: str,
    entity_refs: dict,
    payload: dict,
    created_at: datetime,
    client_emit_id: str,
    report: BackfillReport,
    commit: bool,
) -> None:
    """Wraps PlatformEventService.emit with dedup + reporting. All backfill
    events are system actor, level=system_action, source=backfill."""
    if await _already_emitted(db, org_id, client_emit_id):
        report.already_exists[event_type] += 1
        return

    # Stamp payload with a backfill marker so downstream can filter.
    # Use a namespaced key (not `source`) because several event types
    # have `source` as a canonical taxonomy field (case.created,
    # customer.created, etc.) — collapsing them would clobber real data.
    enriched = {**payload, "_backfill": True}

    # Ensure timestamp is tz-aware — Postgres TIMESTAMPTZ requires it.
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    if commit:
        await PlatformEventService.emit(
            db=db,
            event_type=event_type,
            level="system_action",
            actor=Actor(actor_type="system"),
            organization_id=org_id,
            entity_refs=entity_refs,
            payload=enriched,
            client_emit_id=client_emit_id,
            created_at=created_at,
        )
    report.by_event_type[event_type] += 1


# ---------------------------------------------------------------------------
# Passes
# ---------------------------------------------------------------------------


async def backfill_customers(
    db: AsyncSession, org: Organization, report: BackfillReport, commit: bool
) -> None:
    result = await db.execute(
        select(Customer).where(Customer.organization_id == org.id).order_by(Customer.created_at)
    )
    for c in result.scalars():
        await _emit(
            db,
            event_type="customer.created",
            org_id=org.id,
            entity_refs={"customer_id": c.id},
            payload={
                "customer_type": c.customer_type,
                "is_active": c.is_active,
                "source": "pss_import" if c.pss_id else "qp_native",
            },
            created_at=c.created_at,
            client_emit_id=_emit_id("customer.created", c.id),
            report=report,
            commit=commit,
        )
        # Emit customer.cancelled for already-inactive customers so the
        # churn signal is present on day 1. We don't have the true cancel
        # time — PSS imports carry import-time timestamps, QP-native edits
        # carry updated_at which is the last edit, not the cancel edit.
        # Mark the timestamp as approximate so Sonar / charts don't render
        # a spurious churn spike on import day.
        if not c.is_active or c.status == "inactive":
            cancel_time = c.updated_at or c.created_at
            payload: dict = {
                "reason_code": "other",
                "timestamp_is_approximate": True,
            }
            if c.pss_id:
                payload["source_note"] = "pss_imported_as_inactive"
            await _emit(
                db,
                event_type="customer.cancelled",
                org_id=org.id,
                entity_refs={"customer_id": c.id},
                payload=payload,
                created_at=cancel_time,
                client_emit_id=_emit_id("customer.cancelled", c.id),
                report=report,
                commit=commit,
            )


async def backfill_invoices(
    db: AsyncSession, org: Organization, report: BackfillReport, commit: bool
) -> None:
    result = await db.execute(
        select(Invoice).where(Invoice.organization_id == org.id).order_by(Invoice.created_at)
    )
    for inv in result.scalars():
        # invoice.created for every invoice
        await _emit(
            db,
            event_type="invoice.created",
            org_id=org.id,
            entity_refs={"invoice_id": inv.id, "customer_id": inv.customer_id} if inv.customer_id else {"invoice_id": inv.id},
            payload={
                "document_type": inv.document_type,
                "is_backfilled_from_pss": inv.pss_invoice_id is not None,
            },
            created_at=inv.created_at,
            client_emit_id=_emit_id("invoice.created", inv.id),
            report=report,
            commit=commit,
        )

        # invoice.sent if it has a sent_at (or derived from non-draft status)
        if inv.sent_at and inv.document_type == "invoice":
            await _emit(
                db,
                event_type="invoice.sent",
                org_id=org.id,
                entity_refs={"invoice_id": inv.id, "customer_id": inv.customer_id} if inv.customer_id else {"invoice_id": inv.id},
                payload={
                    "document_type": inv.document_type,
                    "recipient_count": 1,
                    "resolver_used": "backfill_pss",
                },
                created_at=inv.sent_at,
                client_emit_id=_emit_id("invoice.sent", inv.id),
                report=report,
                commit=commit,
            )

        # invoice.paid + invoice.days_to_paid if there's a paid_date
        if inv.paid_date and inv.status == "paid":
            paid_dt = datetime.combine(inv.paid_date, datetime.min.time(), tzinfo=timezone.utc)
            await _emit(
                db,
                event_type="invoice.paid",
                org_id=org.id,
                entity_refs={"invoice_id": inv.id, "customer_id": inv.customer_id} if inv.customer_id else {"invoice_id": inv.id},
                payload={"method": "unknown", "auto_pay": False},
                created_at=paid_dt,
                client_emit_id=_emit_id("invoice.paid", inv.id),
                report=report,
                commit=commit,
            )
            # Derived analytics event
            if inv.sent_at:
                days = (inv.paid_date - inv.sent_at.date()).days
                await _emit(
                    db,
                    event_type="invoice.days_to_paid",
                    org_id=org.id,
                    entity_refs={"invoice_id": inv.id},
                    payload={
                        "days_to_paid": max(days, 0),
                        "document_type": inv.document_type,
                        "auto_pay": False,
                    },
                    created_at=paid_dt,
                    client_emit_id=_emit_id("invoice.days_to_paid", inv.id),
                    report=report,
                    commit=commit,
                )

        # Write-off and void — derive from status
        if inv.status == "write_off":
            write_off_time = inv.written_off_at or inv.updated_at or inv.created_at
            await _emit(
                db,
                event_type="invoice.write_off",
                org_id=org.id,
                entity_refs={"invoice_id": inv.id},
                payload={},
                created_at=write_off_time,
                client_emit_id=_emit_id("invoice.write_off", inv.id),
                report=report,
                commit=commit,
            )
        elif inv.status == "void":
            void_time = inv.voided_at or inv.updated_at or inv.created_at
            await _emit(
                db,
                event_type="invoice.voided",
                org_id=org.id,
                entity_refs={"invoice_id": inv.id},
                payload={},
                created_at=void_time,
                client_emit_id=_emit_id("invoice.voided", inv.id),
                report=report,
                commit=commit,
            )


async def backfill_properties(
    db: AsyncSession, org: Organization, report: BackfillReport, commit: bool
) -> None:
    from src.models.property import Property
    result = await db.execute(
        select(Property).where(Property.organization_id == org.id).order_by(Property.created_at)
    )
    for p in result.scalars():
        await _emit(
            db,
            event_type="property.created",
            org_id=org.id,
            entity_refs={"property_id": p.id, "customer_id": p.customer_id} if p.customer_id else {"property_id": p.id},
            payload={},
            created_at=p.created_at,
            client_emit_id=_emit_id("property.created", p.id),
            report=report,
            commit=commit,
        )


async def backfill_water_features(
    db: AsyncSession, org: Organization, report: BackfillReport, commit: bool
) -> None:
    from src.models.water_feature import WaterFeature
    result = await db.execute(
        select(WaterFeature).where(WaterFeature.organization_id == org.id).order_by(WaterFeature.created_at)
    )
    for wf in result.scalars():
        refs = {"water_feature_id": wf.id}
        if wf.property_id:
            refs["property_id"] = wf.property_id
        payload: dict = {}
        if wf.pool_type:
            payload["pool_type"] = wf.pool_type
        if wf.name:
            payload["name"] = wf.name
        await _emit(
            db,
            event_type="water_feature.created",
            org_id=org.id,
            entity_refs=refs,
            payload=payload,
            created_at=wf.created_at,
            client_emit_id=_emit_id("water_feature.created", wf.id),
            report=report,
            commit=commit,
        )


async def backfill_cases(
    db: AsyncSession, org: Organization, report: BackfillReport, commit: bool
) -> None:
    from src.models.service_case import ServiceCase
    result = await db.execute(
        select(ServiceCase).where(ServiceCase.organization_id == org.id).order_by(ServiceCase.created_at)
    )
    for case in result.scalars():
        refs = {"case_id": case.id}
        if case.customer_id:
            refs["customer_id"] = case.customer_id
        await _emit(
            db,
            event_type="case.created",
            org_id=org.id,
            entity_refs=refs,
            payload={
                "source": case.source or "unknown",
                "status_at_create": case.status,
            },
            created_at=case.created_at,
            client_emit_id=_emit_id("case.created", case.id),
            report=report,
            commit=commit,
        )
        # If the case is already closed, emit case.closed at closed_at.
        if case.status == "closed" and case.closed_at:
            await _emit(
                db,
                event_type="case.closed",
                org_id=org.id,
                entity_refs=refs,
                payload={
                    "reason": "backfill_snapshot",
                    "auto_closed": False,
                    "timestamp_is_approximate": False,
                },
                created_at=case.closed_at,
                client_emit_id=_emit_id("case.closed", case.id),
                report=report,
                commit=commit,
            )


async def backfill_jobs(
    db: AsyncSession, org: Organization, report: BackfillReport, commit: bool
) -> None:
    from src.models.agent_action import AgentAction
    result = await db.execute(
        select(AgentAction).where(AgentAction.organization_id == org.id).order_by(AgentAction.created_at)
    )
    for job in result.scalars():
        refs: dict = {"job_id": job.id}
        if job.case_id:
            refs["case_id"] = job.case_id
        if job.thread_id:
            refs["thread_id"] = job.thread_id
        if job.customer_id:
            refs["customer_id"] = job.customer_id
        await _emit(
            db,
            event_type="job.created",
            org_id=org.id,
            entity_refs=refs,
            payload={
                "job_type": job.action_type or "unknown",
                "status_at_create": job.status,
            },
            created_at=job.created_at,
            client_emit_id=_emit_id("job.created", job.id),
            report=report,
            commit=commit,
        )


async def backfill_visits(
    db: AsyncSession, org: Organization, report: BackfillReport, commit: bool
) -> None:
    from src.models.visit import Visit
    result = await db.execute(
        select(Visit).where(
            Visit.organization_id == org.id,
            Visit.status == "completed",
        ).order_by(Visit.actual_departure)
    )
    for v in result.scalars():
        # visit.completed requires a departure timestamp — skip otherwise.
        if not v.actual_departure:
            continue
        refs = {"visit_id": v.id}
        if v.property_id:
            refs["property_id"] = v.property_id
        if v.customer_id:
            refs["customer_id"] = v.customer_id
        payload: dict = {}
        if v.duration_minutes is not None:
            payload["duration_minutes"] = v.duration_minutes
        await _emit(
            db,
            event_type="visit.completed",
            org_id=org.id,
            entity_refs=refs,
            payload=payload,
            created_at=v.actual_departure,
            client_emit_id=_emit_id("visit.completed", v.id),
            report=report,
            commit=commit,
        )


async def backfill_activation(
    db: AsyncSession, org: Organization, report: BackfillReport, commit: bool
) -> None:
    """For each activation milestone, find the earliest qualifying record
    and emit the first-per-org event at that timestamp. Computes
    minutes_since_prior_milestone correctly by walking FUNNEL_ORDER in
    order and tracking the most recent prior emit.
    """
    # Compute the milestones.
    milestones: dict[str, tuple[datetime, dict]] = {}  # event_type → (when, entity_refs)

    # account_created — earliest user/org-user pairing for this org.
    result = await db.execute(
        text("""
            SELECT ou.user_id, ou.created_at
            FROM organization_users ou
            WHERE ou.organization_id = :org
            ORDER BY ou.created_at ASC LIMIT 1
        """),
        {"org": org.id},
    )
    row = result.first()
    if row and row[1]:
        milestones["activation.account_created"] = (
            row[1] if row[1].tzinfo else row[1].replace(tzinfo=timezone.utc),
            {"user_id": row[0]},
        )

    # first_customer_added — earliest Customer
    result = await db.execute(
        select(Customer.id, Customer.created_at)
        .where(Customer.organization_id == org.id)
        .order_by(Customer.created_at)
        .limit(1)
    )
    row = result.first()
    if row:
        milestones["activation.first_customer_added"] = (
            row[1] if row[1].tzinfo else row[1].replace(tzinfo=timezone.utc),
            {"customer_id": row[0]},
        )

    # first_visit_completed — earliest completed Visit
    from src.models.visit import Visit
    result = await db.execute(
        select(Visit.id, Visit.property_id, Visit.actual_departure)
        .where(Visit.organization_id == org.id, Visit.status == "completed")
        .order_by(Visit.actual_departure)
        .limit(1)
    )
    row = result.first()
    if row and row[2]:
        milestones["activation.first_visit_completed"] = (
            row[2] if row[2].tzinfo else row[2].replace(tzinfo=timezone.utc),
            {"visit_id": row[0], "property_id": row[1]},
        )

    # first_invoice_sent — earliest non-draft Invoice with sent_at
    result = await db.execute(
        select(Invoice.id, Invoice.sent_at)
        .where(
            Invoice.organization_id == org.id,
            Invoice.document_type == "invoice",
            Invoice.sent_at.isnot(None),
        )
        .order_by(Invoice.sent_at)
        .limit(1)
    )
    row = result.first()
    if row:
        milestones["activation.first_invoice_sent"] = (
            row[1] if row[1].tzinfo else row[1].replace(tzinfo=timezone.utc),
            {"invoice_id": row[0]},
        )

    # first_payment_received — earliest Payment by payment_date
    result = await db.execute(
        select(Payment.id, Payment.customer_id, Payment.invoice_id, Payment.payment_date)
        .where(Payment.organization_id == org.id)
        .order_by(Payment.payment_date)
        .limit(1)
    )
    row = result.first()
    if row and row[3]:
        when = datetime.combine(row[3], datetime.min.time(), tzinfo=timezone.utc)
        refs = {"customer_id": row[1]}
        if row[2]:
            refs["invoice_id"] = row[2]
        milestones["activation.first_payment_received"] = (when, refs)

    # Clamp every milestone to be >= account_created. PSS-imported data
    # has customers/invoices with 2024 timestamps — those predate the QP
    # org creation (Jan 2026 for Sapphire), which produces analytically
    # garbage funnel gaps ("time to first customer = -17 months").
    # We pull pre-account milestones forward to account_created and stamp
    # `backfill_clamped: true` + `original_when` so Sonar can see that
    # the floor was applied and filter these out of cohort analysis.
    account_floor: Optional[datetime] = None
    if "activation.account_created" in milestones:
        account_floor = milestones["activation.account_created"][0]

    # Emit in canonical funnel order, carrying prior timestamp forward
    # so minutes_since_prior_milestone is computed right.
    prior_when: Optional[datetime] = None
    for event_type in FUNNEL_ORDER:
        if event_type not in milestones:
            continue
        when, refs = milestones[event_type]
        payload: dict = {}
        if account_floor is not None and when < account_floor:
            payload["backfill_clamped"] = True
            payload["original_when"] = when.isoformat()
            when = account_floor
        if prior_when is not None and when >= prior_when:
            delta_min = int((when - prior_when).total_seconds() / 60)
            payload["minutes_since_prior_milestone"] = delta_min
        await _emit(
            db,
            event_type=event_type,
            org_id=org.id,
            entity_refs=refs,
            payload=payload,
            created_at=when,
            client_emit_id=_emit_id(event_type, org.id),
            report=report,
            commit=commit,
        )
        report.activation_firsts[event_type] = (when, str(refs))
        prior_when = when


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


async def run(org_slug: Optional[str], commit: bool) -> BackfillReport:
    from dotenv import load_dotenv
    load_dotenv("/srv/quantumpools/app/.env")
    db_url = os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(db_url)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    report = BackfillReport()

    async with Session() as db:
        # Which org(s)?
        if org_slug:
            org = (await db.execute(
                select(Organization).where(Organization.slug == org_slug)
            )).scalar_one_or_none()
            if not org:
                raise SystemExit(f"Organization with slug={org_slug!r} not found")
            orgs = [org]
        else:
            orgs = (await db.execute(select(Organization))).scalars().all()

        for org in orgs:
            logger.info(f"Backfilling org: {org.name} ({org.id}) slug={org.slug}")

            # Pass order matters: entity-creation events first so they're
            # in the stream when activation runs, and so downstream queries
            # like "jobs per case" see both sides.
            passes = [
                ("customers", backfill_customers),
                ("properties", backfill_properties),
                ("water_features", backfill_water_features),
                ("cases", backfill_cases),
                ("jobs", backfill_jobs),
                ("visits", backfill_visits),
                ("invoices", backfill_invoices),
                ("activation", backfill_activation),
            ]
            for name, fn in passes:
                await fn(db, org, report, commit)
                if commit:
                    await db.commit()
                logger.info(f"  {name} pass complete")
            logger.info("")

    await engine.dispose()
    return report


def print_report(report: BackfillReport, committed: bool) -> None:
    print()
    print("=" * 60)
    print(f"{'COMMIT' if committed else 'DRY-RUN'} REPORT — event backfill")
    print("=" * 60)
    print(f"Events to {'insert' if committed else 'emit'} (by type):")
    total = 0
    for et, n in report.by_event_type.most_common():
        skipped = report.already_exists.get(et, 0)
        total += n
        print(f"  {et:40s} {n:6d}  (already in DB: {skipped})")
    print(f"  {'TOTAL':40s} {total:6d}")
    print()
    if report.activation_firsts:
        print("Activation milestones (first per org):")
        for et, (when, refs) in report.activation_firsts.items():
            print(f"  {et:40s} {when.isoformat()} refs={refs}")
        print()
    if report.errors:
        print("Errors:")
        for e in report.errors:
            print(f"  {e}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org-slug", default=None,
                        help="Backfill a single org (default: all orgs)")
    parser.add_argument("--commit", action="store_true",
                        help="Actually write events (default: dry-run)")
    args = parser.parse_args()
    report = asyncio.run(run(args.org_slug, args.commit))
    print_report(report, committed=args.commit)


if __name__ == "__main__":
    main()
