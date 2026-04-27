"""Test strip vision reader.

Tech photographs a freshly-dipped pool test strip; this service asks Claude
Haiku 4.5 (multimodal) to read the color bands and return structured chemical
values (pH, free/total chlorine, alkalinity, calcium hardness, cyanuric acid,
and any other bands present).

Pipeline (post brand-library upgrade 2026-04-26):
  1. **Identify** — first Vision call returns just `{brand_id, confidence}`
     by matching against `test_strip_brands` records (name + aliases).
  2. **Read** — second Vision call. If a brand was matched, the prompt
     injects that brand's pad layout + color_scale rows (ground-truth
     reference). Otherwise, falls back to "use your training knowledge"
     mode and logs a `brand_unknown` event so we know which strips need
     chart data.

DNA rules:
  - "AI never commits to the customer" doesn't apply (these are internal
    measurement values, not customer-facing). Auto-fill the form. Tech reviews
    and saves manually — the existing save endpoint stays the source of truth.
  - "Every agent learns" — `AgentLearningService` corrections are wired so
    that when a tech edits a value before saving, that correction trains the
    next call. Lessons are injected per-org.

The reader does NOT save to ChemicalReading directly. It returns a dict of
field-> value tuples; the visit-readings UI pre-populates its inputs and the
existing `POST /v1/visits/{id}/readings` endpoint persists when the tech
clicks save.
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, field
from typing import Any

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.ai_models import get_model
from src.models.test_strip_brand import TestStripBrand, TestStripPad
from src.services.agent_learning_service import (
    AGENT_TEST_STRIP_READER,
    AgentLearningService,
)

logger = logging.getLogger(__name__)


# Fields the test strip reader is allowed to return.
# Keys map 1:1 onto VisitReading / ChemicalReading columns.
SUPPORTED_FIELDS = (
    "ph",
    "free_chlorine",
    "total_chlorine",
    "combined_chlorine",  # derived: total - free
    "alkalinity",
    "calcium_hardness",
    "cyanuric_acid",
    "salt",
    "phosphates",
    "tds",
)


@dataclass
class TestStripResult:
    values: dict[str, float] = field(default_factory=dict)
    confidence: float = 0.0
    brand_detected: str | None = None
    brand_id: str | None = None
    chart_used: bool = False
    notes: str | None = None
    raw_response: str | None = None
    error: str | None = None


_IDENTIFY_PROMPT = """You're identifying a pool/spa test strip from a photograph. Look at the strip itself and any visible packaging/bottle/cap to determine the BRAND + PRODUCT NAME.

Known brands include (case-insensitive substring match against this list — pick the closest):
{brand_list}

If the strip's brand cannot be confidently identified, return null for brand_id.

Return ONLY this JSON shape, no markdown fences:
{{
  "brand_id": "<id from the list above>" or null,
  "brand_name": "what you see — e.g. 'AquaChek 7-way Pool & Spa'",
  "confidence": 0.0-1.0
}}
"""


_READ_PROMPT_WITH_CHART = """You are reading a freshly-dipped pool/spa test strip. The brand is identified — use the printed reference chart below to map each pad's color to a value.

BRAND: {brand_name}
PADS (in order from {pad_order_hint}):
{pads_block}

INSTRUCTIONS:
- For each pad, compare its photographed color to the closest entry on its color_scale and return that scale's value. If the pad color is between two scale entries, pick the closer one.
- Skip pads you can't see clearly. Don't guess.
- If the strip in the photo doesn't match the brand chart layout (different number of pads, different field order), you can fall back to your general knowledge — set chart_followed=false.

{lessons_block}

Return ONLY this JSON shape, no markdown fences, no preamble:
{{
  "values": {{ /* keys are chemistry_field names from the pads above; values are numeric */ }},
  "confidence": 0.0-1.0,
  "chart_followed": true/false,
  "notes": "short tech-facing note about anything unusual. Empty string if nothing notable."
}}
"""


_READ_PROMPT_NO_CHART = """You are reading a freshly-dipped pool/spa test strip from a photograph. The brand could not be confidently identified, so you need to use your general knowledge of common pool test strip color scales.

INSTRUCTIONS:
- Look for any visible reference chart in the photo and use it preferentially.
- Otherwise, use your knowledge of standard color charts for the most common brands (AquaChek, Industrial Test Systems / WaterWorks, La Motte, Taylor, Hach, Pentair, generic).
- Return ONE JSON object with the fields you can confidently read. Skip fields you can't see — don't guess.

ALL FIELDS USE THESE UNITS:
- ph: dimensionless (typical 6.8-8.4)
- free_chlorine, total_chlorine, combined_chlorine: ppm / mg/L (typical 0-10)
- alkalinity: ppm as CaCO3 (typical 0-240)
- calcium_hardness: ppm as CaCO3 (typical 0-1000)
- cyanuric_acid: ppm (typical 0-150)
- salt: ppm (typical 0-5000)
- phosphates: ppb (typical 0-1000)
- tds: ppm

{lessons_block}

