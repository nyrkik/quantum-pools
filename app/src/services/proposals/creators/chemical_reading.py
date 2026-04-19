"""Proposal creator: `chemical_reading` entity_type.

Used by DeepBlue's `log_chemical_reading` tool. Delegates to
`ChemicalService.create()` — the canonical path that handles auto
pool_gallons lookup, recommendation generation, and chemistry emits
(chemical_reading.logged + any out-of-range events).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.chemical_service import ChemicalService
from src.services.events.platform_event_service import Actor
from src.services.proposals.registry import register


_MEASURABLES = (
    "ph", "free_chlorine", "combined_chlorine", "alkalinity",
    "calcium_hardness", "cyanuric_acid", "phosphates", "water_temp",
)


class ChemicalReadingProposalPayload(BaseModel):
    """Fields a proposal can commit to a chemical_reading."""

    property_id: str
    water_feature_id: Optional[str] = None
    ph: Optional[float] = None
    free_chlorine: Optional[float] = None
    combined_chlorine: Optional[float] = None
    alkalinity: Optional[int] = None
    calcium_hardness: Optional[int] = None
    cyanuric_acid: Optional[int] = None
    phosphates: Optional[int] = None
    water_temp: Optional[float] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _at_least_one_reading(self):
        """An empty reading is meaningless — reject at stage time."""
        if not any(getattr(self, k) is not None for k in _MEASURABLES):
            raise ValueError("At least one chemical reading must be provided.")
        return self


@register("chemical_reading", schema=ChemicalReadingProposalPayload)
async def create_chemical_reading_from_proposal(
    payload: dict, org_id: str, actor: Actor, db: AsyncSession,
):
    return await ChemicalService(db).create(
        org_id=org_id,
        actor=actor,
        source="proposal_accepted",
        property_id=payload["property_id"],
        water_feature_id=payload.get("water_feature_id"),
        ph=payload.get("ph"),
        free_chlorine=payload.get("free_chlorine"),
        combined_chlorine=payload.get("combined_chlorine"),
        alkalinity=payload.get("alkalinity"),
        calcium_hardness=payload.get("calcium_hardness"),
        cyanuric_acid=payload.get("cyanuric_acid"),
        phosphates=payload.get("phosphates"),
        water_temp=payload.get("water_temp"),
        notes=payload.get("notes"),
    )
