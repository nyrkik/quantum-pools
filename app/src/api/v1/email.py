"""Email compose API — send emails, generate AI drafts, get customer context, canned templates."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete

from src.core.database import get_db
from src.api.deps import get_current_org_user, OrgUserContext, require_roles
from src.models.organization_user import OrgRole
from src.models.email_template import EmailTemplate

router = APIRouter(prefix="/email", tags=["email"])


class ComposeRequest(BaseModel):
    to: str
    subject: str
    body: str
    customer_id: Optional[str] = None
    job_id: Optional[str] = None
    attachment_ids: Optional[list[str]] = None


class DraftRequest(BaseModel):
    instruction: str
    customer_id: Optional[str] = None
    existing_body: Optional[str] = None


@router.post("/compose")
async def compose_email(
    req: ComposeRequest,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Compose and send an email, track in agent threads."""
    from src.services.email_compose_service import EmailComposeService
    svc = EmailComposeService(db)
    result = await svc.compose_and_send(
        org_id=ctx.organization_id,
        to=req.to,
        subject=req.subject,
        body=req.body,
        customer_id=req.customer_id,
        sender_name=f"{ctx.user.first_name} {ctx.user.last_name}",
        sender_user_id=ctx.user.id,
        job_id=req.job_id,
        attachment_ids=req.attachment_ids,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail={"error": "send_failed", "message": result.get("error", "Failed to send email")})
    # Sender's own email should not show as unread
    if result.get("thread_id"):
        from src.services.agent_thread_service import AgentThreadService
        thread_svc = AgentThreadService(db)
        await thread_svc.mark_thread_read(thread_id=result["thread_id"], user_id=ctx.user.id)
    return result


@router.post("/draft")
async def generate_draft(
    req: DraftRequest,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Generate an AI email draft with customer context."""
    from src.services.email_compose_service import EmailComposeService
    svc = EmailComposeService(db)
    return await svc.generate_draft(
        org_id=ctx.organization_id,
        instruction=req.instruction,
        customer_id=req.customer_id,
        existing_body=req.existing_body,
    )


@router.get("/customer-context/{customer_id}")
async def get_customer_context(
    customer_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Get customer context for compose UI and AI drafting."""
    from src.services.email_compose_service import EmailComposeService
    svc = EmailComposeService(db)
    result = await svc.get_customer_context(ctx.organization_id, customer_id)
    if not result:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Customer not found"})
    return result


class DraftCorrectionRequest(BaseModel):
    original_subject: str
    original_body: str
    edited_subject: str
    edited_body: str
    job_id: Optional[str] = None


@router.post("/draft-correction")
async def log_draft_correction(
    req: DraftCorrectionRequest,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin, OrgRole.manager)),
    db: AsyncSession = Depends(get_db),
):
    """Log when a user edits an AI-drafted email before sending. Used to improve future drafts."""
    from src.services.agents.observability import log_agent_call
    await log_agent_call(
        organization_id=ctx.organization_id,
        agent_name="email_drafter",
        action="draft_corrected",
        input_summary=f"Original: {req.original_subject[:80]}",
        output_summary=f"Edited: {req.edited_subject[:80]}",
        success=True,
        extra_data={
            "original_subject": req.original_subject,
            "original_body": req.original_body[:1000],
            "edited_subject": req.edited_subject,
            "edited_body": req.edited_body[:1000],
            "job_id": req.job_id,
            "corrected_by": f"{ctx.user.first_name} {ctx.user.last_name}",
        },
    )
    # Also store as eval case for future model testing
    from src.services.agents.evals import create_eval_from_correction
    await create_eval_from_correction(
        agent_name="email_drafter",
        org_id=ctx.organization_id,
        input_text=f"Subject: {req.original_subject}\n\n{req.original_body}",
        original_output=req.original_body,
        corrected_output=req.edited_body,
        corrected_by=f"{ctx.user.first_name} {ctx.user.last_name}",
    )
    return {"logged": True}


# --- Canned Email Templates ---


class TemplateCreate(BaseModel):
    name: str
    subject: str
    body: str
    category: str = "general"
    sort_order: int = 0


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


@router.get("/templates")
async def list_templates(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """List active canned email templates for compose UI."""
    result = await db.execute(
        select(EmailTemplate)
        .where(EmailTemplate.organization_id == ctx.organization_id, EmailTemplate.is_active == True)
        .order_by(EmailTemplate.category, EmailTemplate.sort_order, EmailTemplate.name)
    )
    templates = result.scalars().all()
    return {
        "items": [
            {
                "id": t.id,
                "name": t.name,
                "subject": t.subject,
                "body": t.body,
                "category": t.category,
                "sort_order": t.sort_order,
            }
            for t in templates
        ]
    }


@router.get("/templates/all")
async def list_all_templates(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """List all templates including inactive (admin management)."""
    result = await db.execute(
        select(EmailTemplate)
        .where(EmailTemplate.organization_id == ctx.organization_id)
        .order_by(EmailTemplate.category, EmailTemplate.sort_order, EmailTemplate.name)
    )
    templates = result.scalars().all()
    return {
        "items": [
            {
                "id": t.id,
                "name": t.name,
                "subject": t.subject,
                "body": t.body,
                "category": t.category,
                "is_active": t.is_active,
                "sort_order": t.sort_order,
            }
            for t in templates
        ]
    }


@router.post("/templates")
async def create_template(
    req: TemplateCreate,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new canned email template."""
    template = EmailTemplate(
        organization_id=ctx.organization_id,
        name=req.name,
        subject=req.subject,
        body=req.body,
        category=req.category,
        sort_order=req.sort_order,
    )
    db.add(template)
    await db.commit()
    return {"id": template.id, "name": template.name}


@router.put("/templates/{template_id}")
async def update_template(
    template_id: str,
    req: TemplateUpdate,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Update a canned email template."""
    result = await db.execute(
        select(EmailTemplate).where(
            EmailTemplate.id == template_id,
            EmailTemplate.organization_id == ctx.organization_id,
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    updates = req.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(template, k, v)
    await db.commit()
    return {"id": template.id, "name": template.name}


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a canned email template."""
    result = await db.execute(
        delete(EmailTemplate).where(
            EmailTemplate.id == template_id,
            EmailTemplate.organization_id == ctx.organization_id,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    await db.commit()
    return {"deleted": True}
