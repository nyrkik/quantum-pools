"""Reassemble brand+model when the EMD PDF extractor split a brand mid-word.

Symptoms in the wild (Sapphire data, 2026-04-26):
  brand='P' model='urex Triton CC'    →  Purex Triton CC
  brand='P' model='ENTAIR TR-'        →  Pentair TR-
  brand='H' model='ayward C-'         →  Hayward C-
  brand='S' model='ta-Rite S'         →  Sta-Rite S

Algorithm: concat (brand + model), case-insensitively match against the
longest known brand prefix, split into (brand, remainder).

Used by the inspection sync at write time AND by a one-time fixer script
that walks existing equipment_items rows.
"""

from __future__ import annotations

# Order matters — longer prefixes first so "Pentair Purex" wins over "Purex".
KNOWN_BRAND_PREFIXES = [
    "Pentair Purex",
    "Sta-Rite",
    "Sta Rite",
    "StaRite",
    "Aquastar",
    "AquaStar",
    "Aqua Star",
    "Pentair",
    "Hayward",
    "Purex",
    "Jandy",
    "Polaris",
    "Waterway",
    "Rolachem",
    "Rola-Chem",
    "Pulsar",
    "Stenner",
    "Walchem",
    "ProMinent",
    "Pro-Minent",
    "Blue-White",
    "Blue White",
    "LMI",
    "Iwaki",
    "Milton Roy",
    "Triton",
    "Whisperflo",   # Pentair model; rarely the BRAND but we've seen it parsed that way
]

_PREFIXES_LOWER = sorted(
    [(p.lower(), p) for p in KNOWN_BRAND_PREFIXES],
    key=lambda x: -len(x[0]),
)


def reassemble(brand: str | None, model: str | None) -> tuple[str | None, str | None] | None:
    """If brand looks like a 1-2 char fragment that combines with model into a
    known brand, return (brand_canonical, model_remainder). Else None.

    Returning None means leave the row alone — don't guess.
    """
    if not brand:
        return None
    b = brand.strip()
    m = (model or "").strip()
    # Only act on suspicious short brand fragments
    if len(b) > 2 or not m:
        return None

    combined = (b + m).strip()
    combined_lower = combined.lower()
    for prefix_lower, canonical in _PREFIXES_LOWER:
        if combined_lower.startswith(prefix_lower):
            remainder = combined[len(prefix_lower):].lstrip(" -:,.")
            return (canonical, remainder or None)
    return None
