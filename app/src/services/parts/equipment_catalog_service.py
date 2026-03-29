"""Equipment Catalog Service — search, resolve, manage canonical equipment entries."""

import json
import logging
import uuid
from typing import Optional

from sqlalchemy import select, or_, func, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.equipment_catalog import EquipmentCatalog
from src.models.parts_catalog import PartsCatalog

logger = logging.getLogger(__name__)


class EquipmentCatalogService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def search(self, query: str, equipment_type: Optional[str] = None, limit: int = 20) -> list[dict]:
        """Search catalog by canonical_name, aliases, manufacturer, model_number."""
        q = select(EquipmentCatalog).where(EquipmentCatalog.is_active == True)

        if equipment_type:
            q = q.where(EquipmentCatalog.equipment_type == equipment_type)

        if query.strip():
            pattern = f"%{query.strip()}%"
            q = q.where(
                or_(
                    EquipmentCatalog.canonical_name.ilike(pattern),
                    EquipmentCatalog.manufacturer.ilike(pattern),
                    EquipmentCatalog.model_number.ilike(pattern),
                    func.lower(cast(EquipmentCatalog.aliases, String)).contains(query.strip().lower()),
                )
            )

        q = q.order_by(EquipmentCatalog.is_common.desc(), EquipmentCatalog.canonical_name).limit(limit)
        result = await self.db.execute(q)
        return [self._to_dict(e) for e in result.scalars().all()]

    async def get_by_id(self, catalog_id: str) -> Optional[dict]:
        """Get catalog entry with linked parts."""
        result = await self.db.execute(
            select(EquipmentCatalog).where(EquipmentCatalog.id == catalog_id)
        )
        entry = result.scalar_one_or_none()
        if not entry:
            return None

        # Get linked parts
        parts_result = await self.db.execute(
            select(PartsCatalog).where(
                PartsCatalog.for_equipment_id == catalog_id,
                PartsCatalog.is_chemical == False,
            ).order_by(PartsCatalog.category, PartsCatalog.name).limit(20)
        )
        parts = [
            {"id": p.id, "name": p.name, "brand": p.brand, "sku": p.sku,
             "category": p.category, "description": p.description, "product_url": p.product_url}
            for p in parts_result.scalars().all()
        ]

        # Also search by compatible_with + name for parts not yet linked
        if not parts:
            # Build search terms: model_number, aliases, canonical_name
            search_terms = []
            if entry.model_number and entry.model_number != "?":
                search_terms.append(entry.model_number.lower())
            for alias in (entry.aliases or []):
                if len(alias) >= 3:
                    search_terms.append(alias.lower())
            search_terms.append(entry.canonical_name.lower())

            conditions = []
            compat_col = func.lower(cast(PartsCatalog.compatible_with, String))
            name_col = func.lower(PartsCatalog.name)
            for term in search_terms:
                conditions.append(compat_col.contains(term))
                conditions.append(name_col.contains(term))

            if conditions:
                compat_result = await self.db.execute(
                    select(PartsCatalog).where(
                        or_(*conditions),
                        PartsCatalog.is_chemical == False,
                    ).order_by(PartsCatalog.category, PartsCatalog.name).limit(20)
                )
                parts = [
                    {"id": p.id, "name": p.name, "brand": p.brand, "sku": p.sku,
                     "category": p.category, "description": p.description, "product_url": p.product_url}
                    for p in compat_result.scalars().all()
                ]

        d = self._to_dict(entry)
        d["parts"] = parts
        return d

    async def create(self, data: dict, org_id: Optional[str] = None) -> EquipmentCatalog:
        """Create a new catalog entry."""
        entry = EquipmentCatalog(
            id=str(uuid.uuid4()),
            canonical_name=data["canonical_name"],
            equipment_type=data.get("equipment_type", "equipment"),
            manufacturer=data.get("manufacturer"),
            model_number=data.get("model_number"),
            category=data.get("category"),
            specs=data.get("specs"),
            aliases=data.get("aliases", []),
            is_common=data.get("is_common", False),
            source=data.get("source", "manual"),
            created_by_org_id=org_id,
        )
        self.db.add(entry)
        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    async def update(self, catalog_id: str, data: dict) -> Optional[EquipmentCatalog]:
        """Update a catalog entry."""
        result = await self.db.execute(
            select(EquipmentCatalog).where(EquipmentCatalog.id == catalog_id)
        )
        entry = result.scalar_one_or_none()
        if not entry:
            return None

        for k, v in data.items():
            if hasattr(entry, k) and k not in ("id", "created_at"):
                setattr(entry, k, v)

        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    async def resolve(self, raw_text: str, equipment_type: str = "equipment") -> dict:
        """AI-powered resolution: match raw text to catalog entry or create new one.

        Returns: {"entry": dict, "matched": bool, "created": bool}
        """
        normalized = raw_text.strip().lower()
        if not normalized or len(normalized) < 3:
            return {"entry": None, "matched": False, "created": False}

        # 1. Search by alias containment (exact match in aliases)
        alias_result = await self.db.execute(
            select(EquipmentCatalog).where(
                EquipmentCatalog.is_active == True,
                func.lower(cast(EquipmentCatalog.aliases, String)).contains(normalized),
            ).limit(1)
        )
        match = alias_result.scalar_one_or_none()
        if match:
            return {"entry": self._to_dict(match), "matched": True, "created": False}

        # 2. Search by canonical_name, manufacturer, model_number
        pattern = f"%{normalized}%"
        name_result = await self.db.execute(
            select(EquipmentCatalog).where(
                EquipmentCatalog.is_active == True,
                or_(
                    func.lower(EquipmentCatalog.canonical_name).contains(normalized),
                    func.lower(EquipmentCatalog.model_number).contains(normalized),
                ),
            ).limit(1)
        )
        match = name_result.scalar_one_or_none()
        if match:
            await self._add_alias(match, raw_text)
            return {"entry": self._to_dict(match), "matched": True, "created": False}

        # 3. No match — use AI to parse the raw text
        parsed = await self._ai_parse(raw_text, equipment_type)
        if not parsed or not parsed.get("manufacturer"):
            return {"entry": None, "matched": False, "created": False}

        # 4. Search again with parsed data
        if parsed.get("model_number"):
            model_result = await self.db.execute(
                select(EquipmentCatalog).where(
                    EquipmentCatalog.is_active == True,
                    func.lower(EquipmentCatalog.manufacturer) == parsed["manufacturer"].lower(),
                    func.lower(EquipmentCatalog.model_number).contains(parsed["model_number"].lower()),
                ).limit(1)
            )
            match = model_result.scalar_one_or_none()
            if match:
                await self._add_alias(match, raw_text)
                return {"entry": self._to_dict(match), "matched": True, "created": False}

        # 5. Create new entry
        entry = await self.create({
            "canonical_name": parsed.get("canonical_name", raw_text),
            "equipment_type": equipment_type,
            "manufacturer": parsed.get("manufacturer"),
            "model_number": parsed.get("model_number"),
            "category": parsed.get("category"),
            "specs": parsed.get("specs"),
            "aliases": [raw_text.strip()],
            "source": "ai_normalized",
        })

        return {"entry": self._to_dict(entry), "matched": False, "created": True}

    async def _add_alias(self, entry: EquipmentCatalog, alias: str):
        """Add alias to entry if not already present."""
        current = entry.aliases or []
        normalized = alias.strip().lower()
        if not any(a.lower() == normalized for a in current):
            entry.aliases = current + [alias.strip()]
            await self.db.commit()

    async def _ai_parse(self, raw_text: str, equipment_type: str) -> Optional[dict]:
        """Use Claude to parse raw equipment text into structured data."""
        try:
            import anthropic
            from src.core.ai_models import get_model

            client = anthropic.Anthropic()
            response = client.messages.create(
                model=get_model("fast"),
                max_tokens=500,
                messages=[{"role": "user", "content": f"""Parse this pool equipment string into structured data. You are an expert in pool/spa equipment.

Raw text: "{raw_text}"
Equipment type: {equipment_type}

Return JSON with these fields:
- canonical_name: the proper full name (e.g., "Pentair IntelliFlo VS+SVRS 3HP")
- manufacturer: brand/manufacturer name
- model_number: manufacturer's official model/part number if known
- category: specific category (e.g., "Variable Speed Pump", "Cartridge Filter", "Salt Chlorinator")
- specs: object with relevant specs (hp, voltage, gpm, btu, sqft as applicable)

JSON only, no markdown."""}],
            )

            text = response.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            return json.loads(text)
        except Exception as e:
            logger.warning(f"AI parse failed for '{raw_text}': {e}")
            return None

    @staticmethod
    def _to_dict(e: EquipmentCatalog) -> dict:
        return {
            "id": e.id,
            "canonical_name": e.canonical_name,
            "equipment_type": e.equipment_type,
            "manufacturer": e.manufacturer,
            "model_number": e.model_number,
            "category": e.category,
            "image_url": e.image_url,
            "specs": e.specs,
            "aliases": e.aliases or [],
            "is_common": e.is_common,
            "source": e.source,
        }
