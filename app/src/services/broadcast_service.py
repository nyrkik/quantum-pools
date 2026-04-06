"""Broadcast email service — queue and send bulk emails to filtered customer lists."""

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.broadcast_email import BroadcastEmail
from src.models.customer import Customer
from src.services.email_service import EmailService

logger = logging.getLogger(__name__)


class BroadcastService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_recipient_count(self, org_id: str, filter_type: str, filter_data: str | None = None) -> int:
        """Count how many customers match the filter."""
        customers = await self._get_recipients(org_id, filter_type, filter_data)
        return len(customers)

    async def create_broadcast(
        self,
        org_id: str,
        subject: str,
        body: str,
        filter_type: str = "all_active",
        filter_data: str | None = None,
        created_by: str | None = None,
        test_recipient: str | None = None,
    ) -> BroadcastEmail:
        """Create a broadcast and immediately begin sending."""
        # Test send bypasses customer resolution — single email to arbitrary address
        if filter_type == "test":
            if not test_recipient:
                raise ValueError("test_recipient required for test broadcasts")
            broadcast = BroadcastEmail(
                id=str(uuid.uuid4()),
                organization_id=org_id,
                subject=subject,
                body=body,
                filter_type="test",
                filter_data=test_recipient,
                recipient_count=1,
                status="sending",
                created_by=created_by,
            )
            self.db.add(broadcast)
            await self.db.commit()

            email_svc = EmailService(self.db)
            try:
                result = await email_svc.send_agent_reply(
                    org_id=org_id,
                    to=test_recipient,
                    subject=subject,
                    body_text=body,
                    is_new=True,
                )
                broadcast.sent_count = 1 if result.success else 0
                broadcast.failed_count = 0 if result.success else 1
            except Exception as e:
                logger.error(f"Test broadcast failed: {e}")
                broadcast.failed_count = 1

            broadcast.status = "completed"
            broadcast.completed_at = datetime.now(timezone.utc)
            await self.db.commit()
            return broadcast

        customers = await self._get_recipients(org_id, filter_type, filter_data)

        broadcast = BroadcastEmail(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            subject=subject,
            body=body,
            filter_type=filter_type,
            filter_data=filter_data,
            recipient_count=len(customers),
            status="sending",
            created_by=created_by,
        )
        self.db.add(broadcast)
        await self.db.commit()

        # Send synchronously (for now — move to background worker for large lists)
        email_svc = EmailService(self.db)
        sent = 0
        failed = 0

        for cust in customers:
            email_addr = cust.email
            if not email_addr:
                failed += 1
                continue

            # Send to first email if comma-separated
            primary_email = email_addr.split(",")[0].strip()
            if not primary_email:
                failed += 1
                continue

            try:
                result = await email_svc.send_agent_reply(
                    org_id=org_id,
                    to=primary_email,
                    subject=subject,
                    body_text=body,
                    is_new=True,
                )
                if result.success:
                    sent += 1
                else:
                    failed += 1
                    logger.warning(f"Broadcast send failed to {primary_email}: {result.error}")
            except Exception as e:
                failed += 1
                logger.error(f"Broadcast send error to {primary_email}: {e}")

        broadcast.sent_count = sent
        broadcast.failed_count = failed
        broadcast.status = "completed"
        broadcast.completed_at = datetime.now(timezone.utc)
        await self.db.commit()

        return broadcast

    async def _get_recipients(self, org_id: str, filter_type: str, filter_data: str | None = None) -> list:
        """Get customer list based on filter."""
        query = select(Customer).where(
            Customer.organization_id == org_id,
            Customer.is_active == True,
        )

        if filter_type == "commercial":
            query = query.where(Customer.customer_type == "commercial")
        elif filter_type == "residential":
            query = query.where(Customer.customer_type == "residential")
        elif filter_type == "custom" and filter_data:
            customer_ids = json.loads(filter_data)
            query = query.where(Customer.id.in_(customer_ids))
        # "all_active" uses the base query

        # Only customers with email addresses
        query = query.where(Customer.email.isnot(None), Customer.email != "")

        result = await self.db.execute(query)
        return result.scalars().all()