Return ONLY this JSON shape, no markdown fences, no preamble:
{{
  "values": {{ /* ONLY include fields you can read */ }},
  "confidence": 0.0-1.0,
  "brand_detected": "string or null (your best guess at brand from the photo)",
  "notes": "short tech-facing note. Empty string if nothing notable."
}}
"""


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return text


async def _vision_call(image_b64: str, media_type: str, prompt: str, max_tokens: int = 600) -> str:
    """Run a single Claude Vision call against the image, returning the raw text."""
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=await get_model("fast"),
        max_tokens=max_tokens,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": image_b64},
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )
    return response.content[0].text


async def _identify_brand(
    db: AsyncSession,
    image_b64: str,
    media_type: str,
    brand_hint: str | None,
) -> tuple[TestStripBrand | None, str | None, float]:
    """First-pass: list active brands → ask Claude which one this strip is.
    Returns (brand_row | None, brand_name_seen, confidence)."""
    result = await db.execute(
        select(TestStripBrand).where(TestStripBrand.is_active == True).order_by(TestStripBrand.name)
    )
    brands = result.scalars().all()
    if not brands:
        return (None, None, 0.0)

    if brand_hint:
        for b in brands:
            if brand_hint.lower() in (b.name or "").lower() or any(
                brand_hint.lower() in (a or "").lower() for a in (b.aliases or [])
            ):
                return (b, b.name, 1.0)

    brand_lines = [f"- id={b.id}  name={b.name}  aliases={b.aliases or []}" for b in brands]
    prompt = _IDENTIFY_PROMPT.format(brand_list="\n".join(brand_lines))
    try:
        raw = await _vision_call(image_b64, media_type, prompt, max_tokens=200)
        parsed = json.loads(_strip_code_fence(raw))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"test_strip_reader brand-id failed: {e}; assuming unknown")
        return (None, None, 0.0)

    brand_id = parsed.get("brand_id")
    brand_name = parsed.get("brand_name")
    try:
        confidence = float(parsed.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    if not brand_id or confidence < 0.5:
        return (None, brand_name, confidence)
    matched = next((b for b in brands if b.id == brand_id), None)
    return (matched, brand_name or (matched.name if matched else None), confidence)


def _format_pads_block(pads: list[TestStripPad]) -> str:
    lines: list[str] = []
    for p in pads:
        scale = ", ".join(f"{e['hex']}={e['value']}" for e in (p.color_scale or []))
        lines.append(
            f"- pad #{p.pad_index + 1}: {p.chemistry_field} ({p.unit or ''})\n"
            f"    color_scale: {scale}"
        )
    return "\n".join(lines)


def _normalize_values(raw_values: dict | None) -> dict[str, float]:
    out: dict[str, float] = {}
    if not isinstance(raw_values, dict):
        return out
    for k, v in raw_values.items():
        if k not in SUPPORTED_FIELDS:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if fv != fv or fv == float("inf") or fv == float("-inf"):
            continue
        out[k] = round(fv, 2)
    if "combined_chlorine" not in out and "free_chlorine" in out and "total_chlorine" in out:
        cc = out["total_chlorine"] - out["free_chlorine"]
        if cc >= 0:
            out["combined_chlorine"] = round(cc, 2)
    return out


async def read_strip(
    db: AsyncSession,
    org_id: str,
    image_bytes: bytes,
    media_type: str = "image/jpeg",
    brand_hint: str | None = None,
) -> TestStripResult:
    """Two-pass read: identify brand → read with chart-injected prompt (or
    fallback if brand unknown).
    """
    if not image_bytes:
        return TestStripResult(error="empty image")

    image_b64 = base64.b64encode(image_bytes).decode("ascii")

    # Pass 1: identify brand
    brand: TestStripBrand | None = None
    brand_name_seen: str | None = None
    try:
        brand, brand_name_seen, _id_conf = await _identify_brand(db, image_b64, media_type, brand_hint)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"test_strip_reader identify-brand call failed (continuing in fallback mode): {e}")

    # Pull pads if we have a brand
    pads: list[TestStripPad] = []
    if brand is not None:
        result = await db.execute(
            select(TestStripPad).where(TestStripPad.brand_id == brand.id).order_by(TestStripPad.pad_index)
        )
        pads = list(result.scalars().all())

    # Lessons from past corrections
    lessons_block = ""
    try:
        learner = AgentLearningService(db)
        lessons = await learner.build_lessons_prompt(org_id, AGENT_TEST_STRIP_READER) or ""
        if lessons:
            lessons_block = f"LESSONS FROM PAST CORRECTIONS — apply these:\n{lessons}\n"
    except Exception as e:  # noqa: BLE001
        logger.warning(f"test_strip_reader lessons fetch failed (continuing): {e}")

    # Pass 2: read
    chart_used = False
    if brand is not None and pads:
        prompt = _READ_PROMPT_WITH_CHART.format(
            brand_name=brand.name,
            pad_order_hint="dipped end (closer to fingers) to handle end" if brand.notes is None else (brand.notes or "dipped end to handle"),
            pads_block=_format_pads_block(pads),
            lessons_block=lessons_block,
        )
        chart_used = True
    else:
        prompt = _READ_PROMPT_NO_CHART.format(lessons_block=lessons_block)

    try:
        raw = await _vision_call(image_b64, media_type, prompt, max_tokens=600)
    except Exception as e:  # noqa: BLE001
        logger.exception(f"test_strip_reader Claude call failed: {e}")
        return TestStripResult(error=f"vision call failed: {e}")

    try:
        parsed: dict[str, Any] = json.loads(_strip_code_fence(raw))
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"test_strip_reader bad JSON: {e!r}; raw={raw[:200]}")
        return TestStripResult(error=f"parse error: {e}", raw_response=raw[:500])

    values = _normalize_values(parsed.get("values"))
    try:
        confidence = float(parsed.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    chart_followed = bool(parsed.get("chart_followed", chart_used))
    if chart_used and not chart_followed:
        # Reader fell back to general knowledge despite our chart injection
        chart_used = False

    brand_label = (brand.name if brand else None) or parsed.get("brand_detected") or brand_name_seen

    return TestStripResult(
        values=values,
        confidence=confidence,
        brand_detected=brand_label,
        brand_id=brand.id if brand else None,
        chart_used=chart_used,
        notes=parsed.get("notes") or None,
        raw_response=raw[:500],
    )
