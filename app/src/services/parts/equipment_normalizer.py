"""Equipment Normalizer — AI-powered parsing of free-text equipment descriptions into structured data."""

import hashlib
import json
import logging
from typing import Optional

import anthropic
from sqlalchemy import select, func, String, cast
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.ai_models import get_model
from src.core.config import get_settings
from src.core.redis_client import get_redis
from src.models.equipment_item import EquipmentItem

logger = logging.getLogger(__name__)

_CACHE_PREFIX = "equip_norm:"

_NORMALIZE_PROMPT = """Parse this pool equipment description into structured fields.

Equipment type: {equipment_type}
Raw text: "{raw_text}"

Extract:
- brand: manufacturer name (Pentair, Hayward, Jandy/Zodiac, Sta-Rite, Waterway, Raypak, etc.)
- model: model name/series (IntelliFlo VS+SVRS, WhisperFlo, TriStar, Pro-Grid DE, etc.)
- part_number: manufacturer part/model number if present (011056, SP3020EEAZ, S8M150, etc.)
- horsepower: HP rating if present (float)
- flow_rate_gpm: flow rate in GPM if present (int)
- voltage: voltage if present (115, 230, etc.)
- normalized_name: clean standardized name "{{Brand}} {{Model}} {{HP}}HP" (no flow rates, no parenthetical specs)

Return JSON object only. Use null for fields not present in the text.
Standardize brand capitalization (Pentair not PENTAIR, Hayward not HAYWARD, Sta-Rite not STA-RITE).
Standardize model names (IntelliFlo not Intelliflo, WhisperFlo not Whisperflo).
Do not include any explanation, just the JSON object."""


