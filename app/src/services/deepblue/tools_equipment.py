"""DeepBlue tools — Equipment Oracle domain."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .tools_common import ToolContext, MAX_PARTS_SEARCHES_PER_TURN

logger = logging.getLogger(__name__)


async def _exec_get_equipment(inp: dict, ctx: ToolContext) -> dict:
    """Get equipment installed on a property/water feature."""
    from src.models.equipment_item import EquipmentItem
    from src.models.water_feature import WaterFeature

    bow_id = inp.get("bow_id") or ctx.bow_id
    property_id = inp.get("property_id") or ctx.property_id

    if not bow_id and not property_id:
        return {"error": "No property or body of water in context. Ask which property."}

    query = select(EquipmentItem).options(
        selectinload(EquipmentItem.catalog_equipment)
    ).where(EquipmentItem.is_active == True)

    if bow_id:
        query = query.where(EquipmentItem.water_feature_id == bow_id)
    elif property_id:
        wf_ids = (await ctx.db.execute(
            select(WaterFeature.id).where(WaterFeature.property_id == property_id, WaterFeature.is_active == True)
        )).scalars().all()
        if not wf_ids:
            return {"equipment": [], "message": "No bodies of water found for this property."}
        query = query.where(EquipmentItem.water_feature_id.in_(wf_ids))

    items = (await ctx.db.execute(query)).scalars().all()
    return {
        "equipment": [
            {
                "type": ei.equipment_type,
                "brand": ei.brand,
                "model": ei.model,
                "name": (ei.catalog_equipment.canonical_name if ei.catalog_equipment else
                         ei.normalized_name or f"{ei.brand or ''} {ei.model or ''}".strip()),
                "catalog_id": ei.catalog_equipment_id,
            }
            for ei in items
        ]
    }


async def _exec_find_parts(inp: dict, ctx: ToolContext) -> dict:
    """Find replacement parts for equipment. Checks internal catalog first, falls back to web search.

    Supports two modes:
    - find_parts (default): list of matching parts
    - compare_retailers: same part priced across multiple vendors
    """
    from src.models.parts_catalog import PartsCatalog
    from src.models.equipment_catalog import EquipmentCatalog

    # Per-turn cost guardrail
    if ctx.parts_search_count >= MAX_PARTS_SEARCHES_PER_TURN:
        return {
            "error": f"Parts search limit reached ({MAX_PARTS_SEARCHES_PER_TURN} per turn).",
            "retry_hint": "Use the results from previous searches or ask the user to clarify before searching again.",
        }
    ctx.parts_search_count += 1

    model = (inp.get("equipment_model") or "").strip()
    eq_type = (inp.get("equipment_type") or "").strip()
    part_desc = (inp.get("part_description") or "").strip()
    mode = inp.get("mode", "find_parts")
    max_price = inp.get("max_price")
    limit = min(inp.get("limit", 3), 5)

    if not model or len(model) < 3:
        return {
            "error": "Specific equipment model is required",
            "retry_hint": "Use get_equipment first to look up the installed equipment model. Don't search for generic terms like 'pump'.",
        }

    # Check internal catalog first
    equip = (await ctx.db.execute(
        select(EquipmentCatalog).where(
            EquipmentCatalog.canonical_name.ilike(f"%{model}%"),
        ).limit(3)
    )).scalars().all()

    if not equip:
        first_word = model.split()[0] if model.split() else ""
        if first_word:
            equip = (await ctx.db.execute(
                select(EquipmentCatalog).where(
                    EquipmentCatalog.equipment_type == eq_type,
                    EquipmentCatalog.manufacturer.ilike(f"%{first_word}%"),
                ).limit(5)
            )).scalars().all()

    catalog_parts = []
    equipment_matched = None
    if equip:
        equipment_matched = equip[0].canonical_name
        catalog_ids = [e.id for e in equip]
        parts_query = select(PartsCatalog).where(PartsCatalog.for_equipment_id.in_(catalog_ids))
        if part_desc:
            parts_query = parts_query.where(PartsCatalog.name.ilike(f"%{part_desc}%"))
        parts = (await ctx.db.execute(parts_query.limit(limit * 2))).scalars().all()
        catalog_parts = [
            {
                "name": p.name,
                "sku": p.sku,
                "brand": p.brand,
                "category": p.category,
                "vendor": p.vendor_provider,
                "source": "catalog",
            }
            for p in parts[:limit]
        ]

    # Web search fallback / augmentation
    web_results = []
    if len(catalog_parts) < limit:
        try:
            from src.services.parts.web_search_agent import PartsWebSearchAgent
            agent = PartsWebSearchAgent()

            # Build targeted query
            if mode == "compare_retailers":
                if part_desc:
                    search_query = f"{model} {part_desc} — compare prices across pool supply retailers"
                else:
                    search_query = f"{model} replacement parts — compare prices across pool supply retailers"
            else:
                parts_phrase = part_desc if part_desc else "replacement parts"
                search_query = f"{model} {parts_phrase}"

            if max_price:
                search_query += f" under ${max_price}"

            web_data = await agent.search(search_query, max_results=limit)
            web_results = [
                {
                    "name": r.get("product_name", ""),
                    "price": r.get("price"),
                    "vendor": r.get("vendor_name", ""),
                    "url": r.get("vendor_url", ""),
                    "source": "web_search",
                }
                for r in web_data.get("web_results", [])
            ]

            # Apply max_price filter client-side
            if max_price:
                web_results = [r for r in web_results if r.get("price") is None or r["price"] <= max_price]
        except Exception as e:
            logger.warning(f"Web parts search failed: {e}")

    # Compare mode: structure results as vendor comparison
    if mode == "compare_retailers" and web_results:
        return {
            "mode": "compare_retailers",
            "equipment_matched": equipment_matched,
            "part_searched": part_desc or "replacement parts",
            "vendors": web_results,
            "message": f"Found {len(web_results)} retailer{'s' if len(web_results) != 1 else ''} for {model}",
        }

    return {
        "mode": "find_parts",
        "equipment_matched": equipment_matched,
        "part_searched": part_desc or None,
        "catalog_parts": catalog_parts,
        "web_results": web_results,
        "message": None if (catalog_parts or web_results) else f"No parts found for '{model}'.",
    }


async def _exec_search_catalog(inp: dict, ctx: ToolContext) -> dict:
    """Search equipment catalog."""
    from src.models.equipment_catalog import EquipmentCatalog

    query_str = inp.get("query", "")
    eq_type = inp.get("equipment_type")

    q = select(EquipmentCatalog).where(
        EquipmentCatalog.canonical_name.ilike(f"%{query_str}%"),
    )
    if eq_type:
        q = q.where(EquipmentCatalog.equipment_type == eq_type)
    q = q.limit(10)

    results = (await ctx.db.execute(q)).scalars().all()
    return {
        "results": [
            {
                "id": e.id,
                "name": e.canonical_name,
                "manufacturer": e.manufacturer,
                "type": e.equipment_type,
                "model": getattr(e, "model_number", None),
            }
            for e in results
        ],
    }


async def _exec_add_equipment(inp: dict, ctx: ToolContext) -> dict:
    """Stage an add-equipment proposal. Does NOT save the equipment —
    returns a proposal_id that the user confirms via the UI card,
    which then invokes ProposalService.accept.

    Phase 2 Step 5 dogfood — this is the first live DeepBlue tool on
    the proposals pipeline. Pattern repeats across the other 7 tools
    in steps 8-9.
    """
    from src.models.water_feature import WaterFeature
    from src.models.property import Property
    from src.services.proposals import ProposalService

    bow_id = inp.get("bow_id")
    if not bow_id:
        return {"error": "bow_id required. Use find_property to locate it first."}

    # Scope-check: only propose against a WF that belongs to this org.
    wf = (await ctx.db.execute(
        select(WaterFeature).where(
            WaterFeature.id == bow_id,
            WaterFeature.organization_id == ctx.organization_id,
        )
    )).scalar_one_or_none()
    if not wf:
        return {"error": "Body of water not found. Verify bow_id with find_property."}

    prop = (await ctx.db.execute(
        select(Property).where(Property.id == wf.property_id)
    )).scalar_one_or_none()

    # Stage the proposal. Schema validation runs here — missing fields
    # surface as an error the user sees before clicking confirm.
    try:
        proposal = await ProposalService(ctx.db).stage(
            org_id=ctx.organization_id,
            agent_type="deepblue_responder",
            entity_type="equipment_item",
            source_type="deepblue_conversation",
            source_id=getattr(ctx, "conversation_id", None),
            proposed_payload={
                "water_feature_id": bow_id,
                "equipment_type": inp.get("equipment_type"),
                "brand": inp.get("brand"),
                "model": inp.get("model"),
                "notes": inp.get("notes"),
            },
            confidence=inp.get("confidence"),
        )
        await ctx.db.commit()
    except Exception as e:  # noqa: BLE001
        return {"error": f"Could not stage add-equipment proposal: {e}"}

    return {
        "action": "add_equipment",
        # requires_confirmation retained until Step 8 ships ProposalCard
        # (frontend still keys off this to render the legacy confirm UI).
        "requires_confirmation": True,
        "proposal_id": proposal.id,
        "preview": {
            "bow_id": bow_id,
            "bow_name": wf.name or wf.water_type,
            "property_address": prop.full_address if prop else None,
            "equipment_type": inp.get("equipment_type"),
            "brand": inp.get("brand"),
            "model": inp.get("model"),
            "notes": inp.get("notes"),
            # proposal_id flows through to the ConfirmCard payload and
            # then to the /confirm-add-equipment endpoint.
            "proposal_id": proposal.id,
        },
    }


EXECUTORS = {
    "get_equipment": _exec_get_equipment,
    "find_replacement_parts": _exec_find_parts,
    "search_equipment_catalog": _exec_search_catalog,
    "add_equipment_to_pool": _exec_add_equipment,
}
