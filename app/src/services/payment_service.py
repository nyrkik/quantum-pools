"""Payment service — record payments, update invoice and customer balance."""

import uuid
from typing import Optional, List
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from src.models.payment import Payment, PaymentStatus
from src.models.invoice import Invoice
from src.models.customer import Customer
from src.core.exceptions import NotFoundError, ValidationError
from src.services.invoice_service import InvoiceService


class PaymentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(
        self,
        org_id: str,
        customer_id: Optional[str] = None,
        invoice_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[List[Payment], int]:
        query = (
            select(Payment)
            .where(Payment.organization_id == org_id)
            .options(selectinload(Payment.customer), selectinload(Payment.invoice))
        )
        count_query = select(func.count(Payment.id)).where(Payment.organization_id == org_id)

        if customer_id:
            query = query.where(Payment.customer_id == customer_id)
            count_query = count_query.where(Payment.customer_id == customer_id)
        if invoice_id:
            query = query.where(Payment.invoice_id == invoice_id)
            count_query = count_query.where(Payment.invoice_id == invoice_id)

        total = (await self.db.execute(count_query)).scalar() or 0
        result = await self.db.execute(
            query.order_by(Payment.payment_date.desc(), Payment.created_at.desc())
            .offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def create(self, org_id: str, **kwargs) -> Payment:
        customer_id = kwargs["customer_id"]
        invoice_id = kwargs.get("invoice_id")

        # Verify customer
        cust_result = await self.db.execute(
            select(Customer).where(Customer.id == customer_id, Customer.organization_id == org_id)
        )
        customer = cust_result.scalar_one_or_none()
        if not customer:
            raise NotFoundError("Customer")

        # Verify invoice if provided
        invoice = None
        if invoice_id:
            inv_svc = InvoiceService(self.db)
            invoice = await inv_svc.get(org_id, invoice_id)
            if invoice.customer_id != customer_id:
                raise ValidationError("Invoice does not belong to this customer")

        payment = Payment(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            status=PaymentStatus.completed.value,
            **kwargs,
        )
        self.db.add(payment)

        # Update invoice balance
        if invoice:
            inv_svc = InvoiceService(self.db)
            await inv_svc.record_payment(invoice, payment.amount)

        # Update customer balance
        customer.balance = round(customer.balance - payment.amount, 2)

        await self.db.flush()

        # Activation funnel — first-payment-received for this org.
        from src.services.events.activation_tracker import emit_if_first
        await emit_if_first(
            self.db,
            "activation.first_payment_received",
            organization_id=org_id,
            entity_refs={
                "customer_id": customer_id,
                **({"invoice_id": invoice_id} if invoice_id else {}),
            },
            source="payment_service",
        )

        await self.db.refresh(payment)
        return payment

    async def void(self, org_id: str, payment_id: str) -> Payment:
        """Void a payment — reverses invoice balance and customer balance."""
        result = await self.db.execute(
            select(Payment)
            .where(Payment.id == payment_id, Payment.organization_id == org_id)
            .options(selectinload(Payment.customer), selectinload(Payment.invoice))
        )
        payment = result.scalar_one_or_none()
        if not payment:
            raise NotFoundError("Payment")
        if payment.status == PaymentStatus.refunded.value:
            raise ValidationError("Payment is already voided")

        payment.status = PaymentStatus.refunded.value

        # Reverse invoice balance
        if payment.invoice_id:
            invoice = payment.invoice
            if invoice:
                invoice.amount_paid = round((invoice.amount_paid or 0) - payment.amount, 2)
                invoice.balance = round((invoice.total or 0) - invoice.amount_paid, 2)
                if invoice.status == "paid" and invoice.balance > 0:
                    invoice.status = "sent"

        # Reverse customer balance
        customer = payment.customer
        if customer:
            customer.balance = round(customer.balance + payment.amount, 2)

        await self.db.flush()
        await self.db.refresh(payment)
        return payment