class EquipmentNormalizer:
    """Normalizes free-text equipment descriptions into structured data."""

    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db

    async def normalize(self, raw_text: str, equipment_type: str = "equipment") -> dict:
        """Parse raw equipment text into structured fields.

        Uses Claude Haiku for parsing. Cached permanently in Redis.
        Returns dict with: brand, model, part_number, horsepower, flow_rate_gpm,
                          voltage, normalized_name
        """
        if not raw_text or not raw_text.strip():
            return self._empty_result()

        raw_text = raw_text.strip()

        # Check Redis cache (permanent — equipment model names don't change)
        cache_key = self._cache_key(raw_text, equipment_type)
        redis = await get_redis()
        if redis:
            try:
                cached = await redis.get(cache_key)
                if cached:
                    return json.loads(cached)
            except Exception:
                pass

        # Call Claude Haiku
        result = await self._call_ai(raw_text, equipment_type)

        # Cache permanently
        if redis and result.get("normalized_name"):
            try:
                await redis.set(cache_key, json.dumps(result))
            except Exception:
                pass

        return result

    async def find_matching_models(self, normalized: dict, org_id: str) -> list[dict]:
        """Find existing equipment in the org that matches this normalized model."""
        if not self.db or not normalized.get("normalized_name"):
            return []

        brand = normalized.get("brand")
        model = normalized.get("model")

        conditions = []
        if brand:
            conditions.append(EquipmentItem.brand == brand)
        if model:
            conditions.append(EquipmentItem.model == model)

        if not conditions:
            return []

        stmt = (
            select(EquipmentItem)
            .where(
                EquipmentItem.organization_id == org_id,
                EquipmentItem.is_active == True,
                *conditions,
            )
            .limit(10)
        )
        result = await self.db.execute(stmt)
        items = result.scalars().all()
        return [
            {
                "id": item.id,
                "equipment_type": item.equipment_type,
                "brand": item.brand,
                "model": item.model,
                "normalized_name": item.normalized_name,
            }
            for item in items
        ]

    async def get_known_models(
        self, org_id: str, equipment_type: str, query: str = ""
    ) -> list[dict]:
        """Get unique normalized models in the org for autocomplete.

        Returns [{normalized_name, brand, model, part_number, count}] sorted by count desc.
        """
        if not self.db:
            return []

        stmt = (
            select(
                EquipmentItem.normalized_name,
                EquipmentItem.brand,
                EquipmentItem.model,
                EquipmentItem.part_number,
                func.count().label("count"),
            )
            .where(
                EquipmentItem.organization_id == org_id,
                EquipmentItem.equipment_type == equipment_type,
                EquipmentItem.is_active == True,
                EquipmentItem.normalized_name.isnot(None),
            )
            .group_by(
                EquipmentItem.normalized_name,
                EquipmentItem.brand,
                EquipmentItem.model,
                EquipmentItem.part_number,
            )
            .order_by(func.count().desc())
        )

        if query and len(query) >= 3:
            stmt = stmt.where(
                EquipmentItem.normalized_name.ilike(f"%{query}%")
            )

        stmt = stmt.limit(20)
        result = await self.db.execute(stmt)
        rows = result.all()
        return [
            {
                "normalized_name": row.normalized_name,
                "brand": row.brand,
                "model": row.model,
                "part_number": row.part_number,
                "count": row.count,
            }
            for row in rows
        ]

    async def upsert_equipment_item(
        self,
        org_id: str,
        water_feature_id: str,
        equipment_type: str,
        raw_text: str,
        normalized: dict,
    ) -> Optional[EquipmentItem]:
        """Create or update an equipment_item from normalized data.

        Finds existing by (water_feature_id, equipment_type) and updates,
        or creates a new record.
        """
        if not self.db or not raw_text or not raw_text.strip():
            return None

        # Find existing
        stmt = select(EquipmentItem).where(
            EquipmentItem.water_feature_id == water_feature_id,
            EquipmentItem.equipment_type == equipment_type,
            EquipmentItem.is_active == True,
        )
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()

        brand = normalized.get("brand")
        model = normalized.get("model")
        part_number = normalized.get("part_number")
        normalized_name = normalized.get("normalized_name")
        horsepower = normalized.get("horsepower")
        flow_rate_gpm = normalized.get("flow_rate_gpm")
        voltage = normalized.get("voltage")

        if existing:
            existing.brand = brand
            existing.model = model
            existing.part_number = part_number
            existing.normalized_name = normalized_name
            existing.horsepower = horsepower
            existing.flow_rate_gpm = flow_rate_gpm
            existing.voltage = voltage
            await self.db.flush()
            return existing

        import uuid

        item = EquipmentItem(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            water_feature_id=water_feature_id,
            equipment_type=equipment_type,
            brand=brand,
            model=model,
            part_number=part_number,
            normalized_name=normalized_name,
            horsepower=horsepower,
            flow_rate_gpm=flow_rate_gpm,
            voltage=voltage,
        )
        self.db.add(item)
        await self.db.flush()
        return item

    async def _call_ai(self, raw_text: str, equipment_type: str) -> dict:
        """Call Claude Haiku to normalize equipment text."""
        settings = get_settings()
        if not settings.anthropic_api_key:
            logger.warning("No Anthropic API key — skipping AI normalization")
            return self._fallback_parse(raw_text)

        try:
            model_id = await get_model("fast")
            client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            prompt = _NORMALIZE_PROMPT.format(
                equipment_type=equipment_type,
                raw_text=raw_text,
            )

            response = await client.messages.create(
                model=model_id,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.content[0].text.strip()
            # Strip markdown code fences if present
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()

            result = json.loads(text)
            # Validate expected fields
            return {
                "brand": result.get("brand"),
                "model": result.get("model"),
                "part_number": result.get("part_number"),
                "horsepower": self._to_float(result.get("horsepower")),
                "flow_rate_gpm": self._to_int(result.get("flow_rate_gpm")),
                "voltage": self._to_int(result.get("voltage")),
                "normalized_name": result.get("normalized_name"),
            }
        except Exception as e:
            logger.error(f"AI normalization failed for '{raw_text}': {e}")
            return self._fallback_parse(raw_text)

    def _fallback_parse(self, raw_text: str) -> dict:
        """Basic regex fallback when AI is unavailable."""
        import re

        text = raw_text.strip()
        brand = None
        known_brands = {
            "pentair": "Pentair",
            "hayward": "Hayward",
            "jandy": "Jandy",
            "zodiac": "Zodiac",
            "sta-rite": "Sta-Rite",
            "starite": "Sta-Rite",
            "waterway": "Waterway",
            "raypak": "Raypak",
            "polaris": "Polaris",
            "kreepy krauly": "Kreepy Krauly",
            "aquacal": "AquaCal",
            "jacuzzi": "Jacuzzi",
        }
        text_lower = text.lower()
        for key, val in known_brands.items():
            if key in text_lower:
                brand = val
                break

        hp_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:hp|HP)", text)
        gpm_match = re.search(r"(\d+)\s*(?:gpm|GPM)", text, re.IGNORECASE)

        return {
            "brand": brand,
            "model": None,
            "part_number": None,
            "horsepower": float(hp_match.group(1)) if hp_match else None,
            "flow_rate_gpm": int(gpm_match.group(1)) if gpm_match else None,
            "voltage": None,
            "normalized_name": text,
        }

    @staticmethod
    def _empty_result() -> dict:
        return {
            "brand": None,
            "model": None,
            "part_number": None,
            "horsepower": None,
            "flow_rate_gpm": None,
            "voltage": None,
            "normalized_name": None,
        }

    @staticmethod
    def _cache_key(raw_text: str, equipment_type: str) -> str:
        h = hashlib.md5(f"{equipment_type}:{raw_text.strip().lower()}".encode()).hexdigest()
        return f"{_CACHE_PREFIX}{h}"

    @staticmethod
    def _to_float(v) -> Optional[float]:
        if v is None:
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _to_int(v) -> Optional[int]:
        if v is None:
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            return None
