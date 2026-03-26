"""Parts catalog — search, browse, and manage the shared parts database."""

import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from src.core.database import get_db
from src.api.deps import get_current_org_user, require_roles, OrgUserContext
from src.models.organization_user import OrgRole
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
