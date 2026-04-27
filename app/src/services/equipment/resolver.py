"""Equipment resolver — match free-text (brand, model) tuples to catalog entries.

Used by the inspection-equipment sync to attach a `catalog_equipment_id` to
auto-created `EquipmentItem` rows. Pipeline:

1. rapidfuzz pre-filter: top N catalog candidates by manufacturer+model
   similarity. If no candidate clears the floor, return no-match.
2. Single-candidate shortcut: if the top hit is a near-exact (>= 0.92), skip
   the Claude round-trip.
3. Claude Haiku resolver: asks the model to pick the right candidate, with
   `AgentLearningService` lessons injected. Returns catalog_id + confidence
   (0.0-1.0).

Confidence threshold for catalog linkage: >= 0.8. Below that, the EquipmentItem
is created without a catalog FK — raw brand/model strings only.

DNA rule 2 (every agent learns): the resolver pulls past corrections from
`agent_corrections` (agent_type=`equipment_resolver`) before calling Claude.
The acceptance/rejection side of the loop is wired in the equipment routes:
PATCH on a `source_inspection_id`-tagged item logs `edit`; DELETE logs
`rejection`.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Sequence

import anthropic
from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.equipment_catalog import EquipmentCatalog
from src.services.agent_learning_service import (
    AGENT_EQUIPMENT_RESOLVER,
    AgentLearningService,
)

logger = logging.getLogger(__name__)

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL_NAME = "claude-haiku-4-5-20251001"

PREFILTER_FLOOR = 60      # rapidfuzz partial_ratio score 0-100; below this candidate is dropped
EXACT_MATCH_FLOOR = 92    # if best candidate scores >= this, skip Claude
PREFILTER_TOP_N = 5
CLAUDE_CONFIDENCE_FLOOR = 0.8  # below this, no catalog FK linkage


@dataclass
class ResolverResult:
    catalog_equipment_id: str | None
    confidence: float
    candidates_considered: int
    reasoning: str | None = None
    via: str = "none"  # "none" | "rapidfuzz_exact" | "claude" | "skipped_no_input"


def _normalize(s: str | None) -> str:
    return (s or "").strip().lower()


def _build_haystack(c: EquipmentCatalog) -> str:
    parts = [c.manufacturer or "", c.model_number or "", c.canonical_name or ""]
    return " ".join(p for p in parts if p)


async def _prefilter_candidates(
    db: AsyncSession,
    brand: str,
    model: str,
    equipment_type: str | None,
) -> list[tuple[EquipmentCatalog, int]]:
    """Return up to PREFILTER_TOP_N (catalog_row, score) tuples sorted by score desc."""
    query = select(EquipmentCatalog).where(EquipmentCatalog.is_active == True)
    if equipment_type:
        query = query.where(EquipmentCatalog.equipment_type == equipment_type)
    result = await db.execute(query)
    catalog: Sequence[EquipmentCatalog] = result.scalars().all()
    if not catalog:
        return []

    needle = f"{_normalize(brand)} {_normalize(model)}".strip()
    if not needle:
        return []

    haystack = {c.id: _build_haystack(c) for c in catalog}
    by_id = {c.id: c for c in catalog}

    matches = process.extract(
        needle,
        haystack,
        scorer=fuzz.WRatio,
        limit=PREFILTER_TOP_N,
        score_cutoff=PREFILTER_FLOOR,
    )
    out: list[tuple[EquipmentCatalog, int]] = []
    for _, score, key in matches:
        out.append((by_id[key], int(score)))
    return out


async def _resolve_with_claude(
    org_id: str,
    brand: str,
    model: str,
    hp: str | None,
    equipment_type: str | None,
    candidates: list[tuple[EquipmentCatalog, int]],
    learner: AgentLearningService,
) -> ResolverResult:
    """Ask Claude to pick the right candidate. Inject past corrections."""
    if not ANTHROPIC_KEY:
        return ResolverResult(None, 0.0, len(candidates), "no anthropic key", via="none")

    lessons = ""
    try:
        lessons = await learner.build_lessons_prompt(
            org_id, AGENT_EQUIPMENT_RESOLVER, category=equipment_type,
        ) or ""
    except Exception as e:  # noqa: BLE001
        logger.warning(f"equipment_resolver lessons fetch failed (continuing): {e}")

    candidates_json = [
        {
            "id": c.id,
            "manufacturer": c.manufacturer,
            "model_number": c.model_number,
            "canonical_name": c.canonical_name,
            "score": score,
        }
        for c, score in candidates
    ]

    user_content = (
        f"Match this inspection-extracted equipment to the most likely catalog "
        f"entry. Reply ONLY with a JSON object: "
        f'{{"catalog_id": "<id>" or null, "confidence": 0.0-1.0, "reasoning": "<short>"}}.\n\n'
        f"INSPECTION DATA:\n"
        f"  brand: {brand or '(blank)'}\n"
        f"  model: {model or '(blank)'}\n"
        f"  hp: {hp or '(blank)'}\n"
        f"  equipment_type: {equipment_type or '(unknown)'}\n\n"
        f"CANDIDATES (sorted by fuzzy match score):\n"
        f"{json.dumps(candidates_json, indent=2)}\n\n"
        f"Rules:\n"
        f"- Return null catalog_id if NO candidate is a confident match (typo "
        f"differences are OK; structurally different models are not).\n"
        f"- Confidence reflects how sure you are: 1.0 = exact, 0.8 = strong, "
        f"0.5 = plausible, 0.0 = no match.\n"
        f"- Be conservative. False positives are worse than null."
    )
    if lessons:
        user_content = f"{lessons}\n\n{user_content}"

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        resp = client.messages.create(
            model=MODEL_NAME,
            max_tokens=200,
            messages=[{"role": "user", "content": user_content}],
        )
        text = resp.content[0].text.strip()
        # Strip code fences if Claude added any
        if text.startswith("```"):
            text = text.split("```", 2)[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        parsed = json.loads(text)
        catalog_id = parsed.get("catalog_id")
        confidence = float(parsed.get("confidence", 0.0))
        reasoning = parsed.get("reasoning")

        # Validate catalog_id is one we offered
        valid_ids = {c.id for c, _ in candidates}
        if catalog_id and catalog_id not in valid_ids:
            logger.warning(f"equipment_resolver returned id not in candidates: {catalog_id}")
            return ResolverResult(None, 0.0, len(candidates), "returned id not offered", via="claude")

        return ResolverResult(
            catalog_equipment_id=catalog_id if confidence >= CLAUDE_CONFIDENCE_FLOOR else None,
            confidence=confidence,
            candidates_considered=len(candidates),
            reasoning=reasoning,
            via="claude",
        )
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.warning(f"equipment_resolver bad Claude output: {e}")
        return ResolverResult(None, 0.0, len(candidates), f"parse error: {e}", via="claude")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"equipment_resolver Claude call failed: {e}")
        return ResolverResult(None, 0.0, len(candidates), f"api error: {e}", via="claude")


async def resolve(
    db: AsyncSession,
    org_id: str,
    brand: str | None,
    model: str | None,
    hp: str | None = None,
    equipment_type: str | None = None,
) -> ResolverResult:
    """Resolve free-text (brand, model) → catalog FK with confidence.

    Returns ResolverResult. If `catalog_equipment_id` is None, the caller
    should still create the EquipmentItem with raw brand/model strings.
    """
    if not (brand or model):
        return ResolverResult(None, 0.0, 0, "no input", via="skipped_no_input")

    candidates = await _prefilter_candidates(db, brand or "", model or "", equipment_type)
    if not candidates:
        return ResolverResult(None, 0.0, 0, "no candidates above floor", via="none")

    # Single-candidate shortcut for near-exact match
    top_catalog, top_score = candidates[0]
    if top_score >= EXACT_MATCH_FLOOR and (
        len(candidates) == 1 or top_score - candidates[1][1] >= 8
    ):
        return ResolverResult(
            catalog_equipment_id=top_catalog.id,
            confidence=min(1.0, top_score / 100.0),
            candidates_considered=len(candidates),
            reasoning=f"rapidfuzz exact match (score={top_score})",
            via="rapidfuzz_exact",
        )

    learner = AgentLearningService(db)
    return await _resolve_with_claude(
        org_id, brand or "", model or "", hp, equipment_type, candidates, learner,
    )
