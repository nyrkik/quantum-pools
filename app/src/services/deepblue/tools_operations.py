"""DeepBlue tools — Route Strategist / Operations domain."""

import logging

from sqlalchemy import select, desc

from .tools_common import ToolContext

logger = logging.getLogger(__name__)


async def _exec_service_history(inp: dict, ctx: ToolContext) -> dict:
    """Get recent service visits."""
    from src.models.visit import Visit
    from src.models.tech import Tech

    property_id = inp.get("property_id") or ctx.property_id
    limit = inp.get("limit", 10)

    if not property_id:
        return {"error": "No property in context."}

    visits = (await ctx.db.execute(
        select(Visit).where(Visit.property_id == property_id)
        .order_by(desc(Visit.scheduled_date)).limit(limit)
    )).scalars().all()

    # Batch-resolve tech names
    tech_ids = {v.tech_id for v in visits if v.tech_id}
    tech_map = {}
    if tech_ids:
        techs = (await ctx.db.execute(
            select(Tech).where(Tech.id.in_(tech_ids))
        )).scalars().all()
        tech_map = {t.id: f"{t.first_name} {t.last_name}" for t in techs}

    return {
        "visits": [
            {
                "date": v.scheduled_date.strftime("%Y-%m-%d") if v.scheduled_date else None,
                "tech": tech_map.get(v.tech_id, "Unknown"),
                "duration_minutes": v.duration_minutes,
                "status": v.status,
                "notes": v.notes[:200] if v.notes else None,
            }
            for v in visits
        ],
    }


async def _exec_get_routes_today(inp: dict, ctx: ToolContext) -> dict:
    from datetime import date
    from src.models.route import Route
    from src.models.tech import Tech
    from src.models.property import Property
    from sqlalchemy.orm import selectinload

    # "service_day" is day-of-week name; match today's weekday
    weekday_name = date.today().strftime("%A")

    query = (
        select(Route)
        .options(selectinload(Route.stops))
        .where(
            Route.organization_id == ctx.org_id,
            Route.service_day == weekday_name,
        )
    )
    if inp.get("tech_id"):
        query = query.where(Route.tech_id == inp["tech_id"])

    routes = (await ctx.db.execute(query)).scalars().unique().all()

    # Batch-resolve techs and properties
    tech_ids = {r.tech_id for r in routes if r.tech_id}
    all_prop_ids = set()
    for r in routes:
        for s in r.stops:
            if s.property_id:
                all_prop_ids.add(s.property_id)

    tech_map = {}
    if tech_ids:
        techs = (await ctx.db.execute(select(Tech).where(Tech.id.in_(tech_ids)))).scalars().all()
        tech_map = {t.id: f"{t.first_name} {t.last_name}" for t in techs}

    prop_map = {}
    if all_prop_ids:
        props = (await ctx.db.execute(select(Property).where(Property.id.in_(all_prop_ids)))).scalars().all()
        prop_map = {p.id: p.full_address for p in props}

    result = []
    for r in routes:
        sorted_stops = sorted(r.stops, key=lambda s: s.sequence or 0)
        result.append({
            "tech_name": tech_map.get(r.tech_id, "Unknown"),
            "total_stops": r.total_stops,
            "total_duration_minutes": r.total_duration_minutes,
            "total_distance_miles": r.total_distance_miles,
            "stops": [
                {
                    "sequence": s.sequence,
                    "property": prop_map.get(s.property_id),
                    "eta": str(s.estimated_arrival_time) if s.estimated_arrival_time else None,
                }
                for s in sorted_stops
            ],
        })

    return {"date": weekday_name, "routes": result}


async def _exec_get_techs(inp: dict, ctx: ToolContext) -> dict:
    from src.models.tech import Tech

    rows = (await ctx.db.execute(
        select(Tech).where(Tech.organization_id == ctx.org_id, Tech.is_active == True)
    )).scalars().all()
    return {
        "techs": [
            {
                "id": t.id,
                "name": f"{t.first_name} {t.last_name}",
                "email": t.email,
                "phone": t.phone,
                "hourly_rate": float(t.hourly_rate) if t.hourly_rate else None,
                "job_title": t.job_title,
                "working_days": t.working_days,
                "start_address": t.start_address,
            }
            for t in rows
        ],
    }


async def _exec_get_open_jobs(inp: dict, ctx: ToolContext) -> dict:
    from src.models.agent_action import AgentAction

    query = select(AgentAction).where(AgentAction.organization_id == ctx.org_id)
    cust_id = inp.get("customer_id") or ctx.customer_id
    if cust_id:
        query = query.where(AgentAction.customer_id == cust_id)
    if inp.get("status"):
        query = query.where(AgentAction.status == inp["status"])
    else:
        query = query.where(AgentAction.status.in_(("open", "in_progress", "pending_approval")))
    query = query.order_by(desc(AgentAction.created_at)).limit(inp.get("limit", 20))

    rows = (await ctx.db.execute(query)).scalars().all()
    return {
        "jobs": [
            {
                "id": r.id,
                "type": r.action_type,
                "description": r.description,
                "status": r.status,
                "assigned_to": r.assigned_to,
                "due_date": r.due_date.isoformat() if r.due_date else None,
            }
            for r in rows
        ],
    }


