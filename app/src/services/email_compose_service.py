"""Email compose + AI draft service.

Handles outbound email composition with thread tracking, and AI-assisted
draft generation using customer context.
"""

import json
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
from src.core.ai_models import get_model

logger = logging.getLogger(__name__)

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


from src.utils.thread_utils import normalize_subject as _normalize_subject, make_thread_key as _make_thread_key


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
        sender_name: str | None = None,
        job_id: str | None = None,
        sender_user_id: str | None = None,
        attachment_ids: list[str] | None = None,
    ) -> dict:
        """Send email, create AgentMessage + AgentThread records.

        Order: create all records first (status=queued), commit, then send.
        If send fails, records exist with queued status — no phantom emails.
        If send succeeds, update to sent — no lost tracking records.
        """
        # Resolve FROM address
        from_address_override = None
        action = None
        if job_id:
            from src.models.agent_action import AgentAction
            action = (await self.db.execute(
                select(AgentAction).where(AgentAction.id == job_id, AgentAction.organization_id == org_id)
            )).scalar_one_or_none()
            if action and action.thread_id:
                row = (await self.db.execute(
                    select(AgentThread.delivered_to).where(AgentThread.id == action.thread_id)
                )).first()
                if row and row[0]:
                    from_address_override = row[0]

        from_email = (from_address_override
                      or os.environ.get("AGENT_FROM_EMAIL", "noreply@quantumpoolspro.com"))

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

        # Find or create thread
        thread = None
        if action and action.thread_id:
            thread = (await self.db.execute(
                select(AgentThread).where(AgentThread.id == action.thread_id)
            )).scalar_one_or_none()

        if not thread:
            thread = await self._get_or_create_thread(
                org_id=org_id,
                contact_email=to,
                subject=subject,
                customer_id=customer_id,
                customer_name=customer_name,
                property_address=property_address,
            )

        # ── Step 1: Create all records with status=queued ──
        now = datetime.now(timezone.utc)
        message = AgentMessage(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            direction="outbound",
            from_email=from_email,
            to_email=to,
            subject=subject,
            body=body,
            status="queued",
            received_at=now,
            matched_customer_id=customer_id,
            customer_name=customer_name,
            property_address=property_address,
            thread_id=thread.id,
        )
        self.db.add(message)

        # Mark pending inbound messages as handled
        pending_msgs = await self.db.execute(
            select(AgentMessage).where(
                AgentMessage.thread_id == thread.id,
                AgentMessage.status == "pending",
                AgentMessage.direction == "inbound",
            )
        )
        for pm in pending_msgs.scalars().all():
            pm.status = "handled"

        # Job bookkeeping
        if job_id:
            from src.models.agent_action import AgentActionComment
            draft_comments = await self.db.execute(
                select(AgentActionComment).where(
                    AgentActionComment.action_id == job_id,
                    AgentActionComment.text.startswith("[DRAFT_EMAIL]"),
                )
            )
            for dc in draft_comments.scalars().all():
                dc.text = f"[SENT_EMAIL]\nTo: {to}\nSubject: {subject}\n---\n{body}"

            confirm_comment = AgentActionComment(
                id=str(uuid.uuid4()),
                organization_id=org_id,
                action_id=job_id,
                author=sender_name or "System",
                text=f"Email sent to {to}: {subject}",
            )
            self.db.add(confirm_comment)

        # Commit records before sending — nothing is lost if send fails
        await self.db.commit()

        # ── Step 2: Load attachments and send email ──
        email_atts = None
        att_rows = []
        if attachment_ids:
            from src.models.message_attachment import MessageAttachment
            from pathlib import Path
            upload_root = Path(os.environ.get("UPLOAD_DIR", "./uploads"))
            rows = (await self.db.execute(
                select(MessageAttachment).where(
                    MessageAttachment.id.in_(attachment_ids[:5]),
                    MessageAttachment.organization_id == org_id,
                    MessageAttachment.source_type == "agent_message",
                    MessageAttachment.source_id.is_(None),
                )
            )).scalars().all()
            email_atts = []
            for a in rows:
                fpath = upload_root / "attachments" / a.organization_id / a.stored_filename
                if fpath.exists():
                    email_atts.append({
                        "filename": a.filename,
                        "content_bytes": fpath.read_bytes(),
                        "mime_type": a.mime_type,
                    })
                a.source_id = message.id
            att_rows = list(rows)
            await self.db.commit()

        email_svc = EmailService(self.db)
        result = await email_svc.send_agent_reply(
            org_id, to, subject, body,
            from_address=from_address_override,
            sender_name=sender_name,
            is_new=True,
            attachments=email_atts or None,
        )

        # ── Step 3: Update status based on result ──
        if result.success:
            message.status = "sent"
            message.sent_at = datetime.now(timezone.utc)
        else:
            message.status = "failed"
        await self.db.commit()

        # Recalculate thread status
        from src.services.agents.thread_manager import update_thread_status
        await update_thread_status(thread.id)

        if not result.success:
            return {"success": False, "error": result.error}

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

        # Get sender name for the sign-off
        sender_first = ""
        if context_parts:
            # Check if we have sender info passed via instruction
            pass
        # Try to get from the current user context (passed through org tone rules)
        org = await self._get_org(org_id)

        system_prompt = (
            f"You are an email assistant for {org_name}, a professional pool service company.\n"
            f"Write professional but friendly emails. Be concise and specific.\n"
            f"Start with a generic greeting like 'Hi,' or 'Hello,' — do NOT use the customer's name, property name, or any personal identifier in the greeting. This avoids misgendering and keeps it professional for any recipient.\n"
            f"Use details from the customer context when relevant.\n"
            f"NEVER include the property address or street address in the email body. The client knows where they live. Reference the property by name only if it has one (e.g., 'Pinebrook Village'), otherwise don't reference the location at all.\n"
            f"NEVER include account numbers, invoice numbers, or internal reference IDs unless the customer specifically asked about them.\n"
            f"Do NOT include a signature block — it will be appended automatically.\n"
            f"End the body with a brief closing like 'Best,' or 'Thanks,' on its own line. Do NOT add a name after the closing — the signature system handles that.\n"
            f"Do NOT include greeting headers like 'Subject:' in the body.\n\n"
            f"CONTEXT:\n{context_block}\n\n"
            f"You MUST respond with ONLY a JSON object, no other text. Format:\n"
            f'{{"subject": "the email subject", "body": "the email body text"}}\n'
            f"The body should be plain text (no HTML). Use natural line breaks.\n"
            f"Do NOT wrap in markdown code blocks. Do NOT add any text before or after the JSON."
        )

        # Inject lessons from past corrections
        try:
            from src.services.agent_learning_service import AgentLearningService, AGENT_EMAIL_DRAFTER
            learner = AgentLearningService(self.db)
            lessons = await learner.build_lessons_prompt(
                org_id, AGENT_EMAIL_DRAFTER,
                category=None, customer_id=customer_id,
            )
            if lessons:
                system_prompt += "\n\n" + lessons
        except Exception:
            pass

        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
            response = client.messages.create(
                model=await get_model("fast"),
                max_tokens=1024,
                system=system_prompt,
                messages=[{"role": "user", "content": task}],
            )
            text = response.content[0].text.strip()

            # Parse JSON from response — try multiple extraction strategies
            # Strip markdown code blocks
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)

            # Try direct parse first
            try:
                parsed = json.loads(text)
                return {"subject": parsed.get("subject", ""), "body": parsed.get("body", "")}
            except json.JSONDecodeError:
                pass

            # Try extracting JSON object from mixed text
            json_match = re.search(r"\{[^{}]*\"subject\"[^{}]*\"body\"[^{}]*\}", text, re.DOTALL)
            if json_match:
                try:
                    parsed = json.loads(json_match.group())
                    return {"subject": parsed.get("subject", ""), "body": parsed.get("body", "")}
                except json.JSONDecodeError:
                    pass

            # Last resort: use the raw text as the body
            logger.warning("AI returned non-JSON response for draft, using raw text")
            return {"subject": "Follow-up", "body": text if text else "", "error": "AI returned unexpected format"}
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
