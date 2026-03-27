"""Inbox routing rules CRUD — org-level email routing configuration."""

import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.api.deps import OrgUserContext, require_roles
from src.models.organization_user import OrgRole
from src.models.inbox_routing_rule import InboxRoutingRule

router = APIRouter(prefix="/inbox-routing-rules", tags=["inbox-routing"])


# ── Schemas ──────────────────────────────────────────────────────────

class RoutingRuleCreate(BaseModel):
    address_pattern: str = Field(..., min_length=1, max_length=255)
    match_type: str = Field(default="exact", pattern=r"^(exact|contains)$")
    action: str = Field(default="route", pattern=r"^(route|block)$")
    match_field: str = Field(default="to", pattern=r"^(to|from)$")
    category: Optional[str] = None
    required_permission: Optional[str] = None
    priority: int = 0
    is_active: bool = True


class RoutingRuleUpdate(BaseModel):
    address_pattern: Optional[str] = Field(None, min_length=1, max_length=255)
    match_type: Optional[str] = Field(None, pattern=r"^(exact|contains)$")
    action: Optional[str] = Field(None, pattern=r"^(route|block)$")
    match_field: Optional[str] = Field(None, pattern=r"^(to|from)$")
    category: Optional[str] = Field(default=None)
    required_permission: Optional[str] = Field(default=None)
    priority: Optional[int] = None
    is_active: Optional[bool] = None


class RoutingRuleResponse(BaseModel):
    id: str
    address_pattern: str
    match_type: str
    action: str
    match_field: str
    category: str | None
    required_permission: str | None
    priority: int
    is_active: bool
    created_at: str


def _to_response(rule: InboxRoutingRule) -> RoutingRuleResponse:
    return RoutingRuleResponse(
        id=rule.id,
        address_pattern=rule.address_pattern,
        match_type=rule.match_type,
        action=rule.action or "route",
        match_field=rule.match_field or "to",
        category=rule.category,
        required_permission=rule.required_permission,
        priority=rule.priority,
        is_active=rule.is_active,
        created_at=rule.created_at.isoformat() if rule.created_at else "",
    )


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("")
async def list_rules(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """List all routing rules for the organization."""
    result = await db.execute(
        select(InboxRoutingRule)
        .where(InboxRoutingRule.organization_id == ctx.organization_id)
        .order_by(InboxRoutingRule.priority, InboxRoutingRule.created_at)
    )
    return [_to_response(r) for r in result.scalars().all()]


@router.post("", status_code=201)
async def create_rule(
    body: RoutingRuleCreate,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new routing rule."""
    rule = InboxRoutingRule(
        id=str(uuid.uuid4()),
        organization_id=ctx.organization_id,
        address_pattern=body.address_pattern,
        match_type=body.match_type,
        action=body.action,
        match_field=body.match_field,
        category=body.category,
        required_permission=body.required_permission,
        priority=body.priority,
        is_active=body.is_active,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return _to_response(rule)


@router.put("/{rule_id}")
async def update_rule(
    rule_id: str,
    body: RoutingRuleUpdate,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Update a routing rule."""
    result = await db.execute(
        select(InboxRoutingRule).where(
            InboxRoutingRule.id == rule_id,
            InboxRoutingRule.organization_id == ctx.organization_id,
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Routing rule not found")

    if body.address_pattern is not None:
        rule.address_pattern = body.address_pattern
    if body.match_type is not None:
        rule.match_type = body.match_type
    if body.action is not None:
        rule.action = body.action
    if body.match_field is not None:
        rule.match_field = body.match_field
    if body.category is not None:
        rule.category = body.category if body.category else None
    if body.required_permission is not None:
        rule.required_permission = body.required_permission if body.required_permission else None
    if body.priority is not None:
        rule.priority = body.priority
    if body.is_active is not None:
        rule.is_active = body.is_active

    await db.commit()
    await db.refresh(rule)
    return _to_response(rule)


@router.delete("/{rule_id}")
async def delete_rule(
    rule_id: str,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a routing rule."""
    result = await db.execute(
        select(InboxRoutingRule).where(
            InboxRoutingRule.id == rule_id,
            InboxRoutingRule.organization_id == ctx.organization_id,
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Routing rule not found")

    await db.delete(rule)
    await db.commit()
    return {"deleted": True}
