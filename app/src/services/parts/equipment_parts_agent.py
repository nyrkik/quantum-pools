"""Equipment Parts Discovery Agent — discovers replacement parts for installed equipment."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import anthropic
from duckduckgo_search import DDGS
from sqlalchemy import select, or_, func, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.ai_models import get_model
from src.core.config import get_settings
from src.core.redis_client import get_redis
from src.models.parts_catalog import PartsCatalog
from src.models.water_feature import WaterFeature
from src.models.equipment_item import EquipmentItem
from src.models.organization import Organization

logger = logging.getLogger(__name__)

_SEARCH_DELAY = 2.0  # seconds between DuckDuckGo queries
_MIN_MODEL_LEN = 5  # skip vague equipment descriptions
_MAX_PARTS_PER_MODEL = 10
_CACHE_PREFIX = "parts_discovery:"
_CACHE_TTL = 604800  # 7 days

_BLOCKED_DOMAINS = {
    "youtube.com", "reddit.com", "facebook.com", "twitter.com",
    "instagram.com", "tiktok.com", "pinterest.com", "quora.com",
    "wikipedia.org", "wikihow.com",
}

_EXTRACTION_PROMPT = """I need replacement/maintenance parts for this pool equipment:
Equipment: {model}
Type: {equipment_type}

Web search results:
{formatted_results}

Extract a list of REPLACEMENT PARTS (not the equipment itself). For each part:
- name: specific part name (e.g., "Pentair CCP420 Filter Cartridge 4-Pack")
- sku: manufacturer part number if visible (e.g., "160332"), null if not found
- brand: manufacturer name
- category: part category (cartridge, o_ring, seal, motor, impeller, gasket, valve, band_clamp, lid, basket, gauge, lube, rebuild_kit, other)
- estimated_price: price as float if visible, null if not
- compatible_models: list of equipment model strings this part fits

Return ONLY a JSON array (no markdown, no explanation). Only include actual replacement/maintenance parts.
Skip the equipment unit itself, accessories, tools, and unrelated items.
Return at most {max_parts} parts, prioritizing the most commonly needed replacements."""

# Equipment fields on WaterFeature that map to equipment types
_WF_EQUIPMENT_FIELDS = {
    "pump_type": "pump",
    "filter_type": "filter",
    "heater_type": "heater",
    "chlorinator_type": "chlorinator",
    "automation_system": "automation",
}


class EquipmentPartsAgent:
    """Discovers replacement parts for installed pool equipment via web search + Claude extraction."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def discover_parts_for_model(self, equipment_model: str, equipment_type: str) -> list[dict]:
        """Search web for replacement parts for a specific equipment model.

        Returns list of discovered part dicts.
        """
        model = (equipment_model or "").strip()
        if len(model) < _MIN_MODEL_LEN:
            logger.debug(f"Skipping vague model: '{model}'")
            return []

        logger.info(f"Discovering parts for {equipment_type}: {model}")

        # Check Redis cache
        cached = await self._get_cached(model, equipment_type)
        if cached is not None:
            logger.info(f"Cache hit for {model} — {len(cached)} parts")
            # Still upsert cached results in case DB lost them
            await self._upsert_parts(cached, model)
            return cached

        # Search and extract
        try:
            parts = await self._search_and_extract_parts(model, equipment_type)
        except Exception as e:
            logger.error(f"Discovery failed for {model}: {e}")
            return []

        if parts:
            count = await self._upsert_parts(parts, model)
            logger.info(f"Discovered {len(parts)} parts for {model}, upserted {count}")
            await self._set_cached(model, equipment_type, parts)
        else:
            logger.info(f"No parts found for {model}")

        return parts

    async def discover_parts_for_org(self, org_id: str) -> dict:
        """Scan all equipment in an org, discover parts for new/changed models."""
        models = await self._get_unique_equipment_models(org_id)
        logger.info(f"Org {org_id}: found {len(models)} unique equipment models")

        new_models = []
        for m in models:
            has_parts = await self._has_catalog_parts(m["model"])
            if not has_parts:
                new_models.append(m)

        logger.info(f"Org {org_id}: {len(new_models)} models need discovery")

        total_parts = 0
        errors = 0
        for m in new_models:
            try:
                parts = await self.discover_parts_for_model(m["model"], m["type"])
                total_parts += len(parts)
            except Exception as e:
                logger.error(f"Failed discovering parts for {m['model']}: {e}")
                errors += 1
            # Rate limit between models
            if new_models.index(m) < len(new_models) - 1:
                await asyncio.sleep(_SEARCH_DELAY)

        return {
            "models_scanned": len(models),
            "new_models_found": len(new_models),
            "parts_discovered": total_parts,
            "errors": errors,
            "models": [m["model"] for m in new_models],
        }

    async def _get_unique_equipment_models(self, org_id: str) -> list[dict]:
        """Extract unique equipment models from water_features + equipment_items."""
        seen = set()
        results = []

        # Water feature equipment fields
        for field_name, eq_type in _WF_EQUIPMENT_FIELDS.items():
            col = getattr(WaterFeature, field_name)
            stmt = (
                select(func.distinct(col))
                .where(
                    WaterFeature.organization_id == org_id,
                    col.isnot(None),
                    col != "",
                )
            )
            rows = await self.db.execute(stmt)
            for (val,) in rows:
                normalized = val.strip()
                key = normalized.lower()
                if key not in seen and len(normalized) >= _MIN_MODEL_LEN:
                    seen.add(key)
                    results.append({"model": normalized, "type": eq_type, "source": "water_feature"})

        # Equipment items (brand + model)
        stmt = (
            select(EquipmentItem.brand, EquipmentItem.model, EquipmentItem.equipment_type)
            .where(
                EquipmentItem.organization_id == org_id,
                EquipmentItem.is_active.is_(True),
                EquipmentItem.model.isnot(None),
                EquipmentItem.model != "",
            )
            .distinct()
        )
        rows = await self.db.execute(stmt)
        for brand, model, eq_type in rows:
            if not model:
                continue
            # Combine brand + model if brand is present
            full_model = f"{brand} {model}".strip() if brand else model.strip()
            key = full_model.lower()
            if key not in seen and len(full_model) >= _MIN_MODEL_LEN:
                seen.add(key)
                results.append({"model": full_model, "type": eq_type or "equipment", "source": "equipment_item"})

        return results

    async def _has_catalog_parts(self, model: str) -> bool:
        """Check if parts_catalog already has entries compatible with this model."""
        normalized = model.strip().lower()
        # Check compatible_with JSON field (PostgreSQL JSON containment)
        # Also check if name/description mentions the model
        stmt = select(func.count(PartsCatalog.id)).where(
            or_(
                func.lower(cast(PartsCatalog.compatible_with, String)).contains(normalized),
                PartsCatalog.name.ilike(f"%{normalized}%"),
            )
        )
        result = await self.db.execute(stmt)
        count = result.scalar() or 0
        return count > 0

    async def _search_and_extract_parts(self, model: str, equipment_type: str) -> list[dict]:
        """Use Claude's knowledge to identify replacement parts, then verify with web search."""
        settings = get_settings()
        if not settings.anthropic_api_key:
            logger.warning("No Anthropic API key — cannot discover parts")
            return []

        ai_model = await get_model("fast")
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        # Step 1: Ask Claude directly — it knows pool equipment parts from training data
        knowledge_prompt = f"""List the common replacement and maintenance parts for this pool equipment:

Equipment: {model}
Type: {equipment_type}

For each part provide:
- name: specific part name including brand and model compatibility
- sku: manufacturer part number (if you know it, otherwise null)
- brand: manufacturer name
- category: part type (cartridge, grid, o_ring, seal, gasket, motor, impeller, valve, clamp, band, basket, gauge, switch, board, element, other)
- estimated_price: typical retail price in USD (your best estimate, or null)
- compatible_models: list of equipment model numbers this part fits (include "{model}" and any known compatible models)

Return ONLY a JSON array. Maximum {_MAX_PARTS_PER_MODEL} parts. Focus on the most commonly replaced items.
Include: filter media/cartridges, o-rings, seals, gaskets, valves, clamps, motors, impellers, baskets, gauges.
Exclude: the equipment unit itself, tools, chemicals, accessories."""

        try:
            response = await client.messages.create(
                model=ai_model,
                max_tokens=2048,
                messages=[{"role": "user", "content": knowledge_prompt}],
            )
            text = response.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()

            parts = json.loads(text)
            if not isinstance(parts, list):
                logger.warning(f"Expected list, got {type(parts)}")
                return []

            cleaned = []
            for p in parts:
                if not isinstance(p, dict):
                    continue
                name = str(p.get("name", "")).strip()
                if not name:
                    continue
                cleaned.append({
                    "name": name,
                    "sku": str(p["sku"]).strip() if p.get("sku") else None,
                    "brand": str(p.get("brand", "")).strip() or None,
                    "category": str(p.get("category", "other")).strip(),
                    "estimated_price": float(p["estimated_price"]) if p.get("estimated_price") is not None else None,
                    "compatible_models": p.get("compatible_models", [model]),
                })

            logger.info(f"Claude identified {len(cleaned)} parts for {model}")
            return cleaned[:_MAX_PARTS_PER_MODEL]

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse parts response for {model}: {e}")
            return []
        except Exception as e:
            logger.error(f"Parts discovery error for {model}: {e}")
            return []

    def _web_search(self, query: str, max_results: int = 10) -> list[dict]:
        """Execute DuckDuckGo search, return raw results. Synchronous."""
        results = []
        try:
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    href = r.get("href", "")
                    if any(d in href for d in _BLOCKED_DOMAINS):
                        continue
                    if href.lower().endswith(".pdf"):
                        continue
                    results.append({
                        "title": r.get("title", ""),
                        "snippet": r.get("body", ""),
                        "url": href,
                    })
        except Exception as e:
            logger.error(f"DuckDuckGo search error: {e}")
            raise
        return results

    async def _upsert_parts(self, parts: list[dict], source_model: str) -> int:
        """Upsert parts into catalog. Update compatible_with to include source_model."""
        count = 0
        for p in parts:
            sku = p.get("sku")
            if not sku:
                # Generate a deterministic SKU from name
                import hashlib
                sku = f"AUTO-{hashlib.md5(p['name'].lower().encode()).hexdigest()[:8].upper()}"

            # Check if exists by SKU + vendor
            vendor = "discovery"
            stmt = select(PartsCatalog).where(
                PartsCatalog.vendor_provider == vendor,
                PartsCatalog.sku == sku,
            )
            result = await self.db.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                # Update compatible_with to include source_model
                compat = existing.compatible_with or []
                if isinstance(compat, str):
                    try:
                        compat = json.loads(compat)
                    except (json.JSONDecodeError, TypeError):
                        compat = []
                if source_model not in compat:
                    compat.append(source_model)
                    existing.compatible_with = compat
                    existing.last_scraped_at = datetime.now(timezone.utc)
            else:
                # Create new entry
                compat = list(set(p.get("compatible_models", [source_model])))
                if source_model not in compat:
                    compat.append(source_model)
                part = PartsCatalog(
                    vendor_provider=vendor,
                    sku=sku,
                    name=p["name"],
                    brand=p.get("brand"),
                    category=p.get("category"),
                    compatible_with=compat,
                    last_scraped_at=datetime.now(timezone.utc),
                )
                self.db.add(part)
                count += 1

        await self.db.commit()
        return count

    # --- Redis caching ---

    async def _get_cached(self, model: str, equipment_type: str) -> Optional[list[dict]]:
        redis = await get_redis()
        if not redis:
            return None
        try:
            key = self._cache_key(model, equipment_type)
            data = await redis.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.debug(f"Cache read error: {e}")
        return None

    async def _set_cached(self, model: str, equipment_type: str, parts: list[dict]) -> None:
        redis = await get_redis()
        if not redis:
            return
        try:
            key = self._cache_key(model, equipment_type)
            await redis.set(key, json.dumps(parts), ex=_CACHE_TTL)
        except Exception as e:
            logger.debug(f"Cache write error: {e}")

    @staticmethod
    def _cache_key(model: str, equipment_type: str) -> str:
        import hashlib
        normalized = f"{model.strip().lower()}:{equipment_type.strip().lower()}"
        h = hashlib.md5(normalized.encode()).hexdigest()[:12]
        return f"{_CACHE_PREFIX}{h}"
