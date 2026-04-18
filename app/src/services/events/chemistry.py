"""Chemistry-specific event emission helpers.

Wraps PlatformEventService.emit() with the right shape for:
  - chemical_reading.logged — every reading creation
  - chemistry.reading.out_of_range — 0..N events per reading, one per
    parameter that fell outside MAHC / Title-22 / residential defaults.

Both helpers are called by every ChemicalReading-creation site:
  - ChemicalService.create (the `/v1/readings` POST endpoint)
  - DeepBlue's confirm_log_reading handler
  - VisitExperienceService (tech-completed visit workflow)

Keeping this in one module means all three paths emit identically-shaped
events. When thresholds get fancier (jurisdiction-specific ranges,
commercial-pool closure detection), only this file changes.

Design reference: docs/event-taxonomy.md §8.7, docs/ai-platform-phase-1.md §6.7.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.services.events.platform_event_service import Actor, PlatformEventService
from src.services.events.actor_factory import actor_system


# ---------------------------------------------------------------------------
# Threshold table (residential defaults)
#
# Mirrors the ranges used by ChemicalService.generate_recommendations so
# display-side issues and event-side out-of-range signals agree. MAHC /
# Title 22 commercial stricter ranges are a future refinement — for v1
# we use a single table and mark the source as 'residential_default'.
# ---------------------------------------------------------------------------


Severity = Literal["warning", "critical", "closure_required"]
ThresholdSource = Literal["residential_default", "mahc", "title_22", "custom"]


@dataclass(frozen=True)
class OutOfRange:
    parameter: str
    value: float
    direction: Literal["low", "high"]
    severity: Severity
    threshold_source: ThresholdSource


def _check_thresholds(reading) -> list[OutOfRange]:
    """Return structured out-of-range records for a reading.

    Only includes parameters that were both measured and outside the
    residential-default range. Severity bands:
      - warning — slightly out
      - critical — significantly out
      - closure_required — regulatory closure threshold (commercial only;
        currently unused — reserved for jurisdictional refinement)
    """
    out: list[OutOfRange] = []
    src: ThresholdSource = "residential_default"

    # pH: ideal 7.2-7.6
    if reading.ph is not None:
        if reading.ph < 6.8:
            out.append(OutOfRange("ph", reading.ph, "low", "critical", src))
        elif reading.ph < 7.2:
            out.append(OutOfRange("ph", reading.ph, "low", "warning", src))
        elif reading.ph > 8.0:
            out.append(OutOfRange("ph", reading.ph, "high", "critical", src))
        elif reading.ph > 7.6:
            out.append(OutOfRange("ph", reading.ph, "high", "warning", src))

    # Free chlorine: 1-5 ppm residential
    if reading.free_chlorine is not None:
        if reading.free_chlorine < 0.5:
            out.append(OutOfRange("free_chlorine", reading.free_chlorine, "low", "critical", src))
        elif reading.free_chlorine < 1.0:
            out.append(OutOfRange("free_chlorine", reading.free_chlorine, "low", "warning", src))
        elif reading.free_chlorine > 10.0:
            out.append(OutOfRange("free_chlorine", reading.free_chlorine, "high", "critical", src))
        elif reading.free_chlorine > 5.0:
            out.append(OutOfRange("free_chlorine", reading.free_chlorine, "high", "warning", src))

    # Combined chlorine (chloramines): should be <= 0.5
    if reading.combined_chlorine is not None and reading.combined_chlorine > 0.5:
        sev: Severity = "critical" if reading.combined_chlorine > 1.0 else "warning"
        out.append(OutOfRange("combined_chlorine", reading.combined_chlorine, "high", sev, src))

    # Alkalinity: 80-120 ppm
    if reading.alkalinity is not None:
        if reading.alkalinity < 60:
            out.append(OutOfRange("alkalinity", reading.alkalinity, "low", "critical", src))
        elif reading.alkalinity < 80:
            out.append(OutOfRange("alkalinity", reading.alkalinity, "low", "warning", src))
        elif reading.alkalinity > 180:
            out.append(OutOfRange("alkalinity", reading.alkalinity, "high", "critical", src))
        elif reading.alkalinity > 120:
            out.append(OutOfRange("alkalinity", reading.alkalinity, "high", "warning", src))

    # Calcium hardness: 200-400 ppm
    if reading.calcium_hardness is not None:
        if reading.calcium_hardness < 150:
            out.append(OutOfRange("calcium_hardness", reading.calcium_hardness, "low", "critical", src))
        elif reading.calcium_hardness < 200:
            out.append(OutOfRange("calcium_hardness", reading.calcium_hardness, "low", "warning", src))
        elif reading.calcium_hardness > 600:
            out.append(OutOfRange("calcium_hardness", reading.calcium_hardness, "high", "critical", src))
        elif reading.calcium_hardness > 400:
            out.append(OutOfRange("calcium_hardness", reading.calcium_hardness, "high", "warning", src))

    # CYA: 30-80 ppm
    if reading.cyanuric_acid is not None:
        if reading.cyanuric_acid < 30:
            out.append(OutOfRange("cyanuric_acid", reading.cyanuric_acid, "low", "warning", src))
        elif reading.cyanuric_acid > 100:
            out.append(OutOfRange("cyanuric_acid", reading.cyanuric_acid, "high", "critical", src))
        elif reading.cyanuric_acid > 80:
            out.append(OutOfRange("cyanuric_acid", reading.cyanuric_acid, "high", "warning", src))

    # Phosphates: keep below 300 ppb
    if reading.phosphates is not None and reading.phosphates > 300:
        sev = "critical" if reading.phosphates > 1000 else "warning"
        out.append(OutOfRange("phosphates", reading.phosphates, "high", sev, src))

    return out


# ---------------------------------------------------------------------------
# Emit helpers
# ---------------------------------------------------------------------------


ReadingSource = Literal["manual", "test_strip_vision", "deepblue", "visit"]


async def emit_chemical_reading_logged(
    db: AsyncSession,
    reading,
    *,
    source: ReadingSource,
    actor: Optional[Actor] = None,
) -> None:
    """Emit chemical_reading.logged once per reading creation.

    `actor` should reflect the real actor — user when manual via UI,
    agent when test_strip_vision/deepblue did it autonomously. Falls
    back to system if not provided.
    """
    refs = {
        "chemical_reading_id": reading.id,
        "property_id": reading.property_id,
    }
    if reading.water_feature_id:
        refs["water_feature_id"] = reading.water_feature_id
    if reading.visit_id:
        refs["visit_id"] = reading.visit_id

    await PlatformEventService.emit(
        db=db,
        event_type="chemical_reading.logged",
        level=(
            "user_action" if actor and actor.actor_type == "user"
            else "agent_action" if actor and actor.actor_type == "agent"
            else "system_action"
        ),
        actor=actor or actor_system(),
        organization_id=reading.organization_id,
        entity_refs=refs,
        payload={"source": source},
    )


async def emit_chemistry_out_of_range_events(
    db: AsyncSession,
    reading,
    *,
    actor: Optional[Actor] = None,
) -> int:
    """Emit one chemistry.reading.out_of_range event per parameter that's
    outside the acceptable range. Returns the number of events emitted
    (0 if all parameters are within range or not measured).
    """
    breaches = _check_thresholds(reading)
    if not breaches:
        return 0

    refs = {
        "chemical_reading_id": reading.id,
        "property_id": reading.property_id,
    }
    if reading.water_feature_id:
        refs["water_feature_id"] = reading.water_feature_id

    for b in breaches:
        await PlatformEventService.emit(
            db=db,
            event_type="chemistry.reading.out_of_range",
            # Automated check on a logged reading — system-level anomaly
            # detection, not a human action. If an agent triggered the
            # reading log (test-strip vision), we still tag the range
            # check itself as system since it's the threshold table's
            # assessment, not the agent's.
            level="system_action",
            actor=actor_system(),
            organization_id=reading.organization_id,
            entity_refs=refs,
            payload={
                "parameter": b.parameter,
                "direction": b.direction,
                "severity": b.severity,
                "threshold_source": b.threshold_source,
            },
        )
    return len(breaches)
