"""Feedback — in-app user feedback with AI triage."""

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db, get_db_context
from src.api.deps import get_current_org_user, OrgUserContext, require_roles
from src.models.feedback_item import FeedbackItem
from src.models.notification import Notification
from src.models.organization_user import OrgRole

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/feedback", tags=["feedback"])

UPLOAD_DIR = Path("./uploads/feedback")


class FeedbackCreate(BaseModel):
    feedback_type: str  # bug, feature, question
    title: str
    description: Optional[str] = None
    page_url: Optional[str] = None
    browser_info: Optional[str] = None


class FeedbackUpdate(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    resolution_notes: Optional[str] = None


@router.post("", status_code=201)
async def create_feedback(
    feedback_type: str = Form(...),
    title: str = Form(...),
    description: Optional[str] = Form(None),
    page_url: Optional[str] = Form(None),
    browser_info: Optional[str] = Form(None),
    screenshots: list[UploadFile] = File(default=[]),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Create feedback with optional screenshot uploads."""
    feedback_id = str(uuid.uuid4())

    # Save screenshots
    screenshot_urls = []
    if screenshots:
        save_dir = UPLOAD_DIR / feedback_id
        save_dir.mkdir(parents=True, exist_ok=True)
        for i, file in enumerate(screenshots):
            if not file.content_type or not file.content_type.startswith("image/"):
                continue
            ext = file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "jpg"
            filename = f"{i}.{ext}"
            data = await file.read()
            (save_dir / filename).write_bytes(data)
            screenshot_urls.append(f"/uploads/feedback/{feedback_id}/{filename}")

    item = FeedbackItem(
        id=feedback_id,
        organization_id=ctx.organization_id,
        user_id=ctx.user.id,
        user_name=f"{ctx.user.first_name} {ctx.user.last_name}".strip(),
        feedback_type=feedback_type,
        title=title,
        description=description,
        screenshot_urls=screenshot_urls,
        page_url=page_url,
        browser_info=browser_info,
        status="new",
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)

    # AI triage in background
    asyncio.create_task(_ai_triage(feedback_id, ctx.organization_id))

    return {"id": item.id, "status": "new"}


@router.get("")
async def list_feedback(
    status: Optional[str] = Query(None),
    feedback_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """List feedback items (admin only)."""
    q = select(FeedbackItem).where(
        FeedbackItem.organization_id == ctx.organization_id
    ).order_by(desc(FeedbackItem.created_at)).limit(limit)

    if status:
        q = q.where(FeedbackItem.status == status)
    if feedback_type:
        q = q.where(FeedbackItem.feedback_type == feedback_type)

    result = await db.execute(q)
    return [_to_dict(f) for f in result.scalars().all()]


@router.get("/{feedback_id}")
async def get_feedback(
    feedback_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FeedbackItem).where(
            FeedbackItem.id == feedback_id,
            FeedbackItem.organization_id == ctx.organization_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    return _to_dict(item)


@router.put("/{feedback_id}")
async def update_feedback(
    feedback_id: str,
    body: FeedbackUpdate,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FeedbackItem).where(
            FeedbackItem.id == feedback_id,
            FeedbackItem.organization_id == ctx.organization_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")

    if body.status is not None:
        item.status = body.status
        if body.status == "resolved":
            from datetime import datetime, timezone
            item.resolved_at = datetime.now(timezone.utc)
            item.resolved_by = f"{ctx.user.first_name} {ctx.user.last_name}".strip()
    if body.priority is not None:
        item.priority = body.priority
    if body.resolution_notes is not None:
        item.resolution_notes = body.resolution_notes

    await db.commit()
    return _to_dict(item)


async def _ai_triage(feedback_id: str, org_id: str):
    """Background AI triage of feedback."""
    try:
        import anthropic
        from src.core.ai_models import get_model

        async with get_db_context() as db:
            result = await db.execute(
                select(FeedbackItem).where(FeedbackItem.id == feedback_id)
            )
            item = result.scalar_one_or_none()
            if not item:
                return

            # Build prompt
            prompt = f"""Analyze this user feedback from a pool service management app.

Type: {item.feedback_type}
Title: {item.title}
Description: {item.description or 'None'}
Page: {item.page_url or 'Unknown'}
Browser: {item.browser_info or 'Unknown'}
Has screenshots: {len(item.screenshot_urls or []) > 0}

Classify this feedback and return JSON:
{{
  "severity": "critical" | "high" | "medium" | "low",
  "category": "ui" | "functionality" | "performance" | "data" | "integration" | "ux" | "other",
  "is_duplicate_likely": false,
  "suggested_response": "brief helpful response to the user",
  "investigation_notes": "for the dev team — what to look at",
  "can_auto_resolve": false
}}

JSON only."""

            messages = [{"role": "user", "content": prompt}]

            # If screenshots, use Vision
            if item.screenshot_urls:
                content = [{"type": "text", "text": prompt}]
                for url in item.screenshot_urls[:2]:
                    img_path = Path(f"./uploads/feedback/{feedback_id}/{url.split('/')[-1]}")
                    if img_path.exists():
                        import base64
                        img_data = base64.b64encode(img_path.read_bytes()).decode()
                        ext = img_path.suffix.lstrip(".")
                        media = f"image/{ext}" if ext in ("png", "gif", "webp") else "image/jpeg"
                        content.append({
                            "type": "image",
                            "source": {"type": "base64", "media_type": media, "data": img_data},
                        })
                messages = [{"role": "user", "content": content}]

            model_name = await get_model("fast")
            client = anthropic.Anthropic()
            response = client.messages.create(
                model=model_name,
                max_tokens=300,
                messages=messages,
            )

            text = response.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]

            classification = json.loads(text)
            item.ai_classification = classification
            item.ai_response = classification.get("suggested_response")
            item.priority = classification.get("severity", "medium")

            # If critical, notify admins
            if classification.get("severity") == "critical":
                from src.models.organization_user import OrganizationUser
                admins = (await db.execute(
                    select(OrganizationUser).where(
                        OrganizationUser.organization_id == org_id,
                        OrganizationUser.role.in_(("owner", "admin")),
                    )
                )).scalars().all()
                for admin in admins:
                    db.add(Notification(
                        organization_id=org_id,
                        user_id=admin.user_id,
                        type="feedback_critical",
                        title=f"Critical feedback: {item.title[:50]}",
                        body=item.description[:100] if item.description else item.title,
                        link=f"/feedback?id={feedback_id}",
                    ))

            item.status = "triaged"
            await db.commit()
            logger.info(f"Feedback {feedback_id} triaged: {classification.get('severity')} / {classification.get('category')}")

    except Exception as e:
        logger.error(f"AI triage failed for feedback {feedback_id}: {e}")


def _to_dict(f: FeedbackItem) -> dict:
    return {
        "id": f.id,
        "user_name": f.user_name,
        "feedback_type": f.feedback_type,
        "title": f.title,
        "description": f.description,
        "screenshot_urls": f.screenshot_urls or [],
        "page_url": f.page_url,
        "ai_classification": f.ai_classification,
        "ai_response": f.ai_response,
        "status": f.status,
        "priority": f.priority,
        "resolved_by": f.resolved_by,
        "resolved_at": f.resolved_at.isoformat() if f.resolved_at else None,
        "resolution_notes": f.resolution_notes,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }
