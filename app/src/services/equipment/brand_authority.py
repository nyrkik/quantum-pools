"""Brand → category authority list.

Captures industry knowledge that a parsed PDF + downstream resolver can't infer
from text alone: certain manufacturer names are reliably associated with one
equipment type, regardless of which field the inspection extractor put them in.

Used by `inspection.service._sync_equipment_items_from_inspection` to override
the slot's nominal `equipment_type` when the brand says otherwise. Example: the
EMD PDF extractor sometimes drops "Rolachem RC103SC" into `filter_pump_2_make`,
but Rolachem only manufactures chemical feeders / chlorinators, never pool
pumps — so we coerce `equipment_type` to `sanitizer` and skip if a real
sanitizer slot already captured the same brand+model.

Keep this list short and high-confidence. If a brand is multi-category, leave
it out — the resolver agent will figure it out from context.
"""

from __future__ import annotations

# Brand → canonical equipment_type. Brand keys are lowercased on lookup.
SANITIZER_BRANDS = frozenset({
    "rolachem",
    "rola-chem",
    "stenner",
    "blue-white",
    "blue white",
    "lmi",
    "milton roy",
    "walchem",
    "prominent",
    "pro-minent",
    "pulsar",        # Pulsar Chemical (briquette feeders), not the brand of pumps
    "iwaki",
})


def authoritative_type(brand: str | None) -> str | None:
    """Return the authoritative equipment_type for a brand, or None if unknown.

    Substring matching is intentionally conservative — the input must be
    ≥4 chars to match a longer known brand, or the known brand must be
    fully contained in the input (catches `Rolachem RC103SC` → rolachem).
    Otherwise short noisy values like 'P' or 'S' (a separate PDF-extractor
    splitting bug) trigger false matches.
    """
    if not brand:
        return None
    b = brand.strip().lower()
    if b in SANITIZER_BRANDS:
        return "sanitizer"
    # Need at least 4 chars on the input side to do substring matching
    if len(b) < 4:
        return None
    for known in SANITIZER_BRANDS:
        # Known fully contained in input (e.g., "Rolachem auto feeder")
        if known in b:
            return "sanitizer"
        # Input fully contained in known (input is ≥4 char fragment of known)
        if b in known and len(b) >= 4:
            return "sanitizer"
    return None
