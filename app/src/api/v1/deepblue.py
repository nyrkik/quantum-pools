"""DeepBlue Field API — streaming AI assistant for field operations."""

import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.api.deps import get_current_org_user, OrgUserContext

router = APIRouter(prefix="/deepblue", tags=["deepblue"])


class MessageRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    case_id: Optional[str] = None
    # Page context — frontend passes these based on current page
    customer_id: Optional[str] = None
    property_id: Optional[str] = None
    bow_id: Optional[str] = None
    visit_id: Optional[str] = None


@router.post("/message")
async def send_message(
    req: MessageRequest,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a message to DeepBlue. Returns SSE stream."""
    from src.services.deepblue.engine import DeepBlueEngine
    from src.services.deepblue.context_builder import DeepBlueContext

    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    engine = DeepBlueEngine(db)
    context = DeepBlueContext(
        customer_id=req.customer_id,
        property_id=req.property_id,
        bow_id=req.bow_id,
        visit_id=req.visit_id,
    )
    user_name = f"{ctx.user.first_name} {ctx.user.last_name}".strip() or "User"

    async def event_generator():
        try:
            async for event in engine.process_message(
                org_id=ctx.organization_id,
                user_id=ctx.user.id,
                user_name=user_name,
                message=req.message,
                context=context,
                conversation_id=req.conversation_id,
                case_id=req.case_id,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.get("/conversations")
async def list_conversations(
    limit: int = 20,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """List recent DeepBlue conversations for the current user."""
    from src.models.deepblue_conversation import DeepBlueConversation

    results = (await db.execute(
        select(DeepBlueConversation)
        .where(
            DeepBlueConversation.user_id == ctx.user.id,
            DeepBlueConversation.organization_id == ctx.organization_id,
        )
        .order_by(desc(DeepBlueConversation.updated_at))
        .limit(limit)
    )).scalars().all()

    return {
        "conversations": [
            {
                "id": c.id,
                "title": c.title,
                "context": json.loads(c.context_json or "{}"),
                "message_count": len(json.loads(c.messages_json or "[]")),
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in results
        ],
    }


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Load a specific conversation with full message history."""
    from src.models.deepblue_conversation import DeepBlueConversation

    conv = (await db.execute(
        select(DeepBlueConversation).where(
            DeepBlueConversation.id == conversation_id,
            DeepBlueConversation.user_id == ctx.user.id,
        )
    )).scalar_one_or_none()

    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {
        "id": conv.id,
        "title": conv.title,
        "case_id": conv.case_id,
        "context": json.loads(conv.context_json or "{}"),
        "messages": json.loads(conv.messages_json or "[]"),
        "tokens": {
            "input": conv.total_input_tokens,
            "output": conv.total_output_tokens,
        },
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
    }


@router.get("/cases/{case_id}/conversations")
async def list_case_conversations(
    case_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """List all DeepBlue conversations attached to a case."""
    from src.models.deepblue_conversation import DeepBlueConversation

    results = (await db.execute(
        select(DeepBlueConversation)
        .where(
            DeepBlueConversation.case_id == case_id,
            DeepBlueConversation.organization_id == ctx.organization_id,
        )
        .order_by(desc(DeepBlueConversation.updated_at))
    )).scalars().all()

    return {
        "conversations": [
            {
                "id": c.id,
                "title": c.title,
                "user_id": c.user_id,
                "message_count": len(json.loads(c.messages_json or "[]")),
                "messages": json.loads(c.messages_json or "[]"),
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in results
        ],
    }


@router.get("/knowledge-gaps")
async def list_knowledge_gaps(
    resolution: Optional[str] = None,
    reviewed: Optional[bool] = None,
    limit: int = 100,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """List DeepBlue knowledge gaps — queries that needed meta-tool or went unresolved."""
    from src.api.deps import OrgRole
    from src.models.deepblue_knowledge_gap import DeepBlueKnowledgeGap

    if ctx.org_user.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Admin only")

    query = select(DeepBlueKnowledgeGap).where(
        DeepBlueKnowledgeGap.organization_id == ctx.organization_id
    )
    if resolution:
        query = query.where(DeepBlueKnowledgeGap.resolution == resolution)
    if reviewed is not None:
        query = query.where(DeepBlueKnowledgeGap.reviewed == reviewed)
    query = query.order_by(desc(DeepBlueKnowledgeGap.created_at)).limit(limit)

    results = (await db.execute(query)).scalars().all()
    return {
        "gaps": [
            {
                "id": g.id,
                "user_question": g.user_question,
                "resolution": g.resolution,
                "sql_query": g.sql_query,
                "reason": g.reason,
                "result_row_count": g.result_row_count,
                "reviewed": g.reviewed,
                "promoted_to_tool": g.promoted_to_tool,
                "created_at": g.created_at.isoformat() if g.created_at else None,
            }
            for g in results
        ],
    }


class MarkReviewedRequest(BaseModel):
    promoted_to_tool: Optional[str] = None


@router.patch("/knowledge-gaps/{gap_id}/review")
async def mark_gap_reviewed(
    gap_id: str,
    req: MarkReviewedRequest,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a knowledge gap as reviewed, optionally recording which tool was built for it."""
    from src.models.deepblue_knowledge_gap import DeepBlueKnowledgeGap

    if ctx.org_user.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Admin only")

    gap = (await db.execute(
        select(DeepBlueKnowledgeGap).where(
            DeepBlueKnowledgeGap.id == gap_id,
            DeepBlueKnowledgeGap.organization_id == ctx.organization_id,
        )
    )).scalar_one_or_none()
    if not gap:
        raise HTTPException(status_code=404, detail="Gap not found")

    gap.reviewed = True
    if req.promoted_to_tool:
        gap.promoted_to_tool = req.promoted_to_tool
    await db.commit()
    return {"reviewed": True}


class ConfirmBroadcastRequest(BaseModel):
    subject: str
    body: str
    filter_type: str = "all_active"


@router.post("/confirm-broadcast")
async def confirm_broadcast(
    req: ConfirmBroadcastRequest,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Confirm and send a broadcast email drafted by DeepBlue."""
    from src.services.broadcast_service import BroadcastService
    from src.api.deps import require_roles, OrgRole

    # Only admin+ can broadcast
    if ctx.org_user.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only admins can send broadcast emails")

    svc = BroadcastService(db)
    broadcast = await svc.create_broadcast(
        org_id=ctx.organization_id,
        subject=req.subject,
        body=req.body,
        filter_type=req.filter_type,
        created_by=f"{ctx.user.first_name} {ctx.user.last_name}",
    )

    return {
        "broadcast_id": broadcast.id,
        "status": broadcast.status,
        "recipient_count": broadcast.recipient_count,
        "sent_count": broadcast.sent_count,
        "failed_count": broadcast.failed_count,
    }


class SaveToCaseRequest(BaseModel):
    case_id: str


@router.patch("/conversations/{conversation_id}/save-to-case")
async def save_conversation_to_case(
    conversation_id: str,
    req: SaveToCaseRequest,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Attach an existing conversation to a case."""
    from src.models.deepblue_conversation import DeepBlueConversation
    from src.models.service_case import ServiceCase

    conv = (await db.execute(
        select(DeepBlueConversation).where(
            DeepBlueConversation.id == conversation_id,
            DeepBlueConversation.organization_id == ctx.organization_id,
        )
    )).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    case = (await db.execute(
        select(ServiceCase).where(
            ServiceCase.id == req.case_id,
            ServiceCase.organization_id == ctx.organization_id,
        )
    )).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    conv.case_id = req.case_id
    await db.commit()

    return {"saved": True, "conversation_id": conv.id, "case_id": req.case_id}
