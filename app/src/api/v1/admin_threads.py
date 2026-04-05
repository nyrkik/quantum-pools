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
from src.api.deps import OrgUserContext, require_roles, OrgRole
from src.schemas.agent_thread import ApproveBody, ReviseDraftBody, AssignThreadBody
from src.services.agent_thread_service import AgentThreadService

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
    result = await service.get_thread_detail(org_id=ctx.organization_id, thread_id=thread_id, user_permission_slugs=perm_slugs)
    if not result:
        raise HTTPException(status_code=404, detail="Thread not found")
    # Mark as read when viewing
    await service.mark_thread_read(thread_id=thread_id, user_id=ctx.user.id)
    return result


@router.post("/agent-threads/{thread_id}/approve")
async def approve_thread(
    thread_id: str,
    body: ApproveBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Approve the latest pending message in a thread."""
    service = AgentThreadService(db)
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
    # Sender's own reply should not show as unread
    await service.mark_thread_read(thread_id=thread_id, user_id=ctx.user.id)
    return result


@router.post("/agent-threads/{thread_id}/dismiss")
async def dismiss_thread(
    thread_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Dismiss all pending messages in a thread."""
    service = AgentThreadService(db)
    return await service.dismiss_thread(
        org_id=ctx.organization_id,
        thread_id=thread_id,
        user_name=f"{ctx.user.first_name} {ctx.user.last_name}",
    )


@router.post("/agent-threads/{thread_id}/archive")
async def archive_thread(
    thread_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Archive a thread — hidden from inbox, preserved for records."""
    service = AgentThreadService(db)
    return await service.archive_thread(org_id=ctx.organization_id, thread_id=thread_id)


@router.delete("/agent-threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner)),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete a thread and all messages. Owner only."""
    service = AgentThreadService(db)
    return await service.delete_thread(org_id=ctx.organization_id, thread_id=thread_id)


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
    service = AgentThreadService(db)
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
    # Sender's own reply should not show as unread
    await service.mark_thread_read(thread_id=thread_id, user_id=ctx.user.id)
    return result


@router.post("/agent-threads/{thread_id}/revise-draft")
async def revise_thread_draft(
    thread_id: str,
    body: ReviseDraftBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Revise the draft on the latest pending message in a thread."""
    service = AgentThreadService(db)
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
    service = AgentThreadService(db)
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
    service = AgentThreadService(db)
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
    service = AgentThreadService(db)
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

    # Check if this user dismissed this sender
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
    if sender_email.lower() in [d.lower() for d in dismissed]:
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


@router.post("/agent-threads/dismiss-contact-prompt")
async def dismiss_contact_prompt(
    body: DismissContactPromptBody,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Dismiss contact learning prompt for a sender email (per-user)."""
    from src.models.organization_user import OrganizationUser

    org_user = (await db.execute(
        select(OrganizationUser).where(
            OrganizationUser.organization_id == ctx.organization_id,
            OrganizationUser.user_id == ctx.user.id,
        )
    )).scalar_one_or_none()
    if not org_user:
        raise HTTPException(status_code=404, detail="User not found in organization")

    dismissed = []
    try:
        dismissed = json.loads(org_user.dismissed_sender_emails or "[]")
    except (json.JSONDecodeError, TypeError):
        dismissed = []

    email_lower = body.sender_email.lower()
    if email_lower not in [d.lower() for d in dismissed]:
        dismissed.append(email_lower)
        org_user.dismissed_sender_emails = json.dumps(dismissed)
        await db.commit()

    return {"dismissed": True}
