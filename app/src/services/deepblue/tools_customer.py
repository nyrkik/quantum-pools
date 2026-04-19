"""DeepBlue tools — Customer Intelligence domain."""

import logging

from sqlalchemy import select

from .tools_common import ToolContext

logger = logging.getLogger(__name__)


async def _exec_customer_info(inp: dict, ctx: ToolContext) -> dict:
    """Get full customer details."""
    from src.models.customer import Customer
    from src.models.property import Property

    customer_id = inp.get("customer_id") or ctx.customer_id
    if not customer_id:
        return {"error": "No customer in context."}

    cust = (await ctx.db.execute(
        select(Customer).where(Customer.id == customer_id, Customer.organization_id == ctx.org_id)
    )).scalar_one_or_none()
    if not cust:
        return {"error": "Customer not found."}

    props = (await ctx.db.execute(
        select(Property).where(Property.customer_id == customer_id, Property.is_active == True)
    )).scalars().all()

    return {
        "name": cust.display_name,
        "type": cust.customer_type,
        "company": cust.company_name,
        "email": cust.email,
        "phone": cust.phone,
        "monthly_rate": float(cust.monthly_rate) if cust.monthly_rate else None,
        "service_days": cust.preferred_day,
        "status": "active" if cust.is_active else "inactive",
        "properties": [
            {"id": p.id, "name": p.name, "address": p.full_address}
            for p in props
        ],
    }


async def _exec_find_customer(inp: dict, ctx: ToolContext) -> dict:
    """Fuzzy search customers by any text fragment. Falls back to trigram similarity for typos."""
    from sqlalchemy import or_ as _or, text as _text
    from src.models.customer import Customer
    from src.models.property import Property

    query = (inp.get("query") or "").strip()
    if not query:
        return {"error": "Query is required"}
    limit = min(inp.get("limit", 10), 50)
    pattern = f"%{query}%"

    # Search across customer fields (ILIKE)
    cust_result = await ctx.db.execute(
        select(Customer).where(
            Customer.organization_id == ctx.org_id,
            Customer.is_active == True,
            _or(
                Customer.display_name_col.ilike(pattern),
                Customer.company_name.ilike(pattern),
                Customer.first_name.ilike(pattern),
                Customer.last_name.ilike(pattern),
                Customer.email.ilike(pattern),
                Customer.phone.ilike(pattern),
            ),
        ).limit(limit)
    )
    customers = list(cust_result.scalars().all())

    # Also search through properties, then link back to customer
    prop_result = await ctx.db.execute(
        select(Property).where(
            Property.organization_id == ctx.org_id,
            Property.is_active == True,
            _or(
                Property.address.ilike(pattern),
                Property.name.ilike(pattern),
                Property.city.ilike(pattern),
            ),
        ).limit(limit)
    )
    matching_props = prop_result.scalars().all()
    prop_customer_ids = {p.customer_id for p in matching_props if p.customer_id}

    # FALLBACK: if nothing found, try trigram similarity for typo tolerance
    if not customers and not prop_customer_ids:
        sim_result = await ctx.db.execute(_text("""
            SELECT c.id, MAX(GREATEST(
                similarity(lower(c.display_name), lower(:q)),
                similarity(lower(coalesce(c.company_name, '')), lower(:q)),
                similarity(lower(coalesce(p.address, '')), lower(:q)),
                similarity(lower(coalesce(p.name, '')), lower(:q))
            )) AS score
            FROM customers c
            LEFT JOIN properties p ON p.customer_id = c.id
            WHERE c.organization_id = :org_id AND c.is_active = true
              AND (
                similarity(lower(c.display_name), lower(:q)) > 0.3 OR
                similarity(lower(coalesce(c.company_name, '')), lower(:q)) > 0.3 OR
                similarity(lower(coalesce(p.address, '')), lower(:q)) > 0.3 OR
                similarity(lower(coalesce(p.name, '')), lower(:q)) > 0.3
              )
            GROUP BY c.id
            ORDER BY score DESC
            LIMIT :limit
        """), {"org_id": ctx.org_id, "q": query, "limit": limit})
        sim_ids = [row[0] for row in sim_result.fetchall()]
        if sim_ids:
            customers = (await ctx.db.execute(
                select(Customer).where(Customer.id.in_(sim_ids))
            )).scalars().all()

    # Fetch customers matched only via property
    if prop_customer_ids:
        existing_ids = {c.id for c in customers}
        new_ids = prop_customer_ids - existing_ids
        if new_ids:
            extra = (await ctx.db.execute(
                select(Customer).where(Customer.id.in_(new_ids))
            )).scalars().all()
            customers.extend(extra)

    # Build result with first property for context
    results = []
    for c in customers[:limit]:
        prop = (await ctx.db.execute(
            select(Property).where(Property.customer_id == c.id, Property.is_active == True).limit(1)
        )).scalar_one_or_none()
        results.append({
            "customer_id": c.id,
            "name": c.display_name,
            "type": c.customer_type,
            "company": c.company_name,
            "email": c.email,
            "phone": c.phone,
            "primary_address": prop.full_address if prop else None,
        })

    return {"results": results, "count": len(results)}


