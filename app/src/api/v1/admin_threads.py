"""Admin thread endpoints — thin router delegating to AgentThreadService.

Access: owner, admin, manager (visibility filtering replaces hard role gating).
"""

import json
import re
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.events import EventType, publish
from src.api.deps import OrgUserContext, require_roles, OrgRole
from src.schemas.agent_thread import ApproveBody, ReviseDraftBody, AssignThreadBody
from src.services.agent_thread_service import AgentThreadService
from src.services.thread_action_service import ThreadActionService
from src.services.thread_ai_service import ThreadAIService

router = APIRouter(prefix="/admin", tags=["admin-threads"])


async def _get_user_perm_slugs(ctx: OrgUserContext, db: AsyncSession) -> set[str]:
    """Load user's permission slugs for visibility filtering."""
    perms = await ctx.load_permissions(db)
    return set(perms.keys())


@router.get("/client-search")
async def search_clients(
    q: str = Query(..., min_length=2),
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Search customers + properties for autocomplete."""
    service = AgentThreadService(db)
    return await service.search_clients(org_id=ctx.organization_id, q=q)


@router.get("/agent-threads")
async def list_threads(
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    exclude_spam: bool = Query(True),
    exclude_ignored: bool = Query(False),
    assigned_to: Optional[str] = Query(None),
    customer_id: Optional[str] = Query(None),
    folder_id: Optional[str] = Query(None),
    folder: Optional[str] = Query(None),  # system_key shortcut: "inbox", "sent", "automated", "spam"
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """List conversation threads (visibility-filtered by user permissions)."""
    perm_slugs = await _get_user_perm_slugs(ctx, db)
    service = AgentThreadService(db)
    return await service.list_threads(
        org_id=ctx.organization_id,
        status=status,
        search=search,
        exclude_spam=exclude_spam,
        exclude_ignored=exclude_ignored,
        limit=limit,
        offset=offset,
        assigned_to=assigned_to,
        customer_id=customer_id,
        current_user_id=ctx.user.id,
        user_permission_slugs=perm_slugs,
        folder_id=folder_id,
        folder_key=folder,
    )


@router.get("/agent-threads/stats")
async def get_thread_stats(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Thread-level stats (visibility-filtered)."""
    perm_slugs = await _get_user_perm_slugs(ctx, db)
    service = AgentThreadService(db)
    return await service.get_thread_stats(org_id=ctx.organization_id, user_id=ctx.user.id, user_permission_slugs=perm_slugs)


@router.get("/agent-threads/{thread_id}")
async def get_thread(
    thread_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Get thread with full conversation timeline. Marks as read for current user."""
    perm_slugs = await _get_user_perm_slugs(ctx, db)
    service = AgentThreadService(db)
    result = await service.get_thread_detail(org_id=ctx.organization_id, thread_id=thread_id, user_permission_slugs=perm_slugs, user_id=ctx.user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Thread not found")
    # Mark as read — admins/owners broadcast to all users
    await service.mark_thread_read(thread_id=thread_id, user_id=ctx.user.id, org_id=ctx.organization_id, user_role=ctx.org_user.role)
    return result


@router.post("/agent-threads/{thread_id}/approve")
async def approve_thread(
    thread_id: str,
    body: ApproveBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Approve the latest pending message in a thread."""
    service = ThreadActionService(db)
    result = await service.approve_thread(
        org_id=ctx.organization_id,
        thread_id=thread_id,
        response_text=body.response_text,
        user_name=f"{ctx.user.first_name} {ctx.user.last_name}",
        attachment_ids=body.attachment_ids,
    )
    if "error" in result:
        code = {"no_pending": 400, "no_text": 400, "send_failed": 500}[result["error"]]
        raise HTTPException(status_code=code, detail=result["detail"])
    thread_svc = AgentThreadService(db)
    await thread_svc.mark_thread_read(thread_id=thread_id, user_id=ctx.user.id, org_id=ctx.organization_id, user_role=ctx.org_user.role)
    await publish(EventType.THREAD_UPDATED, ctx.organization_id, {"thread_id": thread_id, "action": "approved"})
    return result


@router.post("/agent-threads/{thread_id}/dismiss")
async def dismiss_thread(
    thread_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Dismiss all pending messages in a thread."""
    service = ThreadActionService(db)
    result = await service.dismiss_thread(
        org_id=ctx.organization_id,
        thread_id=thread_id,
        user_name=f"{ctx.user.first_name} {ctx.user.last_name}",
    )
    await publish(EventType.THREAD_UPDATED, ctx.organization_id, {"thread_id": thread_id, "action": "dismissed"})
    return result


@router.post("/agent-threads/{thread_id}/archive")
async def archive_thread(
    thread_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Archive a thread — hidden from inbox, preserved for records."""
    service = AgentThreadService(db)
    result = await service.archive_thread(org_id=ctx.organization_id, thread_id=thread_id)
    await publish(EventType.THREAD_UPDATED, ctx.organization_id, {"thread_id": thread_id, "action": "archived"})
    return result


@router.delete("/agent-threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner)),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete a thread and all messages. Owner only."""
    service = AgentThreadService(db)
    result = await service.delete_thread(org_id=ctx.organization_id, thread_id=thread_id)
    await publish(EventType.THREAD_UPDATED, ctx.organization_id, {"thread_id": thread_id, "action": "deleted"})
    return result


@router.post("/agent-threads/{thread_id}/assign")
async def assign_thread(
    thread_id: str,
    body: AssignThreadBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Assign or unassign a thread to a team member."""
    service = AgentThreadService(db)
    result = await service.assign_thread(
        org_id=ctx.organization_id,
        thread_id=thread_id,
        user_id=body.user_id,
        user_name=body.user_name,
    )
    if "error" in result:
        code = {"not_found": 404, "forbidden": 403}[result["error"]]
        raise HTTPException(status_code=code, detail=result["detail"])
    await publish(EventType.THREAD_UPDATED, ctx.organization_id, {"thread_id": thread_id, "action": "assigned", "assigned_to": body.user_id})
    return result


@router.post("/agent-threads/{thread_id}/save-draft")
async def save_thread_draft(
    thread_id: str,
    body: ApproveBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Save edited draft without sending."""
    from sqlalchemy import select, desc
    from src.models.agent_message import AgentMessage
    result = await db.execute(
        select(AgentMessage)
        .where(
            AgentMessage.thread_id == thread_id,
            AgentMessage.organization_id == ctx.organization_id,
            AgentMessage.status == "pending",
            AgentMessage.direction == "inbound",
        )
        .order_by(desc(AgentMessage.received_at))
        .limit(1)
    )
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="No pending message in this thread")
    msg.draft_response = body.response_text
    await db.commit()
    return {"saved": True}


@router.post("/agent-threads/{thread_id}/send-followup")
async def send_thread_followup(
    thread_id: str,
    body: ApproveBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Send a follow-up in a thread."""
    service = ThreadActionService(db)
    result = await service.send_followup(
        org_id=ctx.organization_id,
        thread_id=thread_id,
        text=body.response_text or "",
        user_name=f"{ctx.user.first_name} {ctx.user.last_name}",
        attachment_ids=body.attachment_ids,
    )
    if "error" in result:
        code = {"not_found": 404, "no_text": 400, "send_failed": 500}[result["error"]]
        raise HTTPException(status_code=code, detail=result["detail"])
    thread_svc = AgentThreadService(db)
    await thread_svc.mark_thread_read(thread_id=thread_id, user_id=ctx.user.id, org_id=ctx.organization_id, user_role=ctx.org_user.role)
    await publish(EventType.THREAD_MESSAGE_NEW, ctx.organization_id, {"thread_id": thread_id, "action": "followup_sent"})
    return result


@router.post("/agent-threads/{thread_id}/revise-draft")
async def revise_thread_draft(
    thread_id: str,
    body: ReviseDraftBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Revise the draft on the latest pending message in a thread."""
    service = ThreadAIService(db)
    result = await service.revise_draft(
        org_id=ctx.organization_id,
        thread_id=thread_id,
        draft=body.draft,
        instruction=body.instruction,
    )
    if "error" in result:
        code = {"not_found": 404, "ai_failed": 500}[result["error"]]
        raise HTTPException(status_code=code, detail=result["detail"])
    return result


@router.post("/agent-threads/{thread_id}/draft-followup")
async def draft_thread_followup(
    thread_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Draft a follow-up for a thread using full conversation context."""
    service = ThreadAIService(db)
    result = await service.draft_followup(
        org_id=ctx.organization_id,
        thread_id=thread_id,
    )
    if "error" in result:
        code = {"not_found": 404, "ai_failed": 500}[result["error"]]
        raise HTTPException(status_code=code, detail=result["detail"])
    return result


# ── Thread visibility override ─────────────────────────────────────

class VisibilityBody(BaseModel):
    visibility_permission: Optional[str] = None


@router.patch("/agent-threads/{thread_id}/visibility")
async def update_thread_visibility(
    thread_id: str,
    body: VisibilityBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Admin override: change thread visibility permission."""
    service = AgentThreadService(db)
    result = await service.update_visibility(
        org_id=ctx.organization_id,
        thread_id=thread_id,
        visibility_permission=body.visibility_permission,
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["detail"])
    return result


@router.post("/agent-threads/{thread_id}/create-case")
async def create_case_from_thread(
    thread_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Create a case from a thread (without a job). For tracking situations that don't need field work."""
    from src.models.agent_thread import AgentThread
    from src.services.service_case_service import ServiceCaseService

    thread = (await db.execute(
        select(AgentThread).where(AgentThread.id == thread_id, AgentThread.organization_id == ctx.organization_id)
    )).scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if thread.case_id:
        return {"case_id": thread.case_id, "already_exists": True}

    svc = ServiceCaseService(db)
    case = await svc.find_or_create_case(
        org_id=ctx.organization_id,
        customer_id=thread.matched_customer_id,
        thread_id=thread_id,
        subject=thread.subject or "",
        source="email",
        created_by=f"{ctx.user.first_name} {ctx.user.last_name}",
    )
    thread.case_id = case.id
    await db.commit()
    return {"case_id": case.id, "case_number": case.case_number}


@router.post("/agent-threads/{thread_id}/create-job")
async def create_job_from_thread(
    thread_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """AI creates a job from thread conversation context."""
    service = ThreadAIService(db)
    result = await service.create_job_from_thread(
        org_id=ctx.organization_id,
        thread_id=thread_id,
        created_by=f"{ctx.user.first_name} {ctx.user.last_name}",
    )
    if "error" in result:
        code = {"not_found": 404, "ai_failed": 500}.get(result["error"], 400)
        raise HTTPException(status_code=code, detail=result["detail"])
    return result


@router.post("/agent-threads/{thread_id}/draft-estimate")
async def draft_estimate_from_thread(
    thread_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """AI drafts an estimate from thread conversation context."""
    service = ThreadAIService(db)
    result = await service.draft_estimate_from_thread(
        org_id=ctx.organization_id,
        thread_id=thread_id,
        created_by=f"{ctx.user.first_name} {ctx.user.last_name}",
    )
    if "error" in result:
        code = {"not_found": 404, "ai_failed": 500}.get(result["error"], 400)
        raise HTTPException(status_code=code, detail=result["detail"])
    return result


# ── Contact Learning ──────────────────────────────────────────────────


@router.get("/agent-threads/{thread_id}/contact-prompt")
async def get_contact_prompt(
    thread_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Check if contact learning prompt should show for this thread + return pre-populated data."""
    from src.models.agent_thread import AgentThread
    from src.models.agent_message import AgentMessage
    from src.models.customer import Customer
    from src.models.customer_contact import CustomerContact
    from src.models.organization import Organization
    from src.models.organization_user import OrganizationUser
    from src.utils.phone_parser import extract_phone_from_signature

    thread = (await db.execute(
        select(AgentThread).where(AgentThread.id == thread_id, AgentThread.organization_id == ctx.organization_id)
    )).scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    sender_email = thread.contact_email
    if not sender_email:
        return {"show_prompt": False}

    # Check if sender is already a known contact
    existing_contact = (await db.execute(
        select(CustomerContact).where(
            CustomerContact.organization_id == ctx.organization_id,
            func.lower(CustomerContact.email) == sender_email.lower(),
        ).limit(1)
    )).scalar_one_or_none()
    if existing_contact:
        return {"show_prompt": False}

    # Check if sender is a customer's primary email
    customers = (await db.execute(
        select(Customer).where(
            Customer.organization_id == ctx.organization_id,
            Customer.is_active == True,
            func.lower(Customer.email).contains(sender_email.lower()),
        ).limit(5)
    )).scalars().all()
    for c in customers:
        stored = [e.strip().lower() for e in (c.email or "").split(",")]
        if sender_email.lower() in stored:
            return {"show_prompt": False}

    # Check org setting
    org = (await db.execute(
        select(Organization).where(Organization.id == ctx.organization_id)
    )).scalar_one_or_none()
    learning_mode = org.email_contact_learning if org else True

    # Check org-wide suppressed senders (exact match + domain wildcard)
    from src.models.suppressed_sender import SuppressedEmailSender
    sender_lower = sender_email.lower()
    sender_domain = sender_lower.split("@")[-1] if "@" in sender_lower else ""
    suppressed = (await db.execute(
        select(SuppressedEmailSender).where(
            SuppressedEmailSender.organization_id == ctx.organization_id,
            func.lower(SuppressedEmailSender.email_pattern).in_(
                [sender_lower, f"*@{sender_domain}"] if sender_domain else [sender_lower]
            ),
        ).limit(1)
    )).scalar_one_or_none()
    if suppressed:
        return {"show_prompt": False}

    # Legacy: also check per-user dismissals (backward compat)
    from src.models.organization_user import OrganizationUser
    org_user = (await db.execute(
        select(OrganizationUser).where(
            OrganizationUser.organization_id == ctx.organization_id,
            OrganizationUser.user_id == ctx.user.id,
        )
    )).scalar_one_or_none()
    dismissed = []
    if org_user and org_user.dismissed_sender_emails:
        try:
            dismissed = json.loads(org_user.dismissed_sender_emails)
        except (json.JSONDecodeError, TypeError):
            dismissed = []
    if sender_lower in [d.lower() for d in dismissed]:
        return {"show_prompt": False}

    # Pre-populate contact info from signature block (not email prefix — almost always wrong)
    from src.utils.phone_parser import extract_name_from_signature
    first_name = ""
    last_name = ""
    phone = None

    # Scan all inbound messages in thread for signature data (most recent first)
    inbound_msgs = (await db.execute(
        select(AgentMessage).where(
            AgentMessage.thread_id == thread_id,
            AgentMessage.direction == "inbound",
        ).order_by(desc(AgentMessage.received_at))
    )).scalars().all()
    for msg in inbound_msgs:
        if not msg.body:
            continue
        if not first_name:
            first_name, last_name = extract_name_from_signature(msg.body)
        if not phone:
            phone = extract_phone_from_signature(msg.body)
        if first_name and phone:
            break

    return {
        "show_prompt": True,
        "mode": "modal" if learning_mode else "banner",
        "sender_email": sender_email,
        "suggested_customer_id": thread.matched_customer_id,
        "suggested_customer_name": thread.customer_name,
        "pre_populated": {
            "first_name": first_name,
            "last_name": last_name,
            "email": sender_email,
            "phone": phone,
            "role": "other",
        },
    }


class ContactFromEmailBody(BaseModel):
    customer_id: str
    first_name: str | None = None
    last_name: str | None = None
    email: str
    phone: str | None = None
    role: str = "other"
    receives_estimates: bool = False
    receives_invoices: bool = False
    receives_service_updates: bool = False


@router.post("/agent-threads/{thread_id}/save-contact")
async def save_contact_from_thread(
    thread_id: str,
    body: ContactFromEmailBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Create a customer contact from an email thread sender. Reassign thread if customer changed."""
    from src.models.agent_thread import AgentThread
    from src.models.agent_message import AgentMessage
    from src.models.customer import Customer
    from src.models.customer_contact import CustomerContact
    from src.services.agents.thread_manager import update_thread_status

    thread = (await db.execute(
        select(AgentThread).where(AgentThread.id == thread_id, AgentThread.organization_id == ctx.organization_id)
    )).scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Verify customer belongs to this org
    customer = (await db.execute(
        select(Customer).where(Customer.id == body.customer_id, Customer.organization_id == ctx.organization_id)
    )).scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Check for duplicate contact
    existing = (await db.execute(
        select(CustomerContact).where(
            CustomerContact.customer_id == body.customer_id,
            func.lower(CustomerContact.email) == body.email.lower(),
        ).limit(1)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Contact with this email already exists for this customer")

    # Create contact
    import uuid
    contact = CustomerContact(
        id=str(uuid.uuid4()),
        customer_id=body.customer_id,
        organization_id=ctx.organization_id,
        first_name=body.first_name,
        last_name=body.last_name,
        email=body.email,
        phone=body.phone,
        role=body.role,
        receives_estimates=body.receives_estimates,
        receives_invoices=body.receives_invoices,
        receives_service_updates=body.receives_service_updates,
        is_primary=False,
    )
    db.add(contact)

    # Reassign thread if customer changed
    customer_changed = thread.matched_customer_id != body.customer_id
    if customer_changed:
        from src.models.property import Property
        thread.matched_customer_id = body.customer_id
        thread.customer_name = customer.display_name
        # Update property_address
        prop = (await db.execute(
            select(Property).where(Property.customer_id == body.customer_id, Property.is_active == True).limit(1)
        )).scalar_one_or_none()
        thread.property_address = prop.full_address if prop else None

        # Reassign all messages in thread
        await db.execute(
            select(AgentMessage).where(AgentMessage.thread_id == thread_id)
        )
        msgs = (await db.execute(
            select(AgentMessage).where(AgentMessage.thread_id == thread_id)
        )).scalars().all()
        for msg in msgs:
            msg.matched_customer_id = body.customer_id
            msg.customer_name = customer.display_name
            msg.match_method = "manual_reassign"

    await db.commit()

    if customer_changed:
        await update_thread_status(thread_id)

    return {
        "contact_id": contact.id,
        "customer_changed": customer_changed,
        "customer_name": customer.display_name,
    }


class ContactLearningToggleBody(BaseModel):
    enabled: bool


@router.put("/contact-learning")
async def toggle_contact_learning(
    body: ContactLearningToggleBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Toggle contact learning mode for the organization."""
    from src.models.organization import Organization

    org = (await db.execute(
        select(Organization).where(Organization.id == ctx.organization_id)
    )).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    org.email_contact_learning = body.enabled
    await db.commit()
    return {"email_contact_learning": org.email_contact_learning}


@router.get("/contact-learning")
async def get_contact_learning(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Get contact learning mode setting."""
    from src.models.organization import Organization

    org = (await db.execute(
        select(Organization).where(Organization.id == ctx.organization_id)
    )).scalar_one_or_none()
    return {"email_contact_learning": org.email_contact_learning if org else True}


class DismissContactPromptBody(BaseModel):
    sender_email: str
    reason: str | None = None  # billing, vendor, notification, personal, marketing, other, spam
    folder_id: str | None = None  # auto-move threads from this sender to this folder


@router.post("/agent-threads/dismiss-contact-prompt")
async def dismiss_contact_prompt(
    body: DismissContactPromptBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Suppress contact learning prompt for a sender email — org-wide.

    Adds the sender to suppressed_email_senders so no user in this org
    will see the 'Add Contact' prompt for this address again.
    """
    from src.models.suppressed_sender import SuppressedEmailSender

    email_lower = body.sender_email.lower().strip()

    # Auto-match folder: if no folder_id provided, check if a custom folder
    # exists whose name matches the tag (e.g., tag "billing" → folder "Billing")
    from src.models.inbox_folder import InboxFolder
    target_folder_id = body.folder_id
    tag_reason = body.reason or "other"
    if target_folder_id is None and tag_reason not in ("other", "spam"):
        matching_folder = (await db.execute(
            select(InboxFolder).where(
                InboxFolder.organization_id == ctx.organization_id,
                InboxFolder.is_system == False,  # noqa: E712
                func.lower(InboxFolder.name).in_([
                    tag_reason, tag_reason + "s",  # "billing" or "billings", "vendor" or "vendors"
                ]),
            ).limit(1)
        )).scalar_one_or_none()
        if matching_folder:
            target_folder_id = matching_folder.id

    # Upsert: create or update tag + folder
    existing = (await db.execute(
        select(SuppressedEmailSender).where(
            SuppressedEmailSender.organization_id == ctx.organization_id,
            func.lower(SuppressedEmailSender.email_pattern) == email_lower,
        ).limit(1)
    )).scalar_one_or_none()
    if existing:
        existing.reason = tag_reason
        existing.folder_id = target_folder_id
    else:
        db.add(SuppressedEmailSender(
            organization_id=ctx.organization_id,
            email_pattern=email_lower,
            reason=tag_reason,
            folder_id=target_folder_id,
            created_by=f"{ctx.user.first_name} {ctx.user.last_name}".strip() or ctx.user.email,
        ))
    await db.commit()

    # Move all existing threads from this sender/domain to the chosen folder
    if target_folder_id is not None:
        from src.models.agent_thread import AgentThread
        if email_lower.startswith("*@"):
            # Domain pattern: match all addresses at this domain
            domain_suffix = email_lower[1:]  # "@scppool.com"
            await db.execute(
                AgentThread.__table__.update()
                .where(
                    AgentThread.organization_id == ctx.organization_id,
                    func.lower(AgentThread.contact_email).like(f"%{domain_suffix}"),
                )
                .values(folder_id=target_folder_id)
            )
        else:
            await db.execute(
                AgentThread.__table__.update()
                .where(
                    AgentThread.organization_id == ctx.organization_id,
                    func.lower(AgentThread.contact_email) == email_lower,
                )
                .values(folder_id=target_folder_id)
            )
        await db.commit()

    return {"dismissed": True}


# --- Bulk actions ---

class BulkThreadAction(BaseModel):
    thread_ids: list[str]


@router.post("/agent-threads/bulk/mark-read")
async def bulk_mark_read(
    body: BulkThreadAction,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Mark multiple threads as read for all org users."""
    service = AgentThreadService(db)
    for tid in body.thread_ids:
        await service.mark_thread_read(
            thread_id=tid, user_id=ctx.user.id,
            org_id=ctx.organization_id, user_role=ctx.org_user.role,
        )
    try:
        await publish(EventType.THREAD_UPDATED, ctx.organization_id, {"bulk": True})
    except Exception:
        pass
    return {"ok": True, "count": len(body.thread_ids)}


@router.post("/agent-threads/bulk/mark-unread")
async def bulk_mark_unread(
    body: BulkThreadAction,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Mark multiple threads as unread by clearing read_at for all org users."""
    from src.models.thread_read import ThreadRead
    from src.models.agent_thread import AgentThread
    gmail_thread_ids = []
    for tid in body.thread_ids:
        await db.execute(
            ThreadRead.__table__.delete().where(
                ThreadRead.thread_id == tid,
            )
        )
        # Collect Gmail thread IDs for sync
        t = (await db.execute(
            select(AgentThread.gmail_thread_id).where(AgentThread.id == tid)
        )).scalar_one_or_none()
        if t:
            gmail_thread_ids.append(t)
    await db.commit()

    # Sync unread to Gmail (non-blocking)
    try:
        if gmail_thread_ids:
            from src.models.email_integration import EmailIntegration, IntegrationStatus
            integration = (await db.execute(
                select(EmailIntegration).where(
                    EmailIntegration.organization_id == ctx.organization_id,
                    EmailIntegration.type == "gmail_api",
                    EmailIntegration.status == IntegrationStatus.connected.value,
                    EmailIntegration.is_primary == True,  # noqa: E712
                )
            )).scalar_one_or_none()
            if integration:
                from src.services.gmail.read_sync import sync_read_state
                import asyncio
                for gtid in gmail_thread_ids:
                    asyncio.create_task(sync_read_state(integration, gtid, mark_read=False))
    except Exception:
        pass

    try:
        await publish(EventType.THREAD_UPDATED, ctx.organization_id, {"bulk": True})
    except Exception:
        pass
    return {"ok": True, "count": len(body.thread_ids)}


class BulkMoveAction(BaseModel):
    thread_ids: list[str]
    folder_id: str | None = None  # null = Inbox


@router.post("/agent-threads/bulk/move")
async def bulk_move(
    body: BulkMoveAction,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Move multiple threads to a folder."""
    from src.services.inbox_folder_service import InboxFolderService
    svc = InboxFolderService(db)
    moved = 0
    for tid in body.thread_ids:
        ok = await svc.move_thread(ctx.organization_id, tid, body.folder_id)
        if ok:
            moved += 1
    try:
        await publish(EventType.THREAD_UPDATED, ctx.organization_id, {"bulk": True})
    except Exception:
        pass
    return {"ok": True, "moved": moved}


class AutoSentFeedbackBody(BaseModel):
    thread_id: str
    was_correct: bool


@router.post("/agent-threads/auto-sent-feedback")
async def auto_sent_feedback(
    body: AutoSentFeedbackBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Record human feedback on an auto-sent AI reply. Feeds the agent learning system."""
    from src.models.agent_message import AgentMessage

    # Find the auto-sent message in this thread
    msg = (await db.execute(
        select(AgentMessage).where(
            AgentMessage.thread_id == body.thread_id,
            AgentMessage.organization_id == ctx.organization_id,
            AgentMessage.status == "auto_sent",
        ).order_by(desc(AgentMessage.sent_at)).limit(1)
    )).scalar_one_or_none()
    if not msg:
        raise HTTPException(404, "No auto-sent message found in thread")

    # Record correction via agent learning service
    try:
        from src.services.agents.agent_learning_service import AgentLearningService
        learner = AgentLearningService(db)
        await learner.record_correction(
            organization_id=ctx.organization_id,
            agent_type="email_drafter",
            category=msg.category or "general",
            customer_id=msg.matched_customer_id,
            input_context=f"Subject: {msg.subject}\n\nBody: {(msg.body or '')[:500]}",
            original_output=msg.final_response or msg.draft_response or "",
            corrected_output=None,
            correction_type="acceptance" if body.was_correct else "rejection",
            correction_note="Human reviewed auto-sent reply",
            reviewed_by=f"{ctx.user.first_name} {ctx.user.last_name}".strip() or ctx.user.email,
        )
    except Exception as e:
        logger = __import__("logging").getLogger(__name__)
        logger.warning(f"Failed to record auto-sent feedback: {e}")

    return {"ok": True}


@router.post("/agent-threads/bulk/spam")
async def bulk_spam(
    body: BulkThreadAction,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Mark threads as spam — sender-level: suppresses the sender org-wide
    and moves ALL threads from those senders to the Spam folder."""
    from src.models.agent_thread import AgentThread
    from src.models.inbox_folder import InboxFolder
    from src.models.suppressed_sender import SuppressedEmailSender

    spam_folder = (await db.execute(
        select(InboxFolder.id).where(
            InboxFolder.organization_id == ctx.organization_id,
            InboxFolder.system_key == "spam",
        )
    )).scalar_one_or_none()
    if not spam_folder:
        raise HTTPException(400, "Spam folder not found")

    # Collect unique sender emails from selected threads
    threads = (await db.execute(
        select(AgentThread.contact_email).where(
            AgentThread.id.in_(body.thread_ids),
            AgentThread.organization_id == ctx.organization_id,
        )
    )).scalars().all()
    sender_emails = set(e.lower() for e in threads if e)

    # Suppress each sender org-wide
    for email_addr in sender_emails:
        existing = (await db.execute(
            select(SuppressedEmailSender).where(
                SuppressedEmailSender.organization_id == ctx.organization_id,
                func.lower(SuppressedEmailSender.email_pattern) == email_addr,
            ).limit(1)
        )).scalar_one_or_none()
        if not existing:
            db.add(SuppressedEmailSender(
                organization_id=ctx.organization_id,
                email_pattern=email_addr,
                reason="spam",
                created_by=f"{ctx.user.first_name} {ctx.user.last_name}".strip() or ctx.user.email,
            ))

    # Move ALL threads from those senders to Spam folder
    moved = 0
    if sender_emails:
        result = await db.execute(
            AgentThread.__table__.update()
            .where(
                AgentThread.organization_id == ctx.organization_id,
                func.lower(AgentThread.contact_email).in_(sender_emails),
            )
            .values(folder_id=spam_folder, folder_override=True)
        )
        moved = result.rowcount

    await db.commit()
    try:
        await publish(EventType.THREAD_UPDATED, ctx.organization_id, {"bulk": True})
    except Exception:
        pass
    return {"ok": True, "senders_suppressed": len(sender_emails), "threads_moved": moved}


@router.post("/agent-threads/bulk/not-spam")
async def bulk_not_spam(
    body: BulkThreadAction,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Mark threads as not spam — sender-level: removes suppression and moves
    ALL threads from those senders back to Inbox."""
    from src.models.agent_thread import AgentThread
    from src.models.suppressed_sender import SuppressedEmailSender

    # Collect unique sender emails from selected threads
    threads = (await db.execute(
        select(AgentThread.contact_email).where(
            AgentThread.id.in_(body.thread_ids),
            AgentThread.organization_id == ctx.organization_id,
        )
    )).scalars().all()
    sender_emails = set(e.lower() for e in threads if e)

    # Remove suppression for those senders
    removed = 0
    for email_addr in sender_emails:
        existing = (await db.execute(
            select(SuppressedEmailSender).where(
                SuppressedEmailSender.organization_id == ctx.organization_id,
                func.lower(SuppressedEmailSender.email_pattern) == email_addr,
            )
        )).scalars().all()
        for s in existing:
            await db.delete(s)
            removed += 1

    # Move ALL threads from those senders back to Inbox (NULL folder_id)
    moved = 0
    if sender_emails:
        result = await db.execute(
            AgentThread.__table__.update()
            .where(
                AgentThread.organization_id == ctx.organization_id,
                func.lower(AgentThread.contact_email).in_(sender_emails),
            )
            .values(folder_id=None, folder_override=True)
        )
        moved = result.rowcount

    await db.commit()
    try:
        await publish(EventType.THREAD_UPDATED, ctx.organization_id, {"bulk": True})
    except Exception:
        pass
    return {"ok": True, "senders_unsuppressed": len(sender_emails), "suppressions_removed": removed, "threads_moved": moved}
