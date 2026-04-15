"""Estimate workflow service — approval creation, email sending, customer approval handling.

Consolidates estimate-related business logic from invoices.py, admin_actions.py, and public.py routers.
"""

import json
import logging
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.agent_action import AgentAction
from src.models.customer import Customer
from src.models.customer_contact import CustomerContact
from src.models.estimate_approval import EstimateApproval
from src.models.invoice import Invoice, InvoiceLineItem
from src.models.notification import Notification
from src.models.organization_user import OrganizationUser
from src.models.property import Property
from src.services.invoice_service import log_job_activity

logger = logging.getLogger(__name__)


class EstimateWorkflowService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_or_create_approval(self, org_id: str, invoice: Invoice) -> EstimateApproval:
        """Get existing approval record or create one with a fresh token and snapshot."""
        existing = (await self.db.execute(
            select(EstimateApproval).where(EstimateApproval.invoice_id == invoice.id)
        )).scalar_one_or_none()
        if existing:
            return existing

        items = (await self.db.execute(
            select(InvoiceLineItem).where(InvoiceLineItem.invoice_id == invoice.id).order_by(InvoiceLineItem.sort_order)
        )).scalars().all()

        snapshot = {
            "line_items": [
                {"description": li.description, "quantity": float(li.quantity),
                 "unit_price": float(li.unit_price), "total": float(li.amount or li.quantity * li.unit_price)}
                for li in items
            ],
            "total": float(invoice.total or 0),
            "subject": invoice.subject,
        }
        approval = EstimateApproval(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            invoice_id=invoice.id,
            approved_by_type="pending",
            approved_by_name="",
            approval_token=secrets.token_urlsafe(32),
            approval_method="email_link",
            snapshot_json=json.dumps(snapshot),
        )
        self.db.add(approval)
        await self.db.flush()
        return approval

    async def _resolve_recipients(self, customer_id: str) -> tuple[list[CustomerContact], Customer | None]:
        """Get estimate contacts and customer for a given customer_id."""
        customer = (await self.db.execute(
            select(Customer).where(Customer.id == customer_id)
        )).scalar_one_or_none()

        contacts = []
        if customer_id:
            contacts = list((await self.db.execute(
                select(CustomerContact).where(
                    CustomerContact.customer_id == customer_id,
                    CustomerContact.receives_estimates == True,
                    CustomerContact.email.isnot(None),
                )
            )).scalars().all())

        return contacts, customer

    async def _build_property_line(self, customer_id: str) -> str:
        """Build a human-readable property line for emails."""
        prop = (await self.db.execute(
            select(Property).where(Property.customer_id == customer_id, Property.is_active == True)
        )).scalars().first()
        if not prop:
            return ""
        if prop.name:
            return f"{prop.name} ({prop.address})" if prop.address else prop.name
        return prop.address or ""

    async def send_estimate_email(
        self, org_id: str, invoice: Invoice, to_email: str | None = None,
    ) -> dict:
        """Send estimate email to customer contacts. Creates approval record if needed.

        Returns {"sent": True, "to": [...], "approval_token": "..."} or raises.
        """
        from src.services.email_service import EmailService
        from src.core.config import settings

        if not invoice.customer_id:
            return {"error": "no_customer", "detail": "No customer linked"}

        contacts, customer = await self._resolve_recipients(invoice.customer_id)
        if not customer:
            return {"error": "no_customer", "detail": "Customer not found"}

        # Determine recipients
        if to_email:
            recipients = [to_email]
        elif contacts:
            recipients = [c.email for c in contacts]
        elif customer.email:
            recipients = [customer.email]
        else:
            return {"error": "no_email", "detail": "No email address for this customer"}

        # Get or create approval
        approval = await self._get_or_create_approval(org_id, invoice)

        # Set recipient info on approval
        if to_email:
            match = next((c for c in contacts if c.email == to_email), None)
            approval.recipient_name = " ".join(filter(None, [match.first_name, match.last_name])) if match and (match.first_name or match.last_name) else None
            approval.recipient_email = to_email
        elif contacts:
            c0 = contacts[0]
            approval.recipient_name = " ".join(filter(None, [c0.first_name, c0.last_name])) if (c0.first_name or c0.last_name) else None
            approval.recipient_email = contacts[0].email
        else:
            approval.recipient_name = None
            approval.recipient_email = customer.email

        # Build approval URL
        base_url = getattr(settings, "FRONTEND_URL", None) or "https://app.quantumpoolspro.com"
        approve_url = f"{base_url}/approve/{approval.approval_token}"

        property_line = await self._build_property_line(invoice.customer_id)

        def _first_name_for(email: str) -> str:
            match = next((c for c in contacts if c.email == email and c.first_name), None)
            return match.first_name if match else ""

        email_svc = EmailService(self.db)
        sent_to = []
        errors = []
        for recipient in recipients:
            result = await email_svc.send_estimate_email(
                org_id=org_id,
                to=recipient,
                estimate_number=invoice.invoice_number,
                subject=f"Estimate: {invoice.subject or 'Service Estimate'}",
                total=float(invoice.total or 0),
                view_url=approve_url,
                property_line=property_line,
                recipient_first_name=_first_name_for(recipient),
            )
            if result.success:
                sent_to.append(recipient)
            else:
                errors.append(f"{recipient}: {result.error}")

        if not sent_to:
            return {"error": "send_failed", "detail": f"Failed to send: {'; '.join(errors)}"}

        return {"sent": True, "to": sent_to, "approval_token": approval.approval_token}

    async def approve_by_admin(self, org_id: str, invoice: Invoice, user_id: str, user_name: str) -> dict:
        """Admin approves estimate on behalf of client. Creates frozen snapshot and job."""
        if invoice.document_type != "estimate":
            return {"error": "not_estimate", "detail": "Only estimates can be approved"}
        if invoice.approved_at:
            return {"error": "already_approved", "detail": "Estimate is already approved"}

        # Build frozen snapshot
        snapshot = {
            "estimate_number": invoice.invoice_number,
            "customer_name": invoice.customer.display_name if invoice.customer else "",
            "subject": invoice.subject,
            "line_items": [
                {"description": li.description, "quantity": li.quantity, "unit_price": li.unit_price, "amount": li.amount}
                for li in (invoice.line_items or [])
            ],
            "subtotal": invoice.subtotal,
            "discount": invoice.discount,
            "tax_rate": invoice.tax_rate,
            "tax_amount": invoice.tax_amount,
            "total": invoice.total,
            "notes": invoice.notes,
            "issue_date": invoice.issue_date.isoformat() if invoice.issue_date else None,
            "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
        }

        now = datetime.now(timezone.utc)
        # Reuse the pending row if send_estimate_email already created one —
        # otherwise we leave a stale pending duplicate that breaks
        # /invoices/{id}/approval's scalar_one_or_none().
        existing = (await self.db.execute(
            select(EstimateApproval).where(EstimateApproval.invoice_id == invoice.id)
        )).scalar_one_or_none()
        if existing and existing.approved_by_type == "pending":
            existing.approved_by_type = "admin_on_behalf"
            existing.approved_by_name = user_name
            existing.approved_by_user_id = user_id
            existing.approval_method = "admin_dashboard"
            existing.snapshot_json = json.dumps(snapshot)
            existing.approved_at = now
            approval = existing
        else:
            approval = EstimateApproval(
                organization_id=org_id,
                invoice_id=invoice.id,
                approved_by_type="admin_on_behalf",
                approved_by_name=user_name,
                approved_by_user_id=user_id,
                approval_method="admin_dashboard",
                snapshot_json=json.dumps(snapshot),
                approved_at=now,
            )
            self.db.add(approval)
        await self.db.flush()

        invoice.approved_at = now
        invoice.approved_by = user_name
        invoice.approval_id = approval.id
        invoice.status = "approved"

        # Create or update linked job
        from src.services.job_invoice_service import get_first_job_for_invoice, link_job_invoice
        action = await get_first_job_for_invoice(self.db, invoice.id)
        if action:
            action.status = "open"
        else:
            action = AgentAction(
                organization_id=org_id,
                customer_id=invoice.customer_id,
                case_id=invoice.case_id,
                action_type="repair",
                description=f"Approved: {invoice.subject or 'Service Estimate'}",
                status="open",
                job_path="customer",
                created_by=user_name,
            )
            self.db.add(action)
            await self.db.flush()
            await link_job_invoice(self.db, action.id, invoice.id, linked_by=user_name)

        await log_job_activity(self.db, invoice.id, f"Estimate approved by {user_name} (on behalf of client)")
        await self.db.commit()

        return {
            "approved": True,
            "approval_id": approval.id,
            "approved_by": user_name,
            "approved_at": now.isoformat(),
            "approval_token": approval.approval_token,
        }

    async def approve_by_customer(
        self, token: str, name: str, email: str | None,
        signature: str | None, user_agent: str | None, notes: str | None,
        client_ip: str | None,
    ) -> dict:
        """Customer approves estimate via public link. Records evidence chain."""
        approval = (await self.db.execute(
            select(EstimateApproval).where(EstimateApproval.approval_token == token)
        )).scalar_one_or_none()
        if not approval:
            return {"error": "not_found", "detail": "Estimate not found or link expired"}

        # Check if the underlying document has already been converted to an
        # invoice. Stale email links (customer clicks an old approval link
        # after the admin has already converted) used to silently overwrite
        # the invoice's status with "approved", producing invoices that look
        # unbilled when they're actually sent. Return a friendly state instead.
        current_invoice = (await self.db.execute(
            select(Invoice).where(Invoice.id == approval.invoice_id)
        )).scalar_one_or_none()
        if current_invoice and current_invoice.document_type == "invoice":
            return {
                "already_converted": True,
                "invoice_number": current_invoice.invoice_number,
                "invoice_total": float(current_invoice.total or 0),
                "payment_token": current_invoice.payment_token,
                "approved_at": approval.approved_at.isoformat() if approval.approved_at else None,
            }

        if approval.approved_by_type and approval.approved_by_type != "pending":
            return {"already_approved": True, "approved_at": approval.approved_at.isoformat()}

        if not name or not name.strip():
            return {"error": "validation", "detail": "Name is required"}
        if not signature or not signature.strip():
            return {"error": "validation", "detail": "Typed signature is required"}

        now = datetime.now(timezone.utc)
        approval.approved_at = now
        approval.approved_by_type = "client"
        approval.approved_by_name = name.strip()
        approval.client_email = email
        approval.client_ip = client_ip
        approval.approval_method = "email_link"
        approval.signature_data = signature.strip()
        approval.notes = f"User-Agent: {user_agent or 'unknown'}" + (f"\n{notes}" if notes else "")

        # Update invoice and create/update job
        invoice = (await self.db.execute(
            select(Invoice).where(Invoice.id == approval.invoice_id)
        )).scalar_one_or_none()
        if invoice:
            invoice.approved_at = now
            invoice.approved_by = name.strip()
            invoice.status = "approved"

            from src.services.job_invoice_service import get_first_job_for_invoice, link_job_invoice
            action = await get_first_job_for_invoice(self.db, invoice.id)
            if action:
                action.status = "open"
            else:
                action = AgentAction(
                    id=str(uuid.uuid4()),
                    organization_id=approval.organization_id,
                    customer_id=invoice.customer_id,
                    case_id=invoice.case_id,
                    action_type="repair",
                    description=f"Approved: {invoice.subject or 'Service Estimate'}",
                    status="open",
                    job_path="customer",
                    created_by=name.strip(),
                )
                self.db.add(action)
                await self.db.flush()
                await link_job_invoice(self.db, action.id, invoice.id, linked_by=name.strip())

            # Update case status
            if invoice.case_id:
                try:
                    from src.services.service_case_service import ServiceCaseService
                    await ServiceCaseService(self.db).update_status_from_children(invoice.case_id)
                except Exception:
                    pass

        # Notify admins/owners
        if invoice:
            admins = (await self.db.execute(
                select(OrganizationUser).where(
                    OrganizationUser.organization_id == approval.organization_id,
                    OrganizationUser.role.in_(("owner", "admin")),
                )
            )).scalars().all()

            for admin in admins:
                self.db.add(Notification(
                    organization_id=approval.organization_id,
                    user_id=admin.user_id,
                    type="estimate_approved",
                    title=f"Estimate approved by {name.strip()}",
                    body=f"{invoice.invoice_number} — {invoice.subject or 'Service Estimate'} (${invoice.total:,.2f})",
                    link=f"/invoices/{invoice.id}",
                ))

            await log_job_activity(self.db, invoice.id, f"Estimate {invoice.invoice_number} approved by customer ({name.strip()})")

        await self.db.commit()
        return {"approved": True, "approved_at": now.isoformat()}