async def _exec_find_property(inp: dict, ctx: ToolContext) -> dict:
    """Fuzzy search properties by address, name, or city. Falls back to trigram similarity for typos."""
    from sqlalchemy import or_ as _or, text as _text
    from src.models.property import Property
    from src.models.customer import Customer
    from src.models.water_feature import WaterFeature

    query = (inp.get("query") or "").strip()
    if not query:
        return {"error": "Query is required"}
    limit = min(inp.get("limit", 10), 50)
    pattern = f"%{query}%"

    # Join with customers to also match customer name fragments (ILIKE first)
    result = await ctx.db.execute(
        select(Property, Customer)
        .join(Customer, Property.customer_id == Customer.id, isouter=True)
        .where(
            Property.organization_id == ctx.org_id,
            Property.is_active == True,
            _or(
                Property.address.ilike(pattern),
                Property.name.ilike(pattern),
                Property.city.ilike(pattern),
                Property.notes.ilike(pattern),
                Customer.display_name_col.ilike(pattern),
                Customer.company_name.ilike(pattern),
            ),
        ).limit(limit)
    )
    rows = result.all()

    # FALLBACK: trigram similarity for typo tolerance
    if not rows:
        sim_result = await ctx.db.execute(_text("""
            SELECT p.id
            FROM properties p
            LEFT JOIN customers c ON c.id = p.customer_id
            WHERE p.organization_id = :org_id AND p.is_active = true
              AND (
                similarity(lower(coalesce(p.address, '')), lower(:q)) > 0.3 OR
                similarity(lower(coalesce(p.name, '')), lower(:q)) > 0.3 OR
                similarity(lower(coalesce(p.city, '')), lower(:q)) > 0.3 OR
                similarity(lower(coalesce(c.display_name, '')), lower(:q)) > 0.3
              )
            ORDER BY GREATEST(
                similarity(lower(coalesce(p.address, '')), lower(:q)),
                similarity(lower(coalesce(p.name, '')), lower(:q)),
                similarity(lower(coalesce(p.city, '')), lower(:q)),
                similarity(lower(coalesce(c.display_name, '')), lower(:q))
            ) DESC
            LIMIT :limit
        """), {"org_id": ctx.org_id, "q": query, "limit": limit})
        sim_ids = [row[0] for row in sim_result.fetchall()]
        if sim_ids:
            rows = (await ctx.db.execute(
                select(Property, Customer)
                .join(Customer, Property.customer_id == Customer.id, isouter=True)
                .where(Property.id.in_(sim_ids))
            )).all()

    results = []
    for prop, cust in rows:
        # Fetch bodies of water for this property
        wfs = (await ctx.db.execute(
            select(WaterFeature).where(
                WaterFeature.property_id == prop.id,
                WaterFeature.is_active == True,
            )
        )).scalars().all()
        results.append({
            "property_id": prop.id,
            "customer_id": prop.customer_id,
            "customer_name": cust.display_name if cust else None,
            "address": prop.full_address,
            "name": prop.name,
            "city": prop.city,
            "gate_code": prop.gate_code,
            "bodies_of_water": [
                {
                    "id": wf.id,
                    "type": wf.water_type,
                    "name": wf.name,
                    "gallons": wf.pool_gallons,
                }
                for wf in wfs
            ],
        })

    return {"results": results, "count": len(results)}


async def _exec_update_note(inp: dict, ctx: ToolContext) -> dict:
    """Preview appending a note to a customer."""
    from src.models.customer import Customer

    customer_id = inp.get("customer_id") or ctx.customer_id
    if not customer_id:
        return {"error": "customer_id required. Use find_customer first."}

    cust = (await ctx.db.execute(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.organization_id == ctx.org_id,
        )
    )).scalar_one_or_none()
    if not cust:
        return {"error": "Customer not found."}

    note_text = (inp.get("note_text") or "").strip()
    if not note_text:
        return {"error": "note_text required"}

    current = cust.notes or ""
    resulting = (current + "\n\n" + note_text).strip() if current else note_text

    # Phase 2 Step 9 migration — stage a proposal instead of preview-only.
    from src.services.proposals import ProposalService
    try:
        proposal = await ProposalService(ctx.db).stage(
            org_id=ctx.org_id,
            agent_type="deepblue_responder",
            entity_type="customer_note_update",
            source_type="deepblue_conversation",
            source_id=getattr(ctx, "conversation_id", None),
            proposed_payload={
                "customer_id": customer_id,
                "note_text": note_text,
            },
        )
        await ctx.db.commit()
    except Exception as e:  # noqa: BLE001
        return {"error": f"Could not stage note-update proposal: {e}"}

    return {
        "action": "update_note",
        "requires_confirmation": True,  # retained for UI until Step 10
        "proposal_id": proposal.id,
        "preview": {
            "customer_id": customer_id,
            "customer_name": cust.display_name,
            "current_notes": current[:500] if current else None,
            "appending": note_text,
            "resulting_notes_preview": resulting[:800],
            "proposal_id": proposal.id,
        },
    }


EXECUTORS = {
    "get_customer_info": _exec_customer_info,
    "find_customer": _exec_find_customer,
    "find_property": _exec_find_property,
    "update_customer_note": _exec_update_note,
}