async def _exec_get_cases(inp: dict, ctx: ToolContext) -> dict:
    from src.models.service_case import ServiceCase

    query = select(ServiceCase).where(ServiceCase.organization_id == ctx.org_id)
    cust_id = inp.get("customer_id") or ctx.customer_id
    if cust_id:
        query = query.where(ServiceCase.customer_id == cust_id)
    if inp.get("status"):
        query = query.where(ServiceCase.status == inp["status"])
    query = query.order_by(desc(ServiceCase.updated_at)).limit(inp.get("limit", 10))

    rows = (await ctx.db.execute(query)).scalars().all()
    return {
        "cases": [
            {
                "case_number": r.case_number,
                "title": r.title,
                "status": r.status,
                "priority": r.priority,
                "invoice_count": r.invoice_count,
                "total_invoiced": float(r.total_invoiced or 0),
                "total_paid": float(r.total_paid or 0),
            }
            for r in rows
        ],
    }


async def _exec_get_inspections(inp: dict, ctx: ToolContext) -> dict:
    from src.models.inspection_facility import InspectionFacility
    from src.models.inspection import Inspection
    from src.models.inspection_violation import InspectionViolation

    property_id = inp.get("property_id") or ctx.property_id
    if not property_id:
        return {"error": "No property in context. Specify a property_id."}

    # A property may be matched to multiple facilities (separate pool/spa
    # permits). Pull inspections across all of them.
    facilities = (await ctx.db.execute(
        select(InspectionFacility).where(InspectionFacility.matched_property_id == property_id)
    )).scalars().all()
    if not facilities:
        return {"inspections": [], "message": "This property has no matched inspection facility."}

    facility_ids = [f.id for f in facilities]
    facility_names = {f.id: f.name for f in facilities}
    limit = inp.get("limit", 5)
    inspections = (await ctx.db.execute(
        select(Inspection).where(Inspection.facility_id.in_(facility_ids))
        .order_by(desc(Inspection.inspection_date)).limit(limit)
    )).scalars().all()

    result = []
    for i in inspections:
        violations = (await ctx.db.execute(
            select(InspectionViolation).where(InspectionViolation.inspection_id == i.id)
        )).scalars().all()
        result.append({
            "facility_name": facility_names.get(i.facility_id),
            "date": i.inspection_date.isoformat() if i.inspection_date else None,
            "type": i.inspection_type,
            "inspector": i.inspector_name,
            "total_violations": i.total_violations,
            "major_violations": i.major_violations,
            "closure_status": i.closure_status,
            "closure_required": i.closure_required,
            "reinspection_required": i.reinspection_required,
            "violations": [
                {"description": v.description[:200] if v.description else None, "is_major": v.is_major}
                for v in violations[:10]
            ],
        })

    return {
        "facilities": [
            {
                "name": f.name,
                "address": f"{f.street_address}, {f.city}" if f.street_address else None,
                "permit_holder": f.permit_holder,
                "permit_id": f.facility_id,
            }
            for f in facilities
        ],
        "inspections": result,
    }


async def _exec_create_case(inp: dict, ctx: ToolContext) -> dict:
    """Preview creating a service case. Does NOT save — returns confirmation request."""
    title = (inp.get("title") or "").strip()
    if not title:
        return {"error": "Title is required", "retry_hint": "Provide a brief description of the issue."}

    customer_id = inp.get("customer_id") or ctx.customer_id
    customer_name = None

    from src.models.customer import Customer

    if customer_id:
        cust = (await ctx.db.execute(
            select(Customer).where(Customer.id == customer_id)
        )).scalar_one_or_none()
        if cust:
            customer_name = cust.display_name

    # If no customer resolved, try fuzzy-matching from the title
    if not customer_id:
        try:
            org_id = ctx.org_id
            customers = (await ctx.db.execute(
                select(Customer).where(
                    Customer.organization_id == org_id,
                    Customer.status == "active",
                )
            )).scalars().all()
            title_lower = title.lower()
            best_match = None
            for c in customers:
                # Check display_name, company_name, first+last
                names = [
                    (c.display_name or "").lower(),
                    (c.company_name or "").lower(),
                    f"{(c.first_name or '')} {(c.last_name or '')}".strip().lower(),
                ]
                for name in names:
                    if name and len(name) >= 3 and name in title_lower:
                        # Prefer longest match (more specific)
                        if not best_match or len(name) > len(best_match[1]):
                            best_match = (c, name)
            if best_match:
                customer_id = best_match[0].id
                customer_name = best_match[0].display_name
        except Exception:
            pass  # Non-blocking — customer resolution is best-effort

    priority = inp.get("priority", "normal")

    # Phase 2 Step 9 migration — stage a proposal instead of preview-only.
    from src.services.proposals import ProposalService
    try:
        proposal = await ProposalService(ctx.db).stage(
            org_id=ctx.org_id,
            agent_type="deepblue_responder",
            entity_type="case",
            source_type="deepblue_conversation",
            source_id=getattr(ctx, "conversation_id", None),
            proposed_payload={
                "title": title,
                "customer_id": customer_id,
                "priority": priority,
                "source": "deepblue",
            },
        )
        await ctx.db.commit()
    except Exception as e:  # noqa: BLE001
        return {"error": f"Could not stage create-case proposal: {e}"}

    return {
        "proposal_id": proposal.id,
        "preview": {
            "type": "create_case",
            "title": title,
            "customer_id": customer_id,
            "customer_name": customer_name or "No customer linked",
            "priority": priority,
            "proposal_id": proposal.id,
        },
    }


EXECUTORS = {
    "get_service_history": _exec_service_history,
    "get_routes_today": _exec_get_routes_today,
    "get_techs": _exec_get_techs,
    "get_open_jobs": _exec_get_open_jobs,
    "get_cases": _exec_get_cases,
    "get_inspections": _exec_get_inspections,
    "create_case": _exec_create_case,
}
