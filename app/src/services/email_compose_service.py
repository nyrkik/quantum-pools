"""Email compose + AI draft service.

Handles outbound email composition with thread tracking, and AI-assisted
draft generation using customer context.
"""

import logging
import os
import re
import uuid
from datetime import datetime, timezone

import anthropic
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.agent_message import AgentMessage
from src.models.agent_thread import AgentThread
from src.models.customer import Customer
from src.models.invoice import Invoice
from src.models.organization import Organization
from src.models.property import Property
from src.models.visit import Visit
from src.models.water_feature import WaterFeature
from src.services.email_service import EmailMessage, EmailService

logger = logging.getLogger(__name__)

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


def _normalize_subject(subject: str) -> str:
    """Strip Re:/Fwd: prefixes for thread matching."""
    s = subject.strip()
    while True:
        lower = s.lower()
        if lower.startswith("re:"):
            s = s[3:].strip()
        elif lower.startswith("fwd:"):
            s = s[4:].strip()
        elif lower.startswith("fw:"):
            s = s[3:].strip()
        else:
            break
    return s


def _make_thread_key(contact_email: str, subject: str) -> str:
    return f"{_normalize_subject(subject)}|{contact_email}".lower()


class EmailComposeService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Compose & send
    # ------------------------------------------------------------------

    async def compose_and_send(
        self,
        org_id: str,
        to: str,
        subject: str,
        body: str,
        customer_id: str | None = None,
    ) -> dict:
        """Send email, create AgentMessage + AgentThread records."""
        org = await self._get_org(org_id)
        signature = org.agent_signature if org else None

        # Append signature
        full_body = body
        if signature:
            full_body = f"{body}\n\n--\n{signature}"

        email_svc = EmailService(self.db)
        msg = EmailMessage(to=to, subject=subject, text_body=full_body)
        result = await email_svc.send_email(org_id, msg)

        if not result.success:
            return {"success": False, "error": result.error}

        # Resolve customer info
        customer_name = None
        property_address = None
        if customer_id:
            cust = (await self.db.execute(
                select(Customer).where(Customer.id == customer_id)
            )).scalar_one_or_none()
            if cust:
                customer_name = cust.display_name
                prop = (await self.db.execute(
                    select(Property).where(Property.customer_id == customer_id).limit(1)
                )).scalar_one_or_none()
                if prop:
                    property_address = prop.address

        from_email = (org.agent_from_email if org and org.agent_from_email
                      else os.environ.get("AGENT_FROM_EMAIL", "noreply@quantumpoolspro.com"))

        # Find or create thread
        thread = await self._get_or_create_thread(
            org_id=org_id,
            contact_email=to,
            subject=subject,
            customer_id=customer_id,
            customer_name=customer_name,
            property_address=property_address,
        )

        # Create message record
        now = datetime.now(timezone.utc)
        message = AgentMessage(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            direction="outbound",
            from_email=from_email,
            to_email=to,
            subject=subject,
            body=full_body,
            status="sent",
            sent_at=now,
            received_at=now,
            matched_customer_id=customer_id,
            customer_name=customer_name,
            property_address=property_address,
            thread_id=thread.id,
        )
        self.db.add(message)

        # Update thread
        thread.message_count = (thread.message_count or 0) + 1
        thread.last_message_at = now
        thread.last_direction = "outbound"
        thread.last_snippet = body[:200]
        thread.status = "handled"
        thread.has_pending = False

        await self.db.commit()

        return {
            "success": True,
            "thread_id": thread.id,
            "message_id": message.id,
        }

    # ------------------------------------------------------------------
    # AI draft
    # ------------------------------------------------------------------

    async def generate_draft(
        self,
        org_id: str,
        instruction: str,
        customer_id: str | None = None,
        existing_body: str | None = None,
    ) -> dict:
        """Generate an AI email draft with optional customer context."""
        if not ANTHROPIC_KEY:
            return {"subject": "", "body": "", "error": "AI not configured"}

        org = await self._get_org(org_id)
        context_parts: list[str] = []

        # Org context
        org_name = org.name if org else "Pool Service Company"
        context_parts.append(f"Company: {org_name}")
        if org and org.agent_tone_rules:
            context_parts.append(f"Tone guidelines: {org.agent_tone_rules}")

        # Customer context
        if customer_id:
            ctx = await self.get_customer_context(org_id, customer_id)
            if ctx:
                context_parts.append(f"Customer: {ctx['name']}")
                if ctx.get("company"):
                    context_parts.append(f"Company: {ctx['company']}")
                if ctx.get("type"):
                    context_parts.append(f"Type: {ctx['type']}")
                if ctx.get("email"):
                    context_parts.append(f"Email: {ctx['email']}")
                if ctx.get("properties"):
                    props = ", ".join(p["address"] for p in ctx["properties"] if p.get("address"))
                    if props:
                        context_parts.append(f"Properties: {props}")
                if ctx.get("open_invoices"):
                    inv_lines = []
                    for inv in ctx["open_invoices"][:3]:
                        inv_lines.append(f"  #{inv['number']} — ${inv['total']:.2f} (due {inv['due_date']})")
                    context_parts.append("Open invoices:\n" + "\n".join(inv_lines))
                if ctx.get("balance") and ctx["balance"] > 0:
                    context_parts.append(f"Outstanding balance: ${ctx['balance']:.2f}")
                if ctx.get("last_visit"):
                    context_parts.append(f"Last service visit: {ctx['last_visit']}")
                if ctx.get("recent_threads"):
                    thread_lines = []
                    for t in ctx["recent_threads"][:3]:
                        thread_lines.append(f"  - {t['subject']} ({t['status']})")
                    context_parts.append("Recent conversations:\n" + "\n".join(thread_lines))
                if ctx.get("water_features"):
                    wf_lines = []
                    for wf in ctx["water_features"][:5]:
                        wf_lines.append(f"  - {wf['name']} ({wf['type']}, {wf.get('gallons', 'unknown')} gal)")
                    context_parts.append("Water features:\n" + "\n".join(wf_lines))

        context_block = "\n".join(context_parts) if context_parts else "No customer context available."

        # Build prompt
        if existing_body:
            task = (
                f"The user wants to improve or complete this email draft.\n"
                f"Current draft:\n---\n{existing_body}\n---\n"
                f"User instruction: {instruction}\n"
                f"Rewrite the full email (subject and body)."
            )
        else:
            task = (
                f"Write a new email based on this instruction: {instruction}\n"
                f"Generate both a subject line and body."
            )

        system_prompt = (
            f"You are an email assistant for {org_name}, a professional pool service company.\n"
            f"Write professional but friendly emails. Be concise and specific.\n"
            f"Use details from the customer context when relevant.\n"
            f"Do NOT include a signature — it will be appended automatically.\n"
            f"Do NOT include greeting headers like 'Subject:' in the body.\n\n"
            f"CONTEXT:\n{context_block}\n\n"
            f"Respond in this exact JSON format:\n"
            f'{{"subject": "...", "body": "..."}}\n'
            f"The body should be plain text (no HTML). Use natural line breaks."
        )

        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
            response = client.messages.create(
                model="claude-haiku-4-20250414",
                max_tokens=1024,
                system=system_prompt,
                messages=[{"role": "user", "content": task}],
            )
            text = response.content[0].text.strip()

            # Parse JSON from response
            import json
            # Handle markdown code blocks
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)

            parsed = json.loads(text)
            return {
                "subject": parsed.get("subject", ""),
                "body": parsed.get("body", ""),
            }
        except json.JSONDecodeError:
            # Try to extract subject and body from non-JSON response
            logger.warning("AI returned non-JSON response for draft")
            return {"subject": "", "body": text if text else "", "error": "AI returned unexpected format"}
        except Exception as e:
            logger.error(f"AI draft generation failed: {e}")
            return {"subject": "", "body": "", "error": str(e)}

    # ------------------------------------------------------------------
    # Customer context
    # ------------------------------------------------------------------

    async def get_customer_context(self, org_id: str, customer_id: str) -> dict | None:
        """Load customer context for compose UI and AI drafting."""
        cust = (await self.db.execute(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.organization_id == org_id,
            )
        )).scalar_one_or_none()

        if not cust:
            return None

        # Properties
        props = (await self.db.execute(
            select(Property).where(Property.customer_id == customer_id)
        )).scalars().all()

        properties = [
            {"id": p.id, "address": p.address, "name": p.name}
            for p in props
        ]

        # Water features
        water_features = []
        for p in props:
            bows = (await self.db.execute(
                select(WaterFeature).where(WaterFeature.property_id == p.id)
            )).scalars().all()
            for b in bows:
                water_features.append({
                    "name": b.name or b.water_type,
                    "type": b.water_type,
                    "gallons": b.pool_gallons,
                })

        # Recent threads
        threads = (await self.db.execute(
            select(AgentThread)
            .where(AgentThread.matched_customer_id == customer_id)
            .order_by(desc(AgentThread.last_message_at))
            .limit(5)
        )).scalars().all()

        recent_threads = [
            {"subject": t.subject, "status": t.status, "last_at": t.last_message_at.isoformat() if t.last_message_at else None}
            for t in threads
        ]

        # Open invoices
        open_invoices = []
        try:
            invoices = (await self.db.execute(
                select(Invoice).where(
                    Invoice.customer_id == customer_id,
                    Invoice.status.in_(("sent", "overdue", "pending")),
                ).order_by(desc(Invoice.due_date)).limit(5)
            )).scalars().all()
            for inv in invoices:
                open_invoices.append({
                    "number": inv.invoice_number,
                    "total": float(inv.total or 0),
                    "due_date": inv.due_date.isoformat() if inv.due_date else "N/A",
                    "status": inv.status,
                })
        except Exception:
            pass  # Invoice model may not have all fields

        # Last visit
        last_visit = None
        try:
            prop_ids = [p.id for p in props]
            if prop_ids:
                visit = (await self.db.execute(
                    select(Visit)
                    .where(Visit.property_id.in_(prop_ids))
                    .order_by(desc(Visit.visit_date))
                    .limit(1)
                )).scalar_one_or_none()
                if visit:
                    last_visit = visit.scheduled_date.isoformat() if visit.scheduled_date else None
        except Exception:
            pass

        # Open jobs (agent actions via thread)
        open_jobs = []
        try:
            from src.models.agent_action import AgentAction
            thread_ids = [t.id for t in threads]
            if thread_ids:
                actions = (await self.db.execute(
                    select(AgentAction).where(
                        AgentAction.thread_id.in_(thread_ids),
                        AgentAction.status.in_(("open", "in_progress")),
                    ).limit(5)
                )).scalars().all()
                for a in actions:
                    open_jobs.append({
                        "type": a.action_type,
                        "description": a.description,
                        "status": a.status,
                    })
        except Exception:
            pass

        return {
            "id": cust.id,
            "name": cust.display_name,
            "email": cust.email,
            "phone": cust.phone,
            "company": cust.company_name,
            "type": cust.customer_type,
            "balance": float(cust.balance or 0),
            "properties": properties,
            "water_features": water_features,
            "recent_threads": recent_threads,
            "open_invoices": open_invoices,
            "open_jobs": open_jobs,
            "last_visit": last_visit,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get_org(self, org_id: str) -> Organization | None:
        result = await self.db.execute(
            select(Organization).where(Organization.id == org_id)
        )
        return result.scalar_one_or_none()

    async def _get_or_create_thread(
        self,
        org_id: str,
        contact_email: str,
        subject: str,
        customer_id: str | None = None,
        customer_name: str | None = None,
        property_address: str | None = None,
    ) -> AgentThread:
        """Find existing thread or create new one."""
        thread_key = _make_thread_key(contact_email, subject)

        result = await self.db.execute(
            select(AgentThread).where(AgentThread.thread_key == thread_key)
        )
        thread = result.scalar_one_or_none()

        if not thread:
            thread = AgentThread(
                id=str(uuid.uuid4()),
                organization_id=org_id,
                thread_key=thread_key,
                contact_email=contact_email,
                subject=subject,
                matched_customer_id=customer_id,
                customer_name=customer_name,
                property_address=property_address,
                status="handled",
                message_count=0,
            )
            self.db.add(thread)
            await self.db.flush()
        else:
            if customer_id and not thread.matched_customer_id:
                thread.matched_customer_id = customer_id
            if customer_name and not thread.customer_name:
                thread.customer_name = customer_name

        return thread
