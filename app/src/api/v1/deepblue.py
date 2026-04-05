"""DeepBlue Field API — streaming AI assistant for field operations."""

import json
from datetime import datetime, timezone
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
    scope: str = "mine",  # mine | shared | all
    limit: int = 50,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """List DeepBlue conversations. scope: mine | shared | all."""
    from src.models.deepblue_conversation import DeepBlueConversation

    query = select(DeepBlueConversation).where(
        DeepBlueConversation.organization_id == ctx.organization_id,
        DeepBlueConversation.deleted_at.is_(None),
        DeepBlueConversation.case_id.is_(None),  # case-linked chats are in the case UI
    )

    if scope == "mine":
        query = query.where(DeepBlueConversation.user_id == ctx.user.id)
    elif scope == "shared":
        query = query.where(DeepBlueConversation.visibility == "shared")
    elif scope == "all":
        # Admin view — only for owner/admin
        if ctx.org_user.role not in ("owner", "admin"):
            raise HTTPException(status_code=403, detail="Admin only")
    else:
        raise HTTPException(status_code=400, detail="Invalid scope")

    query = query.order_by(
        desc(DeepBlueConversation.pinned),
        desc(DeepBlueConversation.updated_at),
    ).limit(limit)

    results = (await db.execute(query)).scalars().all()

    return {
        "conversations": [
            {
                "id": c.id,
                "title": c.title,
                "user_id": c.user_id,
                "visibility": c.visibility,
                "pinned": c.pinned,
                "context": json.loads(c.context_json or "{}"),
                "message_count": len(json.loads(c.messages_json or "[]")),
                "shared_at": c.shared_at.isoformat() if c.shared_at else None,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in results
        ],
    }


@router.get("/usage-stats")
async def get_usage_stats(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin dashboard data: org totals + per-user breakdown for current month."""
    if ctx.org_user.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Admin only")

    from datetime import date as _date
    from sqlalchemy import func as _func
    from src.models.deepblue_user_usage import DeepBlueUserUsage
    from src.models.user import User
    from src.models.organization import Organization

    from datetime import timedelta as _td
    today = _date.today()
    month_start = today.replace(day=1)
    prev_month_end = month_start - _td(days=1)
    prev_month_start = prev_month_end.replace(day=1)

    org = (await db.execute(select(Organization).where(Organization.id == ctx.organization_id))).scalar_one_or_none()

    # Current month org totals
    current = (await db.execute(
        select(
            _func.coalesce(_func.sum(DeepBlueUserUsage.input_tokens), 0),
            _func.coalesce(_func.sum(DeepBlueUserUsage.output_tokens), 0),
            _func.coalesce(_func.sum(DeepBlueUserUsage.message_count), 0),
            _func.coalesce(_func.sum(DeepBlueUserUsage.off_topic_count), 0),
        ).where(
            DeepBlueUserUsage.organization_id == ctx.organization_id,
            DeepBlueUserUsage.date >= month_start,
        )
    )).one()

    # Previous month for comparison
    previous = (await db.execute(
        select(
            _func.coalesce(_func.sum(DeepBlueUserUsage.input_tokens), 0),
            _func.coalesce(_func.sum(DeepBlueUserUsage.output_tokens), 0),
            _func.coalesce(_func.sum(DeepBlueUserUsage.message_count), 0),
        ).where(
            DeepBlueUserUsage.organization_id == ctx.organization_id,
            DeepBlueUserUsage.date >= prev_month_start,
            DeepBlueUserUsage.date <= prev_month_end,
        )
    )).one()

    # Per-user breakdown current month
    per_user = (await db.execute(
        select(
            DeepBlueUserUsage.user_id,
            _func.coalesce(_func.sum(DeepBlueUserUsage.input_tokens), 0).label("input_tokens"),
            _func.coalesce(_func.sum(DeepBlueUserUsage.output_tokens), 0).label("output_tokens"),
            _func.coalesce(_func.sum(DeepBlueUserUsage.message_count), 0).label("message_count"),
            _func.coalesce(_func.sum(DeepBlueUserUsage.off_topic_count), 0).label("off_topic_count"),
            _func.max(DeepBlueUserUsage.date).label("last_active"),
        ).where(
            DeepBlueUserUsage.organization_id == ctx.organization_id,
            DeepBlueUserUsage.date >= month_start,
        ).group_by(DeepBlueUserUsage.user_id)
    )).all()

    # Resolve user names
    user_ids = [r.user_id for r in per_user]
    users_map = {}
    if user_ids:
        users = (await db.execute(
            select(User).where(User.id.in_(user_ids))
        )).scalars().all()
        users_map = {u.id: f"{u.first_name} {u.last_name}".strip() or u.email for u in users}

    # Cost estimation (Haiku pricing)
    def estimate_cost(inp, out):
        return inp * 0.80 / 1_000_000 + out * 4.00 / 1_000_000

    user_rows = [
        {
            "user_id": r.user_id,
            "name": users_map.get(r.user_id, "Unknown"),
            "message_count": r.message_count,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "estimated_cost_usd": round(estimate_cost(r.input_tokens, r.output_tokens), 4),
            "off_topic_count": r.off_topic_count,
            "off_topic_pct": round(100 * r.off_topic_count / r.message_count, 1) if r.message_count else 0,
            "last_active": r.last_active.isoformat() if r.last_active else None,
        }
        for r in per_user
    ]
    user_rows.sort(key=lambda x: x["input_tokens"] + x["output_tokens"], reverse=True)

    return {
        "current_month": {
            "input_tokens": current[0],
            "output_tokens": current[1],
            "message_count": current[2],
            "off_topic_count": current[3],
            "estimated_cost_usd": round(estimate_cost(current[0], current[1]), 2),
        },
        "previous_month": {
            "input_tokens": previous[0],
            "output_tokens": previous[1],
            "message_count": previous[2],
            "estimated_cost_usd": round(estimate_cost(previous[0], previous[1]), 2),
        },
        "limits": {
            "user_daily_input": org.deepblue_user_daily_input_tokens if org else 500000,
            "user_daily_output": org.deepblue_user_daily_output_tokens if org else 100000,
            "user_monthly_input": org.deepblue_user_monthly_input_tokens if org else 5000000,
            "user_monthly_output": org.deepblue_user_monthly_output_tokens if org else 1000000,
            "org_monthly_input": org.deepblue_org_monthly_input_tokens if org else 50000000,
            "org_monthly_output": org.deepblue_org_monthly_output_tokens if org else 10000000,
            "rate_limit_per_minute": org.deepblue_rate_limit_per_minute if org else 30,
        },
        "users": user_rows,
    }


@router.post("/eval-run")
async def run_eval(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Run the DeepBlue tool-selection eval suite. Owner only."""
    if ctx.org_user.role != "owner":
        raise HTTPException(status_code=403, detail="Owner only")

    import anthropic as _anthropic
    import os as _os
    from src.services.deepblue.eval_prompts import EVAL_PROMPTS
    from src.services.deepblue.tools import TOOLS
    from src.services.deepblue.engine import _build_system_prompt
    from src.services.deepblue.context_builder import DeepBlueContext, build_context
    from src.core.ai_models import get_model

    ANTHROPIC_KEY = _os.environ.get("ANTHROPIC_API_KEY", "")
    if not ANTHROPIC_KEY:
        raise HTTPException(status_code=500, detail="AI not configured")

    # Build minimal context (no customer in view)
    empty_ctx = DeepBlueContext()
    built = await build_context(db, ctx.organization_id, empty_ctx)
    system_prompt = _build_system_prompt(built, "Evaluator")

    client = _anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    model = await get_model("fast")

    results = []
    for p in EVAL_PROMPTS:
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=1024,
                system=system_prompt,
                tools=TOOLS,
                messages=[{"role": "user", "content": p["prompt"]}],
            )
            tools_called = [b.name for b in resp.content if b.type == "tool_use"]
            text_response = " ".join(b.text for b in resp.content if b.type == "text")

            # Evaluate
            passed = True
            reason = ""

            if p.get("expected_off_topic"):
                if "focused on pool" not in text_response.lower() and "i'm here to help" not in text_response.lower():
                    passed = False
                    reason = "Did not decline off-topic request"
            elif p.get("expected_no_tools_required"):
                if tools_called:
                    passed = False
                    reason = f"Called tools when none required: {tools_called}"
            else:
                expected = p.get("expected_tools", [])
                expected_any = p.get("expected_tools_any", [])
                if expected:
                    missing = [t for t in expected if t not in tools_called]
                    if missing:
                        passed = False
                        reason = f"Missing expected tools: {missing}. Called: {tools_called}"
                if expected_any and passed:
                    if not any(t in tools_called for t in expected_any):
                        passed = False
                        reason = f"None of {expected_any} were called. Got: {tools_called}"

            must_not = p.get("must_not_contain", [])
            for phrase in must_not:
                if phrase.lower() in text_response.lower():
                    passed = False
                    reason = f"Response contained forbidden phrase: {phrase}"

            results.append({
                "id": p["id"],
                "prompt": p["prompt"],
                "tools_called": tools_called,
                "text_response": text_response[:300],
                "passed": passed,
                "reason": reason,
            })
        except Exception as e:
            results.append({
                "id": p["id"],
                "prompt": p["prompt"],
                "passed": False,
                "reason": f"Error: {str(e)[:200]}",
            })

    passed_count = sum(1 for r in results if r["passed"])
    return {
        "total": len(results),
        "passed": passed_count,
        "failed": len(results) - passed_count,
        "results": results,
    }


@router.post("/retention/run")
async def run_retention(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Run retention cleanup. Owner only. Can be called by a cron job or manually."""
    if ctx.org_user.role != "owner":
        raise HTTPException(status_code=403, detail="Owner only")
    from src.services.deepblue.retention_service import run_retention_cleanup
    counts = await run_retention_cleanup(db)
    return counts


class ShareRequest(BaseModel):
    visibility: str  # private | shared


@router.patch("/conversations/{conversation_id}/visibility")
async def update_visibility(
    conversation_id: str,
    req: ShareRequest,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    from src.models.deepblue_conversation import DeepBlueConversation
    from datetime import datetime, timezone

    conv = (await db.execute(
        select(DeepBlueConversation).where(
            DeepBlueConversation.id == conversation_id,
            DeepBlueConversation.organization_id == ctx.organization_id,
        )
    )).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Not found")
    if conv.user_id != ctx.user.id:
        raise HTTPException(status_code=403, detail="Only the creator can share this conversation")
    if req.visibility not in ("private", "shared"):
        raise HTTPException(status_code=400, detail="Invalid visibility")

    conv.visibility = req.visibility
    if req.visibility == "shared":
        conv.shared_at = datetime.now(timezone.utc)
        conv.shared_by = ctx.user.id
    else:
        conv.shared_at = None
        conv.shared_by = None
    await db.commit()
    return {"visibility": conv.visibility}


class PinRequest(BaseModel):
    pinned: bool


@router.patch("/conversations/{conversation_id}/pin")
async def update_pin(
    conversation_id: str,
    req: PinRequest,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    from src.models.deepblue_conversation import DeepBlueConversation

    conv = (await db.execute(
        select(DeepBlueConversation).where(
            DeepBlueConversation.id == conversation_id,
            DeepBlueConversation.user_id == ctx.user.id,
        )
    )).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Not found")
    conv.pinned = req.pinned
    await db.commit()
    return {"pinned": conv.pinned}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a conversation. Owner only. Case-linked and shared conversations cannot be deleted."""
    from src.models.deepblue_conversation import DeepBlueConversation
    from datetime import datetime, timezone

    conv = (await db.execute(
        select(DeepBlueConversation).where(
            DeepBlueConversation.id == conversation_id,
            DeepBlueConversation.organization_id == ctx.organization_id,
        )
    )).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Not found")
    if conv.user_id != ctx.user.id:
        raise HTTPException(status_code=403, detail="Only the creator can delete this conversation")
    if conv.case_id:
        raise HTTPException(status_code=400, detail="Case-linked conversations cannot be deleted")

    conv.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return {"deleted": True}


@router.post("/conversations/{conversation_id}/restore")
async def restore_conversation(
    conversation_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    from src.models.deepblue_conversation import DeepBlueConversation

    conv = (await db.execute(
        select(DeepBlueConversation).where(
            DeepBlueConversation.id == conversation_id,
            DeepBlueConversation.user_id == ctx.user.id,
        )
    )).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Not found")
    conv.deleted_at = None
    await db.commit()
    return {"restored": True}


@router.post("/conversations/{conversation_id}/fork")
async def fork_conversation(
    conversation_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Fork a shared conversation into a new private copy for the current user."""
    from src.models.deepblue_conversation import DeepBlueConversation
    import uuid as _uuid

    source = (await db.execute(
        select(DeepBlueConversation).where(
            DeepBlueConversation.id == conversation_id,
            DeepBlueConversation.organization_id == ctx.organization_id,
        )
    )).scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Not found")
    if source.visibility != "shared" and source.user_id != ctx.user.id:
        raise HTTPException(status_code=403, detail="Cannot fork this conversation")

    fork = DeepBlueConversation(
        id=str(_uuid.uuid4()),
        organization_id=ctx.organization_id,
        user_id=ctx.user.id,
        context_json=source.context_json,
        title=f"Fork: {source.title}"[:200] if source.title else "Forked conversation",
        messages_json=source.messages_json,
        visibility="private",
    )
    db.add(fork)
    await db.commit()
    return {"id": fork.id}


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Load a specific conversation. Accessible if: owner, or shared within org, or case-linked."""
    from src.models.deepblue_conversation import DeepBlueConversation

    conv = (await db.execute(
        select(DeepBlueConversation).where(
            DeepBlueConversation.id == conversation_id,
            DeepBlueConversation.organization_id == ctx.organization_id,
        )
    )).scalar_one_or_none()

    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    # Access check
    is_owner = conv.user_id == ctx.user.id
    is_shared = conv.visibility == "shared"
    is_case_linked = conv.case_id is not None
    if not (is_owner or is_shared or is_case_linked):
        raise HTTPException(status_code=403, detail="Not authorized")
    if conv.deleted_at and not is_owner:
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


class ConfirmAddEquipmentRequest(BaseModel):
    bow_id: str
    equipment_type: str
    brand: str
    model: str
    notes: Optional[str] = None


@router.post("/confirm-add-equipment")
async def confirm_add_equipment(
    req: ConfirmAddEquipmentRequest,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Confirm adding equipment to a body of water."""
    import uuid as _uuid
    from src.models.equipment_item import EquipmentItem
    from src.models.water_feature import WaterFeature
    from src.models.property import Property

    # Verify BOW belongs to this org
    wf = (await db.execute(
        select(WaterFeature).where(WaterFeature.id == req.bow_id)
    )).scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="Body of water not found")
    prop = (await db.execute(
        select(Property).where(
            Property.id == wf.property_id,
            Property.organization_id == ctx.organization_id,
        )
    )).scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=403, detail="Not authorized")

    item = EquipmentItem(
        id=str(_uuid.uuid4()),
        water_feature_id=req.bow_id,
        equipment_type=req.equipment_type,
        brand=req.brand,
        model=req.model,
        notes=req.notes,
        is_active=True,
    )
    db.add(item)
    await db.commit()
    return {"equipment_id": item.id, "saved": True}


class ConfirmLogReadingRequest(BaseModel):
    property_id: str
    bow_id: Optional[str] = None
    ph: Optional[float] = None
    free_chlorine: Optional[float] = None
    combined_chlorine: Optional[float] = None
    alkalinity: Optional[int] = None
    calcium_hardness: Optional[int] = None
    cyanuric_acid: Optional[int] = None
    phosphates: Optional[int] = None
    water_temp: Optional[float] = None
    notes: Optional[str] = None


@router.post("/confirm-log-reading")
async def confirm_log_reading(
    req: ConfirmLogReadingRequest,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Confirm logging a chemical reading."""
    import uuid as _uuid
    from src.models.chemical_reading import ChemicalReading
    from src.models.property import Property

    prop = (await db.execute(
        select(Property).where(
            Property.id == req.property_id,
            Property.organization_id == ctx.organization_id,
        )
    )).scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    reading = ChemicalReading(
        id=str(_uuid.uuid4()),
        organization_id=ctx.organization_id,
        property_id=req.property_id,
        water_feature_id=req.bow_id,
        ph=req.ph,
        free_chlorine=req.free_chlorine,
        combined_chlorine=req.combined_chlorine,
        alkalinity=req.alkalinity,
        calcium_hardness=req.calcium_hardness,
        cyanuric_acid=req.cyanuric_acid,
        phosphates=req.phosphates,
        water_temp=req.water_temp,
        notes=req.notes,
    )
    db.add(reading)
    await db.commit()
    return {"reading_id": reading.id, "saved": True}


class ConfirmUpdateNoteRequest(BaseModel):
    customer_id: str
    note_text: str


@router.post("/confirm-update-note")
async def confirm_update_note(
    req: ConfirmUpdateNoteRequest,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Append a note to a customer record."""
    from src.models.customer import Customer

    cust = (await db.execute(
        select(Customer).where(
            Customer.id == req.customer_id,
            Customer.organization_id == ctx.organization_id,
        )
    )).scalar_one_or_none()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")

    current = cust.notes or ""
    cust.notes = (current + "\n\n" + req.note_text).strip() if current else req.note_text
    await db.commit()
    return {"saved": True}


class ConfirmBroadcastRequest(BaseModel):
    subject: str
    body: str
    filter_type: str = "all_active"
    customer_ids: Optional[list[str]] = None
    test_recipient: Optional[str] = None


@router.post("/confirm-broadcast")
async def confirm_broadcast(
    req: ConfirmBroadcastRequest,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Confirm and send a broadcast email drafted by DeepBlue."""
    import json as _json
    from src.services.broadcast_service import BroadcastService

    # Only admin+ can broadcast
    if ctx.org_user.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only admins can send broadcast emails")

    # Default test recipient to current user's email
    test_recipient = req.test_recipient
    if req.filter_type == "test" and not test_recipient:
        test_recipient = ctx.user.email

    filter_data = None
    if req.filter_type == "custom":
        if not req.customer_ids:
            raise HTTPException(status_code=400, detail="customer_ids required for custom filter")
        filter_data = _json.dumps(req.customer_ids)

    svc = BroadcastService(db)
    broadcast = await svc.create_broadcast(
        org_id=ctx.organization_id,
        subject=req.subject,
        body=req.body,
        filter_type=req.filter_type,
        filter_data=filter_data,
        created_by=f"{ctx.user.first_name} {ctx.user.last_name}",
        test_recipient=test_recipient,
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
