"""Invoice service — CRUD, auto-numbering, status transitions, balance recalculation."""

import uuid
from typing import Optional, List
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload

from src.models.invoice import Invoice, InvoiceLineItem, InvoiceStatus
from src.models.customer import Customer
from src.core.exceptions import NotFoundError, ValidationError


class InvoiceService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _next_seq(self, org_id: str, pattern: str) -> int:
        """Find the highest sequence number matching pattern and return next."""
        import re
        result = await self.db.execute(
            select(Invoice.invoice_number)
            .where(
                Invoice.organization_id == org_id,
                Invoice.invoice_number.like(pattern),
            )
        )
        max_seq = 0
        for (num,) in result.all():
            digits = re.findall(r'\d+', num)
            if digits:
                seq = int(digits[-1]) if len(digits) == 1 else int(digits[-1])
                # For invoices like "26001" extract seq after YY prefix
                # For estimates like "EST-26001" extract seq after YY prefix
                raw = num.replace("EST-", "")
                if raw.isdigit() and len(raw) >= 3:
                    s = int(raw[2:])  # strip YY, get sequence
                    max_seq = max(max_seq, s)
        return max_seq + 1

    async def next_estimate_number(self, org_id: str) -> str:
        """EST-26001, EST-26002, ..."""
        from datetime import date as date_type
        yy = date_type.today().year % 100
        result = await self.db.execute(
            select(Invoice.invoice_number)
            .where(
                Invoice.organization_id == org_id,
                Invoice.invoice_number.like(f"EST-{yy}%"),
            )
        )
        max_seq = 0
        for (num,) in result.all():
            try:
                raw = num.replace("EST-", "")
                max_seq = max(max_seq, int(raw[2:]))
            except (ValueError, IndexError):
                pass
        return f"EST-{yy}{max_seq + 1:03d}"

    async def next_invoice_number(self, org_id: str) -> str:
        """26001, 26002, ..."""
        from datetime import date as date_type
        yy = date_type.today().year % 100
        result = await self.db.execute(
            select(Invoice.invoice_number)
            .where(
                Invoice.organization_id == org_id,
                Invoice.invoice_number.op("~")(f"^{yy}\\d+$"),
            )
        )
        max_seq = 0
        for (num,) in result.all():
            try:
                max_seq = max(max_seq, int(num[2:]))
            except (ValueError, IndexError):
                pass
        return f"{yy}{max_seq + 1:03d}"

    def _recalculate_totals(self, invoice: Invoice, line_items: list[InvoiceLineItem]) -> None:
        """Recalculate subtotal, tax, total, and balance from line items."""
        subtotal = sum(item.amount for item in line_items)
        taxable = sum(item.amount for item in line_items if item.is_taxed)
        tax_amount = round(taxable * (invoice.tax_rate / 100), 2) if invoice.tax_rate else 0.0
        total = round(subtotal - (invoice.discount or 0) + tax_amount, 2)

        invoice.subtotal = round(subtotal, 2)
        invoice.tax_amount = tax_amount
        invoice.total = total
        invoice.balance = round(total - (invoice.amount_paid or 0), 2)

    async def list(
        self,
        org_id: str,
        status: Optional[str] = None,
        customer_id: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
        document_type: Optional[str] = None,
    ) -> tuple[List[Invoice], int]:
        query = (
            select(Invoice)
            .where(Invoice.organization_id == org_id)
            .options(selectinload(Invoice.customer))
        )
        count_query = select(func.count(Invoice.id)).where(Invoice.organization_id == org_id)

        if document_type:
            query = query.where(Invoice.document_type == document_type)
            count_query = count_query.where(Invoice.document_type == document_type)

        if status:
            query = query.where(Invoice.status == status)
            count_query = count_query.where(Invoice.status == status)
        if customer_id:
            query = query.where(Invoice.customer_id == customer_id)
            count_query = count_query.where(Invoice.customer_id == customer_id)
        if date_from:
            query = query.where(Invoice.issue_date >= date_from)
            count_query = count_query.where(Invoice.issue_date >= date_from)
        if date_to:
            query = query.where(Invoice.issue_date <= date_to)
            count_query = count_query.where(Invoice.issue_date <= date_to)
        if search:
            search_filter = f"%{search}%"
            query = query.where(
                (Invoice.invoice_number.ilike(search_filter))
                | (Invoice.subject.ilike(search_filter))
            )
            count_query = count_query.where(
                (Invoice.invoice_number.ilike(search_filter))
                | (Invoice.subject.ilike(search_filter))
            )

        total = (await self.db.execute(count_query)).scalar() or 0
        result = await self.db.execute(
            query.order_by(Invoice.issue_date.desc(), Invoice.created_at.desc())
            .offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def get(self, org_id: str, invoice_id: str) -> Invoice:
        result = await self.db.execute(
            select(Invoice)
            .where(Invoice.id == invoice_id, Invoice.organization_id == org_id)
            .options(
                selectinload(Invoice.line_items),
                selectinload(Invoice.payments),
                selectinload(Invoice.customer),
            )
        )
        invoice = result.scalar_one_or_none()
        if not invoice:
            raise NotFoundError("Invoice")
        return invoice

    async def get_by_token(self, token: str) -> Invoice:
        """Get invoice by payment token (for public pay page)."""
        result = await self.db.execute(
            select(Invoice)
            .where(Invoice.payment_token == token)
            .options(
                selectinload(Invoice.line_items),
                selectinload(Invoice.customer),
            )
        )
        invoice = result.scalar_one_or_none()
        if not invoice:
            raise NotFoundError("Invoice")
        return invoice

    async def create(self, org_id: str, customer_id: str, line_items_data: List[dict], **kwargs) -> Invoice:
        # Verify customer exists
        cust_result = await self.db.execute(
            select(Customer).where(Customer.id == customer_id, Customer.organization_id == org_id)
        )
        if not cust_result.scalar_one_or_none():
            raise NotFoundError("Customer")

        doc_type = kwargs.get("document_type", "invoice")
        if doc_type == "estimate":
            invoice_number = await self.next_estimate_number(org_id)
        else:
            invoice_number = await self.next_invoice_number(org_id)

        invoice = Invoice(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            customer_id=customer_id,
            invoice_number=invoice_number,
            **kwargs,
        )
        self.db.add(invoice)

        # Create line items
        items = []
        for i, item_data in enumerate(line_items_data):
            amount = round(item_data.get("quantity", 1.0) * item_data.get("unit_price", 0.0), 2)
            # Validate service_id belongs to org if provided
            sid = item_data.get("service_id")
            if sid:
                from src.models.service import Service
                svc_check = await self.db.execute(
                    select(Service).where(Service.id == sid, Service.organization_id == org_id)
                )
                if not svc_check.scalar_one_or_none():
                    sid = None

            item = InvoiceLineItem(
                id=str(uuid.uuid4()),
                invoice_id=invoice.id,
                service_id=sid,
                description=item_data["description"],
                quantity=item_data.get("quantity", 1.0),
                unit_price=item_data.get("unit_price", 0.0),
                amount=amount,
                is_taxed=item_data.get("is_taxed", False),
                sort_order=item_data.get("sort_order", i),
            )
            self.db.add(item)
            items.append(item)

        self._recalculate_totals(invoice, items)
        await self.db.flush()

        # Reload with relationships
        return await self.get(org_id, invoice.id)

    async def update(self, org_id: str, invoice_id: str, line_items_data: Optional[List[dict]] = None, **kwargs) -> Invoice:
        invoice = await self.get(org_id, invoice_id)

        if invoice.status not in (InvoiceStatus.draft.value, InvoiceStatus.sent.value):
            raise ValidationError(f"Cannot edit invoice in '{invoice.status}' status")

        for key, value in kwargs.items():
            if value is not None:
                setattr(invoice, key, value)

        if line_items_data is not None:
            # Delete existing line items
            for item in list(invoice.line_items):
                await self.db.delete(item)

            # Create new line items
            items = []
            for i, item_data in enumerate(line_items_data):
                amount = round(item_data.get("quantity", 1.0) * item_data.get("unit_price", 0.0), 2)
                sid = item_data.get("service_id")
                if sid:
                    from src.models.service import Service
                    svc_check = await self.db.execute(
                        select(Service).where(Service.id == sid, Service.organization_id == invoice.organization_id)
                    )
                    if not svc_check.scalar_one_or_none():
                        sid = None
                item = InvoiceLineItem(
                    id=str(uuid.uuid4()),
                    invoice_id=invoice.id,
                    service_id=sid,
                    description=item_data["description"],
                    quantity=item_data.get("quantity", 1.0),
                    unit_price=item_data.get("unit_price", 0.0),
                    amount=amount,
                    is_taxed=item_data.get("is_taxed", False),
                    sort_order=item_data.get("sort_order", i),
                )
                self.db.add(item)
                items.append(item)

            self._recalculate_totals(invoice, items)
        else:
            self._recalculate_totals(invoice, list(invoice.line_items))

        await self.db.flush()
        return await self.get(org_id, invoice.id)

    async def send(self, org_id: str, invoice_id: str) -> Invoice:
        """Mark invoice as sent."""
        invoice = await self.get(org_id, invoice_id)
        if invoice.status == InvoiceStatus.void.value:
            raise ValidationError("Cannot send a voided invoice")
        if invoice.status == InvoiceStatus.paid.value:
            raise ValidationError("Invoice is already paid")

        from datetime import datetime, timezone
        invoice.status = InvoiceStatus.sent.value
        invoice.sent_at = datetime.now(timezone.utc)
        await self.db.flush()
        return invoice

    async def void(self, org_id: str, invoice_id: str) -> Invoice:
        """Void an invoice."""
        invoice = await self.get(org_id, invoice_id)
        if invoice.status == InvoiceStatus.paid.value:
            raise ValidationError("Cannot void a paid invoice")
        invoice.status = InvoiceStatus.void.value
        invoice.balance = 0.0
        await self.db.flush()
        return invoice

    async def write_off(self, org_id: str, invoice_id: str) -> Invoice:
        """Write off an invoice."""
        invoice = await self.get(org_id, invoice_id)
        if invoice.status == InvoiceStatus.void.value:
            raise ValidationError("Cannot write off a voided invoice")
        invoice.status = InvoiceStatus.written_off.value
        invoice.balance = 0.0
        await self.db.flush()
        return invoice

    async def mark_viewed(self, token: str) -> Invoice:
        """Mark invoice as viewed (from public pay page)."""
        invoice = await self.get_by_token(token)
        if invoice.status == InvoiceStatus.sent.value:
            from datetime import datetime, timezone
            invoice.status = InvoiceStatus.viewed.value
            invoice.viewed_at = datetime.now(timezone.utc)
            await self.db.flush()
        return invoice

    async def record_payment(self, invoice: Invoice, amount: float) -> None:
        """Update invoice after a payment is recorded."""
        invoice.amount_paid = round(invoice.amount_paid + amount, 2)
        invoice.balance = round(invoice.total - invoice.amount_paid, 2)

        if invoice.balance <= 0:
            invoice.status = InvoiceStatus.paid.value
            invoice.paid_date = date.today()
            invoice.balance = 0.0

        await self.db.flush()

    async def get_stats(self, org_id: str) -> dict:
        """Get invoice statistics for dashboard."""
        from datetime import date as date_type
        today = date_type.today()
        first_of_month = today.replace(day=1)

        # Exclude estimates from all financial stats
        invoices_only = and_(
            Invoice.organization_id == org_id,
            Invoice.document_type != "estimate",
        )

        # Outstanding (sent/viewed/overdue)
        outstanding_result = await self.db.execute(
            select(func.coalesce(func.sum(Invoice.balance), 0.0)).where(
                invoices_only,
                Invoice.status.in_([
                    InvoiceStatus.sent.value,
                    InvoiceStatus.viewed.value,
                    InvoiceStatus.overdue.value,
                ])
            )
        )
        total_outstanding = outstanding_result.scalar() or 0.0

        # Overdue
        overdue_result = await self.db.execute(
            select(func.coalesce(func.sum(Invoice.balance), 0.0)).where(
                invoices_only,
                Invoice.status == InvoiceStatus.overdue.value,
            )
        )
        total_overdue = overdue_result.scalar() or 0.0

        # Monthly revenue (paid this month)
        revenue_result = await self.db.execute(
            select(func.coalesce(func.sum(Invoice.total), 0.0)).where(
                invoices_only,
                Invoice.status == InvoiceStatus.paid.value,
                Invoice.paid_date >= first_of_month,
            )
        )
        monthly_revenue = revenue_result.scalar() or 0.0

        # Counts
        count_result = await self.db.execute(
            select(func.count(Invoice.id)).where(invoices_only)
        )
        invoice_count = count_result.scalar() or 0

        paid_result = await self.db.execute(
            select(func.count(Invoice.id)).where(
                invoices_only,
                Invoice.status == InvoiceStatus.paid.value,
            )
        )
        paid_count = paid_result.scalar() or 0

        overdue_count_result = await self.db.execute(
            select(func.count(Invoice.id)).where(
                invoices_only,
                Invoice.status == InvoiceStatus.overdue.value,
            )
        )
        overdue_count = overdue_count_result.scalar() or 0

        return {
            "total_outstanding": round(total_outstanding, 2),
            "total_overdue": round(total_overdue, 2),
            "monthly_revenue": round(monthly_revenue, 2),
            "invoice_count": invoice_count,
            "paid_count": paid_count,
            "overdue_count": overdue_count,
        }

    async def get_monthly(self, org_id: str, year: int) -> List[dict]:
        """Get monthly paid vs open totals for the given year."""
        from sqlalchemy import extract, case

        paid_statuses = [InvoiceStatus.paid.value]
        open_statuses = [
            InvoiceStatus.draft.value, InvoiceStatus.sent.value,
            InvoiceStatus.viewed.value, InvoiceStatus.overdue.value,
        ]

        result = await self.db.execute(
            select(
                extract("month", Invoice.issue_date).label("month"),
                func.coalesce(func.sum(
                    case((Invoice.status.in_(paid_statuses), Invoice.total), else_=0.0)
                ), 0.0).label("paid"),
                func.coalesce(func.sum(
                    case((Invoice.status.in_(open_statuses), Invoice.total), else_=0.0)
                ), 0.0).label("open"),
            ).where(
                Invoice.organization_id == org_id,
                Invoice.document_type != "estimate",
                extract("year", Invoice.issue_date) == year,
                Invoice.status != InvoiceStatus.void.value,
            ).group_by(extract("month", Invoice.issue_date))
        )

        month_data = {int(row.month): {"paid": round(float(row.paid), 2), "open": round(float(row.open), 2)} for row in result}
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        return [
            {"month": months[i], "paid": month_data.get(i + 1, {}).get("paid", 0), "open": month_data.get(i + 1, {}).get("open", 0)}
            for i in range(12)
        ]
