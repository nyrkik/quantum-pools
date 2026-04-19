"""DeepBlue tools — Chemistry Advisor domain."""

import logging

from sqlalchemy import select, desc

from .tools_common import ToolContext

logger = logging.getLogger(__name__)


async def _exec_dosing(inp: dict, ctx: ToolContext) -> dict:
    """Deterministic chemical dosing calculator."""
    from src.services.dosing_engine import calculate_dosing
    return calculate_dosing(
        pool_gallons=inp.get("pool_gallons", 15000),
        ph=inp.get("ph"),
        free_chlorine=inp.get("free_chlorine"),
        alkalinity=inp.get("alkalinity"),
        calcium_hardness=inp.get("calcium_hardness"),
        cyanuric_acid=inp.get("cyanuric_acid"),
        combined_chlorine=inp.get("combined_chlorine"),
        phosphates=inp.get("phosphates"),
    )


async def _exec_chemical_history(inp: dict, ctx: ToolContext) -> dict:
    """Get recent chemical readings."""
    from src.models.chemical_reading import ChemicalReading

    bow_id = inp.get("bow_id") or ctx.bow_id
    property_id = inp.get("property_id") or ctx.property_id
    limit = inp.get("limit", 10)

    if not bow_id and not property_id:
        return {"error": "No property or body of water in context."}

    query = select(ChemicalReading).order_by(desc(ChemicalReading.created_at)).limit(limit)
    if bow_id:
        query = query.where(ChemicalReading.water_feature_id == bow_id)
    elif property_id:
        query = query.where(ChemicalReading.property_id == property_id)

    readings = (await ctx.db.execute(query)).scalars().all()
    return {
        "readings": [
            {
                "date": r.created_at.strftime("%Y-%m-%d") if r.created_at else None,
                "ph": r.ph, "free_chlorine": r.free_chlorine,
                "combined_chlorine": r.combined_chlorine,
                "alkalinity": r.alkalinity, "calcium_hardness": r.calcium_hardness,
                "cyanuric_acid": r.cyanuric_acid, "phosphates": r.phosphates,
                "water_temp": r.water_temp,
            }
            for r in readings
        ],
    }


async def _exec_log_reading(inp: dict, ctx: ToolContext) -> dict:
    """Stage a log-chemical-reading proposal. Phase 2 Step 9 migration.

    Same proposal pattern as add_equipment — user confirms via the UI
    card → ProposalService.accept → ChemicalService.create (emits
    chemical_reading.logged + any out-of-range events).
    """
    from src.models.property import Property
    from src.services.proposals import ProposalService

    property_id = inp.get("property_id") or ctx.property_id
    if not property_id:
        return {"error": "property_id required. Use find_property first."}

    # Scope-check: property must belong to this org.
    prop = (await ctx.db.execute(
        select(Property).where(
            Property.id == property_id,
            Property.organization_id == ctx.organization_id,
        )
    )).scalar_one_or_none()
    if not prop:
        return {"error": "Property not found."}

    readings = {
        k: inp[k] for k in (
            "ph", "free_chlorine", "combined_chlorine", "alkalinity",
            "calcium_hardness", "cyanuric_acid", "phosphates", "water_temp",
        ) if inp.get(k) is not None
    }
    if not readings:
        return {"error": "At least one chemical reading must be provided."}

    try:
        proposal = await ProposalService(ctx.db).stage(
            org_id=ctx.organization_id,
            agent_type="deepblue_responder",
            entity_type="chemical_reading",
            source_type="deepblue_conversation",
            source_id=getattr(ctx, "conversation_id", None),
            proposed_payload={
                "property_id": property_id,
                "water_feature_id": inp.get("bow_id"),
                **readings,
                "notes": inp.get("notes"),
            },
        )
        await ctx.db.commit()
    except Exception as e:  # noqa: BLE001
        return {"error": f"Could not stage log-reading proposal: {e}"}

    return {
        "action": "log_reading",
        "proposal_id": proposal.id,
        "preview": {
            "property_id": property_id,
            "bow_id": inp.get("bow_id"),
            "property_address": prop.full_address,
            "readings": readings,
            "notes": inp.get("notes"),
            "proposal_id": proposal.id,
        },
    }


EXECUTORS = {
    "chemical_dosing_calculator": _exec_dosing,
    "get_chemical_history": _exec_chemical_history,
    "log_chemical_reading": _exec_log_reading,
}
