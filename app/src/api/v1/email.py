"""Email compose API — send emails, generate AI drafts, get customer context."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.api.deps import get_current_org_user, OrgUserContext, require_roles
from src.models.organization_user import OrgRole

router = APIRouter(prefix="/email", tags=["email"])


class ComposeRequest(BaseModel):
    to: str
    subject: str
    body: str
    customer_id: Optional[str] = None


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
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail={"error": "send_failed", "message": result.get("error", "Failed to send email")})
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
