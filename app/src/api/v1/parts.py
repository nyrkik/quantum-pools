"""Parts catalog — search, browse, and manage the shared parts database."""

import asyncio
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy import select, or_, func, cast, String
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from src.core.database import get_db
from src.api.deps import get_current_org_user, require_roles, OrgUserContext
from src.models.organization_user import OrgRole
from src.models.parts_catalog import PartsCatalog
from src.models.property import Property
from src.models.water_feature import WaterFeature
from src.services.parts.search_service import PartsSearchService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/parts", tags=["parts"])


@router.get("/search")
async def search_parts(
    q: str = Query("", min_length=0),
    vendor: Optional[str] = None,
    category: Optional[str] = None,
    brand: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Search the parts catalog."""
    svc = PartsSearchService(db)
    return await svc.search(q, vendor_provider=vendor, category=category, brand=brand, limit=limit)


@router.get("/web-search")
async def web_search_parts(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=20),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Search local catalog + web for pool parts. Returns both result sets."""
    from src.services.parts.web_search_agent import PartsWebSearchAgent

    # Local catalog search
    svc = PartsSearchService(db)
    catalog_results = await svc.search(q, limit=limit)

    # Web search (graceful failure)
    agent = PartsWebSearchAgent()
    try:
        web_data = await agent.search(q, max_results=limit)
    except Exception:
        logger.warning(f"Web search failed for '{q}', returning catalog only")
        web_data = {"web_results": [], "cached": False}

    return {
        "catalog_results": catalog_results,
        "web_results": web_data["web_results"],
        "cached": web_data.get("cached", False),
    }


@router.get("/categories")
async def list_categories(
    vendor: Optional[str] = None,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """List available categories."""
    svc = PartsSearchService(db)
    return await svc.get_categories(vendor_provider=vendor)


@router.get("/brands")
async def list_brands(
    vendor: Optional[str] = None,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """List available brands."""
    svc = PartsSearchService(db)
    return await svc.get_brands(vendor_provider=vendor)


@router.get("/stats")
async def catalog_stats(
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get catalog statistics."""
    svc = PartsSearchService(db)
    return await svc.get_stats()


@router.post("/discover")
async def discover_parts_for_org(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Trigger equipment parts discovery for the current org (admin+).

    Scans all equipment models across water features and equipment items,
    discovers replacement parts for any models not yet in the catalog.
    """
    from src.services.parts.equipment_parts_agent import EquipmentPartsAgent

    agent = EquipmentPartsAgent(db)
    result = await agent.discover_parts_for_org(ctx.organization_id)
    return result


@router.post("/discover-model")
async def discover_parts_for_model(
    body: dict,
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner, OrgRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Discover parts for a specific equipment model.

    Body: {"model": "Pentair CCP420", "type": "filter"}
    """
    from src.services.parts.equipment_parts_agent import EquipmentPartsAgent

    model = (body.get("model") or "").strip()
    eq_type = (body.get("type") or "equipment").strip()
    if len(model) < 5:
        raise HTTPException(status_code=400, detail="Model name too short (min 5 chars)")

    agent = EquipmentPartsAgent(db)
    parts = await agent.discover_parts_for_model(model, eq_type)
    return {"model": model, "type": eq_type, "parts_discovered": len(parts), "parts": parts}


@router.get("/customer/{customer_id}")
async def get_customer_parts(
    customer_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get compatible parts grouped by equipment for a customer's water features."""
    # 1. Get all properties for customer (org-scoped)
    prop_result = await db.execute(
        select(Property).where(
            Property.customer_id == customer_id,
            Property.organization_id == ctx.organization_id,
        )
    )
    properties = prop_result.scalars().all()
    if not properties:
        return {"equipment": [], "total_parts": 0, "equipment_without_parts": []}

    prop_ids = [p.id for p in properties]

    # 2. Get all water features for those properties
    wf_result = await db.execute(
        select(WaterFeature).where(WaterFeature.property_id.in_(prop_ids))
    )
    water_features = wf_result.scalars().all()

    # 3. Extract unique equipment models per water feature
    equipment_fields = [
        ("pump", "pump_type"),
        ("filter", "filter_type"),
        ("heater", "heater_type"),
        ("chlorinator", "chlorinator_type"),
        ("automation", "automation_system"),
    ]

    equipment_entries: list[dict] = []
    seen_models: set[str] = set()

    for wf in water_features:
        for eq_type, field in equipment_fields:
            model = getattr(wf, field, None)
            if not model or not model.strip():
                continue
            model = model.strip()
            key = f"{wf.id}:{eq_type}:{model}"
            if key in seen_models:
                continue
            seen_models.add(key)
            equipment_entries.append({
                "water_feature_id": wf.id,
                "water_feature_name": wf.name or wf.water_type.replace("_", " ").title(),
                "property_id": wf.property_id,
                "equipment_type": eq_type,
                "model": model,
            })

    if not equipment_entries:
        return {"equipment": [], "total_parts": 0, "equipment_without_parts": []}

    # 4. For each model, find compatible parts in catalog
    total_parts = 0
    equipment_without_parts: list[str] = []
    results: list[dict] = []

    for entry in equipment_entries:
        model = entry["model"]
        # Normalize for search — extract key terms
        normalized = model.strip().lower()
        # Build search tokens from model string (split on spaces, dashes, slashes)
        import re
        tokens = [t for t in re.split(r'[\s/\-,]+', normalized) if len(t) >= 3]

        # Search compatible_with JSON containment + name/description ILIKE
        conditions = []
        # JSON text containment (handles partial matches)
        conditions.append(
            func.lower(cast(PartsCatalog.compatible_with, String)).contains(normalized)
        )
        # Name/description ILIKE for each significant token
        for token in tokens[:3]:  # limit to first 3 tokens
            conditions.append(PartsCatalog.name.ilike(f"%{token}%"))
        # Also try the full model string
        conditions.append(PartsCatalog.name.ilike(f"%{model}%"))
        conditions.append(PartsCatalog.description.ilike(f"%{model}%"))

        stmt = (
            select(PartsCatalog)
            .where(or_(*conditions))
            .where(PartsCatalog.is_chemical == False)  # noqa: E712
            .order_by(PartsCatalog.category, PartsCatalog.name)
            .limit(20)
        )
        part_result = await db.execute(stmt)
        parts = part_result.scalars().all()

        part_dicts = []
        for p in parts:
            estimated_price = None
            if p.specs and isinstance(p.specs, dict):
                estimated_price = p.specs.get("estimated_price")
            part_dicts.append({
                "id": p.id,
                "name": p.name,
                "sku": p.sku,
                "brand": p.brand,
                "category": p.category,
                "estimated_price": estimated_price,
                "product_url": p.product_url,
                "image_url": p.image_url,
            })

        if part_dicts:
            total_parts += len(part_dicts)
            results.append({**entry, "parts": part_dicts})
        else:
            equipment_without_parts.append(model)
            # Still include the equipment entry with empty parts so frontend can show search
            results.append({**entry, "parts": []})

    return {
        "equipment": results,
        "total_parts": total_parts,
        "equipment_without_parts": equipment_without_parts,
    }


@router.get("/{part_id}")
async def get_part(
    part_id: str,
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single part by ID."""
    svc = PartsSearchService(db)
    part = await svc.get_part(part_id)
    if not part:
        raise HTTPException(status_code=404, detail="Part not found")
    return part


@router.post("/scrape")
async def trigger_scrape(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner)),
    db: AsyncSession = Depends(get_db),
):
    """Trigger SCP catalog scrape (owner only).

    Currently returns info about pool360.com requiring auth.
    Use /parts/seed instead to populate the catalog.
    """
    from src.services.parts.scp_scraper import SCPScraper
    scraper = SCPScraper()
    result = await scraper.scrape_catalog(db)
    return result


@router.post("/seed")
async def seed_catalog(
    ctx: OrgUserContext = Depends(require_roles(OrgRole.owner)),
    db: AsyncSession = Depends(get_db),
):
    """Seed the catalog with common pool parts (owner only). Idempotent."""
    from src.services.parts.seed_catalog import seed_catalog as do_seed
    result = await do_seed(db)
    await db.commit()
    return result
