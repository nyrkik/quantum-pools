"""Import historical PSS invoices into QP.

Step 9-prequel for the AI Platform plan. PSS exported ~2000 invoices
spanning 2024-10 through now as three yearly CSVs. This script bridges
them into QP's Invoice table so Step 9's event backfill can emit real
historical invoice/payment/activation events with accurate timestamps.

Usage:
  dry-run (default — no DB writes):
    ./venv/bin/python app/scripts/import_pss_invoices.py \\
        --invoices-dir /tmp/pss_invoices \\
        --pssclients /srv/quantumpools/data/pssclients-2026-02-13.csv

  commit (actually writes):
    ./venv/bin/python app/scripts/import_pss_invoices.py \\
        --invoices-dir /tmp/pss_invoices \\
        --pssclients /srv/quantumpools/data/pssclients-2026-02-13.csv \\
        --commit

Bridge strategy: invoice CSVs reference Client by DisplayName
("Aghaian, Andrea" for residential, company name for commercial).
The pssclients CSV maps DisplayName → PSS client ID. QP customers
already have pss_id set from the earlier reimport. So:

    invoice.Client (name)
        → pssclients.DisplayName (same name format)
        → pssclients.ID
        → Customer.pss_id
        → Customer.id

Idempotency: uses Invoice.pss_invoice_id as the dedup key; rows already
imported are skipped.

Payment synthesis: for Paid-status invoices with a Paid On date, creates
a Payment record (method="unknown", recorded_by="pss_import").

Dry-run output reports: rows parsed, customers matched / unmatched /
ambiguous, invoices to insert, payments to synthesize, status mapping
breakdown.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
import sys
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Allow running from repo root without venv-activated PYTHONPATH gymnastics.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.customer import Customer  # noqa: E402
from src.models.invoice import Invoice  # noqa: E402
from src.models.payment import Payment  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


# --- PSS → QP status mapping ---
PSS_STATUS_MAP = {
    "paid": "paid",
    "sent": "sent",
    "late": "sent",         # late = sent + past due; due_date drives "late" display
    "written-off": "write_off",
    "draft": "draft",
}


# --- Data classes ---

@dataclass
class ParsedInvoice:
    """One row from a PSS invoice CSV, already typed + cleaned."""
    pss_invoice_id: str
    po_number: Optional[str]
    client_name: str
    client_zip: Optional[str]
    subject: Optional[str]
    status: str               # QP-normalized status
    issue_date: Optional[datetime.date]
    due_date: Optional[datetime.date]
    paid_on: Optional[datetime.date]
    paid_amount: float
    subtotal: float
    total: float
    balance: float
    notes: Optional[str]
    is_recurring: bool


@dataclass
class DryRunReport:
    total_rows: int = 0
    parsed: int = 0
    parse_errors: list[tuple[int, str, str]] = field(default_factory=list)  # (row, reason, raw)
    unmatched_clients: Counter = field(default_factory=Counter)  # client_name → count
    matched_invoices: int = 0
    already_imported: int = 0
    status_breakdown: Counter = field(default_factory=Counter)
    payments_to_create: int = 0
    source_files: list[str] = field(default_factory=list)
    customers_to_create: int = 0
    customers_by_type: Counter = field(default_factory=Counter)
    customer_sample_names: list[str] = field(default_factory=list)


# --- Parsers ---

def _parse_date(s: str):
    """PSS dates are YYYY-MM-DD or empty."""
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_float(s: str) -> float:
    s = (s or "").strip().replace(",", "")
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _normalize_status(pss_status: str) -> Optional[str]:
    key = (pss_status or "").strip().lower()
    return PSS_STATUS_MAP.get(key)


def parse_row(row: dict) -> Optional[ParsedInvoice]:
    """Turn one CSV row into a typed invoice record. Returns None if
    required fields are missing or malformed."""
    # Headers have leading spaces — normalize keys.
    row = {k.strip(): (v or "").strip() for k, v in row.items()}

    pss_id = row.get("Invoice ID", "").strip()
    client = row.get("Client", "").strip().strip('"')
    status = _normalize_status(row.get("Status", ""))

    if not pss_id or not client or not status:
        return None

    # Invoice model has no po_number or tags columns — append any non-empty
    # values to notes so the data isn't lost at import time.
    notes_parts = []
    if row.get("Notes"):
        notes_parts.append(row["Notes"])
    po = row.get("P.O Number", "")
    if po:
        notes_parts.append(f"PO #{po}")
    tags = row.get("Tags", "")
    if tags:
        notes_parts.append(f"Tags: {tags}")
    notes_combined = " | ".join(notes_parts) if notes_parts else None

    return ParsedInvoice(
        pss_invoice_id=pss_id,
        po_number=po or None,
        client_name=client,
        client_zip=row.get("Client Zip Code") or None,
        subject=row.get("Subject") or None,
        status=status,
        issue_date=_parse_date(row.get("Issue Date", "")),
        due_date=_parse_date(row.get("Due Date", "")),
        paid_on=_parse_date(row.get("Paid On", "")),
        paid_amount=_parse_float(row.get("Paid Amount", "")),
        subtotal=_parse_float(row.get("Sub Amount", "")),
        total=_parse_float(row.get("Total Amount", "")),
        balance=_parse_float(row.get("Balance", "")),
        notes=notes_combined,
        is_recurring=(row.get("Is Recurring", "").lower() == "yes"),
    )


# --- Bridge builder: PSS client ID → QP Customer.id ---


async def build_pssid_to_customer_id(db: AsyncSession, org_id: str) -> dict[str, str]:
    """Load Customer.pss_id → Customer.id for the given org."""
    mapping: dict[str, str] = {}
    result = await db.execute(
        select(Customer.id, Customer.pss_id).where(
            Customer.organization_id == org_id,
            Customer.pss_id.isnot(None),
        )
    )
    for cid, pss_id in result:
        mapping[pss_id] = cid
    return mapping


# --- Missing customers (churned) import ---


def load_pssclients(pssclients_path: Path) -> dict[str, dict]:
    """Full pssclients CSV as {pss_id: normalized_row}."""
    out = {}
    with open(pssclients_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row = {k.strip(): (v or "").strip() for k, v in row.items()}
            pss_id = row.get("ID*", "").strip()
            if pss_id:
                out[pss_id] = row
    return out


def scan_earliest_issue_dates(invoices_dir: Path) -> dict[str, datetime.date]:
    """One pass over all invoice CSVs → {client_name: earliest Issue Date}.
    Used to set a realistic created_at on churned customers we import."""
    earliest: dict[str, datetime.date] = {}
    for csv_path in sorted(invoices_dir.glob("pssinvoices-all-*.csv")):
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row = {k.strip(): (v or "").strip() for k, v in row.items()}
                client = row.get("Client", "").strip().strip('"')
                issue = _parse_date(row.get("Issue Date", ""))
                if client and issue:
                    if client not in earliest or issue < earliest[client]:
                        earliest[client] = issue
    return earliest


def build_missing_customers(
    pssclients: dict[str, dict],
    existing_pssid_set: set[str],
    earliest_dates: dict[str, datetime.date],
) -> list[dict]:
    """Return list of customer dicts to create for churned clients
    referenced by invoices but missing from QP. Keyed by pss_id."""
    out = []
    for pss_id, row in pssclients.items():
        if pss_id in existing_pssid_set:
            continue
        display = row.get("DisplayName", "").strip()
        if not display:
            continue
        # Only import if we actually have invoices for them
        # (skip inactive customers with zero invoice history — they'd
        # pollute the customer list with no analytic upside).
        if display not in earliest_dates:
            continue

        client_type = (row.get("ClientType", "").strip().lower()) or "residential"
        first = (row.get("FirstName") or "").strip() or row.get("CompanyName", "").strip() or display
        last = (row.get("LastName") or "").strip() or "—"
        # Force NOT-NULL fields to have something
        if not first:
            first = "—"
        if not last:
            last = "—"

        out.append({
            "pss_id": pss_id,
            "display_name": display,
            "first_name": first[:100],
            "last_name": last[:100],
            "company_name": (row.get("CompanyName") or "").strip()[:200] or None,
            "email": (row.get("Email") or "").strip()[:255] or None,
            "phone": (row.get("Phone") or "").strip()[:20] or None,
            "billing_address": (row.get("Address") or "").strip() or None,
            "billing_city": (row.get("City") or "").strip()[:100] or None,
            "billing_state": (row.get("State") or "").strip()[:50] or None,
            "billing_zip": (row.get("Zip") or "").strip()[:20] or None,
            "customer_type": "commercial" if client_type == "commercial" else "residential",
            "is_active": False,
            "status": "inactive",
            "created_at": earliest_dates.get(display),  # best-known signup approximation
            "notes": (row.get("Notes") or "").strip() or None,
        })
    return out


# --- Core ---

async def run(invoices_dir: Path, pssclients_path: Path, org_slug: str, commit: bool) -> DryRunReport:
    from dotenv import load_dotenv
    load_dotenv("/srv/quantumpools/app/.env")
    db_url = os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(db_url)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    report = DryRunReport()

    async with Session() as db:
        # Resolve org
        from src.models.organization import Organization
        org = (await db.execute(
            select(Organization).where(Organization.slug == org_slug)
        )).scalar_one_or_none()
        if not org:
            raise SystemExit(f"Organization with slug={org_slug!r} not found")

        logger.info(f"Org: {org.name} ({org.id})")
        logger.info("")

        # Bridge 1: DisplayName → PSS client ID (full PSS export)
        pssclients = load_pssclients(pssclients_path)
        disp_to_pssid = {r.get("DisplayName", ""): pss_id for pss_id, r in pssclients.items() if r.get("DisplayName")}
        logger.info(f"Loaded {len(disp_to_pssid)} DisplayName → pss_id mappings from {pssclients_path.name}")

        # Bridge 2: PSS client ID → QP Customer ID (what's already in QP)
        pssid_to_cid = await build_pssid_to_customer_id(db, org.id)
        logger.info(f"Loaded {len(pssid_to_cid)} pss_id → Customer.id mappings from QP DB")

        # First invoice-scan pass: find earliest Issue Date per client
        earliest_dates = scan_earliest_issue_dates(invoices_dir)
        logger.info(f"Found earliest Issue Date for {len(earliest_dates)} unique clients across invoices")

        # Missing-customer discovery: inactive PSS clients referenced by
        # invoices but not yet in QP.
        missing = build_missing_customers(
            pssclients, set(pssid_to_cid.keys()), earliest_dates,
        )
        report.customers_to_create = len(missing)
        for m in missing:
            report.customers_by_type[m["customer_type"]] += 1
        report.customer_sample_names = [m["display_name"] for m in missing[:10]]

        # Import missing customers if --commit; otherwise mock the bridge
        # so invoice-matching report below reflects post-import state.
        if commit and missing:
            logger.info(f"COMMIT: inserting {len(missing)} missing (inactive) customers...")
            for m in missing:
                cust = Customer(
                    id=str(uuid.uuid4()),
                    organization_id=org.id,
                    pss_id=m["pss_id"],
                    first_name=m["first_name"],
                    last_name=m["last_name"],
                    company_name=m["company_name"],
                    # display_name is a computed property — the real column is
                    # display_name_col and a before-insert hook populates it.
                    display_name_col=m["display_name"],
                    email=m["email"],
                    phone=m["phone"],
                    billing_address=m["billing_address"],
                    billing_city=m["billing_city"],
                    billing_state=m["billing_state"],
                    billing_zip=m["billing_zip"],
                    customer_type=m["customer_type"],
                    is_active=m["is_active"],
                    status=m["status"],
                    notes=m["notes"],
                    created_at=datetime.combine(m["created_at"], datetime.min.time(), tzinfo=timezone.utc)
                        if m["created_at"] else datetime.now(timezone.utc),
                )
                db.add(cust)
                # Update in-memory bridge so invoice loop sees them
                pssid_to_cid[m["pss_id"]] = cust.id
            await db.flush()

        # For dry-run, pretend missing customers exist in the bridge so
        # the invoice-match count reflects what a full commit would produce.
        if not commit:
            for m in missing:
                pssid_to_cid[m["pss_id"]] = f"DRYRUN-{m['pss_id']}"

        # Compose: DisplayName → Customer.id (post-import bridge)
        disp_to_cid = {
            disp: pssid_to_cid[pss_id]
            for disp, pss_id in disp_to_pssid.items()
            if pss_id in pssid_to_cid
        }
        logger.info(f"Composed {len(disp_to_cid)} DisplayName → Customer.id mappings (post-import)")
        logger.info("")

        # Pre-load already-imported pss_invoice_ids for idempotency
        existing_result = await db.execute(
            select(Invoice.pss_invoice_id).where(
                Invoice.organization_id == org.id,
                Invoice.pss_invoice_id.isnot(None),
            )
        )
        already_imported = {r[0] for r in existing_result if r[0]}
        logger.info(f"Already-imported pss_invoice_ids in QP: {len(already_imported)}")
        logger.info("")

        # Process each CSV file
        to_insert: list[tuple[ParsedInvoice, str]] = []  # (parsed, customer_id)

        for csv_path in sorted(invoices_dir.glob("pssinvoices-all-*.csv")):
            report.source_files.append(csv_path.name)
            logger.info(f"Processing {csv_path.name}...")

            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for i, row in enumerate(reader, start=2):  # start=2 because header is line 1
                    report.total_rows += 1
                    parsed = parse_row(row)
                    if not parsed:
                        report.parse_errors.append((i, "missing required field(s)", str(row)[:120]))
                        continue
                    report.parsed += 1
                    report.status_breakdown[parsed.status] += 1

                    if parsed.pss_invoice_id in already_imported:
                        report.already_imported += 1
                        continue

                    cid = disp_to_cid.get(parsed.client_name)
                    if not cid:
                        report.unmatched_clients[parsed.client_name] += 1
                        continue

                    report.matched_invoices += 1
                    if parsed.status == "paid" and parsed.paid_on:
                        report.payments_to_create += 1
                    to_insert.append((parsed, cid))

        # --- Commit path ---
        if commit:
            logger.info("")
            logger.info(f"COMMIT MODE — inserting {len(to_insert)} invoices + {report.payments_to_create} payments")
            for parsed, cid in to_insert:
                inv = Invoice(
                    id=str(uuid.uuid4()),
                    organization_id=org.id,
                    customer_id=cid,
                    pss_invoice_id=parsed.pss_invoice_id,
                    document_type="invoice",
                    status=parsed.status,
                    issue_date=parsed.issue_date,
                    due_date=parsed.due_date,
                    subtotal=parsed.subtotal,
                    total=parsed.total,
                    balance=parsed.balance,
                    amount_paid=parsed.paid_amount,
                    subject=parsed.subject,
                    notes=parsed.notes,
                    is_recurring=parsed.is_recurring,
                    # Match created_at to issue_date so event backfill (Step 9)
                    # produces accurate historical timestamps.
                    created_at=datetime.combine(parsed.issue_date, datetime.min.time(), tzinfo=timezone.utc)
                        if parsed.issue_date else datetime.now(timezone.utc),
                    sent_at=datetime.combine(parsed.issue_date, datetime.min.time(), tzinfo=timezone.utc)
                        if parsed.issue_date and parsed.status != "draft" else None,
                    paid_date=parsed.paid_on if parsed.status == "paid" else None,
                )
                db.add(inv)

                # Synthetic Payment for paid invoices
                if parsed.status == "paid" and parsed.paid_on:
                    pay = Payment(
                        id=str(uuid.uuid4()),
                        organization_id=org.id,
                        customer_id=cid,
                        invoice_id=inv.id,
                        amount=parsed.paid_amount,
                        payment_method="unknown",
                        payment_date=parsed.paid_on,
                        status="completed",
                        reference_number=parsed.pss_invoice_id,
                        recorded_by="pss_import",
                        created_at=datetime.combine(parsed.paid_on, datetime.min.time(), tzinfo=timezone.utc),
                    )
                    db.add(pay)

            await db.commit()
            logger.info("COMMIT DONE.")

    await engine.dispose()
    return report


def print_report(report: DryRunReport, top_unmatched: int = 30) -> None:
    line = "=" * 60
    print()
    print(line)
    print("DRY-RUN REPORT" if True else "COMMIT REPORT")
    print(line)
    print(f"Source files:         {', '.join(report.source_files)}")
    print(f"Total CSV rows:       {report.total_rows}")
    print(f"Parsed OK:            {report.parsed}")
    print(f"Parse errors:         {len(report.parse_errors)}")
    print(f"Already imported:     {report.already_imported}")
    print()
    print("Churned-customer import (runs before invoices):")
    print(f"  Customers to create:  {report.customers_to_create}")
    for t, n in report.customers_by_type.most_common():
        print(f"    {t:12s} {n}")
    if report.customer_sample_names:
        print(f"  Sample display_names: {', '.join(report.customer_sample_names)}")
    print()
    print("Invoice import (after customer import):")
    print(f"  Matched to customer:  {report.matched_invoices}")
    print(f"  Unmatched clients:    {sum(report.unmatched_clients.values())} rows across {len(report.unmatched_clients)} unique names")
    print(f"  Payments to synthesize (Paid status with Paid On date): {report.payments_to_create}")
    print()
    print("Status breakdown:")
    for status, n in report.status_breakdown.most_common():
        print(f"  {status:12s} {n}")
    print()
    if report.unmatched_clients:
        print(f"Top {top_unmatched} unmatched client names:")
        for name, n in report.unmatched_clients.most_common(top_unmatched):
            print(f"  {n:4d}×  {name}")
    else:
        print("(all client names matched)")
    print()
    if report.parse_errors[:10]:
        print("First 10 parse errors:")
        for row, reason, raw in report.parse_errors[:10]:
            print(f"  row {row}: {reason} — {raw[:100]}")
    print(line)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--invoices-dir", required=True, type=Path)
    parser.add_argument("--pssclients", required=True, type=Path)
    parser.add_argument("--org-slug", default="sapphire")
    parser.add_argument("--commit", action="store_true",
                        help="Actually write to DB (default: dry run)")
    args = parser.parse_args()

    if not args.invoices_dir.is_dir():
        raise SystemExit(f"--invoices-dir not a directory: {args.invoices_dir}")
    if not args.pssclients.is_file():
        raise SystemExit(f"--pssclients not a file: {args.pssclients}")

    report = asyncio.run(run(
        args.invoices_dir, args.pssclients,
        org_slug=args.org_slug, commit=args.commit,
    ))
    print_report(report)


if __name__ == "__main__":
    main()
