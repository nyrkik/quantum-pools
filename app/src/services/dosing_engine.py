"""Deterministic chemical dosing calculator + LSI calculator.

Pure functions — no DB access, no AI. All formulas are industry-standard.
This is safety-critical: never let AI generate dosing amounts.

LSI (Langelier Saturation Index) is calculated using a hardcoded water
temperature constant (75°F). Per `feedback_water_temp_constant.md`,
real-time temperature isn't worth the UI tax for the precision a
coarsely-banded gauge exposes; the tech can mentally adjust if their
pool runs hot or cold.
"""

import math


WATER_TEMP_F_DEFAULT = 75.0  # See module docstring + feedback memo.


# Industry-standard temperature factor table — ASR/Pool Operator's
# Handbook. Linearly interpolate between anchor points.
_TF_TABLE = [
    (32, 0.0),
    (37, 0.1),
    (46, 0.2),
    (53, 0.3),
    (60, 0.4),
    (66, 0.5),
    (76, 0.6),
    (84, 0.7),
    (94, 0.8),
    (105, 0.9),
]


def _tf(temp_f: float) -> float:
    """Temperature factor via linear interpolation against the standard
    LSI table. Clamped to the table's range."""
    if temp_f <= _TF_TABLE[0][0]:
        return _TF_TABLE[0][1]
    if temp_f >= _TF_TABLE[-1][0]:
        return _TF_TABLE[-1][1]
    for (t_lo, f_lo), (t_hi, f_hi) in zip(_TF_TABLE, _TF_TABLE[1:]):
        if t_lo <= temp_f <= t_hi:
            ratio = (temp_f - t_lo) / (t_hi - t_lo)
            return f_lo + ratio * (f_hi - f_lo)
    return _TF_TABLE[-1][1]  # unreachable; satisfy linter


def calculate_lsi(
    ph: float,
    calcium_hardness: float,
    alkalinity: float,
    cyanuric_acid: float | None = None,
    temp_f: float = WATER_TEMP_F_DEFAULT,
) -> dict:
    """Langelier Saturation Index.

    LSI = pH + TF + CF + AF − 12.1

    Where:
    - TF (temperature factor): interpolated from the standard table
    - CF (calcium hardness factor): log10(Ca) − 0.4
    - AF (alkalinity factor): log10(effective_alk), where
      effective_alk = alkalinity − cyanuric_acid / 3 (when CYA present)

    Returns a dict with the value, a 3-band classification
    (corrosive | balanced | scaling), and the inputs used so callers
    can surface the assumption ("temp: 75°F (assumed)").

    Classification thresholds:
      < -0.3  corrosive (water dissolves calcium → etching, pitting)
      -0.3..+0.3  balanced
      > +0.3  scaling (calcium precipitates → cloudy water, scale)
    """
    if calcium_hardness <= 0 or alkalinity <= 0:
        # log10 undefined; surface as a degenerate-input error rather
        # than crashing or returning a misleading number.
        raise ValueError(
            "calcium_hardness and alkalinity must be > 0 for LSI calculation"
        )

    cya = cyanuric_acid or 0.0
    effective_alk = alkalinity - (cya / 3.0)
    if effective_alk <= 0:
        raise ValueError(
            "effective_alk (alkalinity − CYA/3) must be > 0 for LSI calculation"
        )

    tf = _tf(temp_f)
    cf = math.log10(calcium_hardness) - 0.4
    af = math.log10(effective_alk)
    lsi = ph + tf + cf + af - 12.1
    lsi = round(lsi, 2)

    if lsi < -0.3:
        classification = "corrosive"
    elif lsi > 0.3:
        classification = "scaling"
    else:
        classification = "balanced"

    return {
        "value": lsi,
        "classification": classification,
        "based_on": {
            "ph": ph,
            "temp_f": temp_f,
            "calcium_hardness": calcium_hardness,
            "alkalinity": alkalinity,
            "cyanuric_acid": cya,
        },
    }


def calculate_dosing(
    pool_gallons: int,
    ph: float | None = None,
    free_chlorine: float | None = None,
    alkalinity: int | None = None,
    calcium_hardness: int | None = None,
    cyanuric_acid: int | None = None,
    combined_chlorine: float | None = None,
    phosphates: int | None = None,
) -> dict:
    """Calculate chemical dosing for all provided readings.

    Returns a structured result with current/target values and exact amounts.
    """
    results = []
    gal_factor = pool_gallons / 10000

    # pH adjustment
    if ph is not None:
        target_ph = 7.4
        if ph < 7.2:
            diff = target_ph - ph
            # Soda ash: ~6 oz per 10k gallons per 0.1 pH
            soda_ash_oz = diff * gal_factor * 6
            results.append({
                "parameter": "pH",
                "current": ph,
                "target": "7.2 – 7.6",
                "status": "low",
                "chemical": "Soda ash (sodium carbonate)",
                "amount": f"{soda_ash_oz:.1f} oz",
                "amount_value": round(soda_ash_oz, 1),
                "unit": "oz",
                "notes": "Add slowly with pump running. Retest after 4 hours.",
            })
        elif ph > 7.8:
            diff = ph - target_ph
            # Muriatic acid: ~16 oz per 10k gallons per 0.1 pH
            acid_oz = diff * gal_factor * 16
            # Also express in cups for field convenience
            acid_cups = acid_oz / 8
            results.append({
                "parameter": "pH",
                "current": ph,
                "target": "7.2 – 7.6",
                "status": "high",
                "chemical": "Muriatic acid (31.45%)",
                "amount": f"{acid_oz:.1f} oz ({acid_cups:.1f} cups)",
                "amount_value": round(acid_oz, 1),
                "unit": "oz",
                "notes": "Pour into deep end with pump running. Never add near skimmer.",
            })
        else:
            results.append({
                "parameter": "pH",
                "current": ph,
                "target": "7.2 – 7.6",
                "status": "ok",
                "chemical": None,
                "amount": None,
            })

    # Free chlorine
    if free_chlorine is not None:
        if free_chlorine < 1.0:
            diff = 3.0 - free_chlorine  # Target mid-range
            # Liquid chlorine (12.5%): ~10 oz per 10k gallons per 1 ppm
            liq_oz = diff * gal_factor * 10
            # Cal-hypo (68%): ~2 oz per 10k gallons per 1 ppm
            cal_hypo_oz = diff * gal_factor * 2
            # Dichlor (56%): ~2.5 oz per 10k gallons per 1 ppm
            dichlor_oz = diff * gal_factor * 2.5
            results.append({
                "parameter": "Free Chlorine",
                "current": free_chlorine,
                "target": "1.0 – 5.0 ppm",
                "status": "low",
                "chemical": "Liquid chlorine (12.5%)",
                "amount": f"{liq_oz:.1f} oz",
                "amount_value": round(liq_oz, 1),
                "unit": "oz",
                "alternatives": [
                    {"chemical": "Cal-hypo (68%)", "amount": f"{cal_hypo_oz:.1f} oz"},
                    {"chemical": "Dichlor (56%)", "amount": f"{dichlor_oz:.1f} oz"},
                ],
                "notes": "Add in evening for best retention. Retest next day.",
            })
        elif free_chlorine > 10.0:
            results.append({
                "parameter": "Free Chlorine",
                "current": free_chlorine,
                "target": "1.0 – 5.0 ppm",
                "status": "high",
                "chemical": "Sodium thiosulfate (chlorine neutralizer)",
                "amount": f"{gal_factor * 2.5:.1f} oz per 1 ppm reduction",
                "notes": "Or wait — chlorine will dissipate naturally. Keep swimmers out above 5 ppm.",
            })
        else:
            results.append({
                "parameter": "Free Chlorine",
                "current": free_chlorine,
                "target": "1.0 – 5.0 ppm",
                "status": "ok",
                "chemical": None,
                "amount": None,
            })

    # Combined chlorine (chloramines)
    if combined_chlorine is not None:
        if combined_chlorine > 0.5:
            # Breakpoint chlorination: need to raise FC to 10x combined chlorine
            shock_target = combined_chlorine * 10
            current_fc = free_chlorine or 0
            fc_needed = max(0, shock_target - current_fc)
            shock_oz = fc_needed * gal_factor * 10  # liquid chlorine
            results.append({
                "parameter": "Combined Chlorine",
                "current": combined_chlorine,
                "target": "< 0.5 ppm",
                "status": "high",
                "chemical": "Liquid chlorine (breakpoint shock)",
                "amount": f"{shock_oz:.1f} oz",
                "amount_value": round(shock_oz, 1),
                "unit": "oz",
                "notes": f"Breakpoint target: {shock_target:.1f} ppm FC. Add at dusk, run pump overnight.",
            })
        else:
            results.append({
                "parameter": "Combined Chlorine",
                "current": combined_chlorine,
                "target": "< 0.5 ppm",
                "status": "ok",
                "chemical": None,
                "amount": None,
            })

    # Total alkalinity
    if alkalinity is not None:
        if alkalinity < 80:
            diff = 100 - alkalinity
            # Sodium bicarbonate: 1.5 lbs per 10k gallons per 10 ppm
            bicarb_lbs = diff / 10 * gal_factor * 1.5
            results.append({
                "parameter": "Total Alkalinity",
                "current": alkalinity,
                "target": "80 – 120 ppm",
                "status": "low",
                "chemical": "Sodium bicarbonate (baking soda)",
                "amount": f"{bicarb_lbs:.1f} lbs",
                "amount_value": round(bicarb_lbs, 1),
                "unit": "lbs",
                "notes": "Add max 2 lbs per 10k gallons at a time. Retest after 6 hours.",
            })
        elif alkalinity > 120:
            diff = alkalinity - 100
            acid_oz = diff / 10 * gal_factor * 26
            results.append({
                "parameter": "Total Alkalinity",
                "current": alkalinity,
                "target": "80 – 120 ppm",
                "status": "high",
                "chemical": "Muriatic acid (31.45%)",
                "amount": f"{acid_oz:.1f} oz",
                "amount_value": round(acid_oz, 1),
                "unit": "oz",
                "notes": "This will also lower pH. Add in deep end with pump running. Retest after 4 hours.",
            })
        else:
            results.append({
                "parameter": "Total Alkalinity",
                "current": alkalinity,
                "target": "80 – 120 ppm",
                "status": "ok",
                "chemical": None,
                "amount": None,
            })

    # Calcium hardness
    if calcium_hardness is not None:
        if calcium_hardness < 200:
            diff = 300 - calcium_hardness
            # Calcium chloride: 1.2 lbs per 10k gallons per 10 ppm
            calcium_lbs = diff / 10 * gal_factor * 1.2
            results.append({
                "parameter": "Calcium Hardness",
                "current": calcium_hardness,
                "target": "200 – 400 ppm",
                "status": "low",
                "chemical": "Calcium chloride",
                "amount": f"{calcium_lbs:.1f} lbs",
                "amount_value": round(calcium_lbs, 1),
                "unit": "lbs",
                "notes": "Pre-dissolve in bucket of water. Add slowly to avoid cloudiness.",
            })
        elif calcium_hardness > 400:
            results.append({
                "parameter": "Calcium Hardness",
                "current": calcium_hardness,
                "target": "200 – 400 ppm",
                "status": "high",
                "chemical": "Partial drain and refill",
                "amount": None,
                "notes": "No chemical lowers calcium. Drain ~1/3 and refill with fresh water.",
            })
        else:
            results.append({
                "parameter": "Calcium Hardness",
                "current": calcium_hardness,
                "target": "200 – 400 ppm",
                "status": "ok",
                "chemical": None,
                "amount": None,
            })

    # Cyanuric acid (stabilizer)
    if cyanuric_acid is not None:
        if cyanuric_acid < 30:
            diff = 50 - cyanuric_acid
            # Stabilizer: 13 oz per 10k gallons per 10 ppm
            cya_oz = diff / 10 * gal_factor * 13
            results.append({
                "parameter": "Cyanuric Acid (CYA)",
                "current": cyanuric_acid,
                "target": "30 – 80 ppm",
                "status": "low",
                "chemical": "Cyanuric acid (stabilizer)",
                "amount": f"{cya_oz:.1f} oz",
                "amount_value": round(cya_oz, 1),
                "unit": "oz",
                "notes": "Add to skimmer basket or dissolve in sock in pump basket. Takes 3-5 days to fully dissolve.",
            })
        elif cyanuric_acid > 80:
            results.append({
                "parameter": "Cyanuric Acid (CYA)",
                "current": cyanuric_acid,
                "target": "30 – 80 ppm",
                "status": "high",
                "chemical": "Partial drain and refill",
                "amount": None,
                "notes": "No chemical lowers CYA. Drain and refill. Above 100 ppm, chlorine becomes ineffective.",
            })
        else:
            results.append({
                "parameter": "Cyanuric Acid (CYA)",
                "current": cyanuric_acid,
                "target": "30 – 80 ppm",
                "status": "ok",
                "chemical": None,
                "amount": None,
            })

    # Phosphates
    if phosphates is not None:
        if phosphates > 300:
            results.append({
                "parameter": "Phosphates",
                "current": phosphates,
                "target": "< 300 ppb",
                "status": "high",
                "chemical": "Phosphate remover (lanthanum-based)",
                "amount": "Per product label",
                "notes": f"At {phosphates} ppb, may need multiple treatments. Run filter continuously for 48 hours after treatment.",
            })
        else:
            results.append({
                "parameter": "Phosphates",
                "current": phosphates,
                "target": "< 300 ppb",
                "status": "ok",
                "chemical": None,
                "amount": None,
            })

    issues = [r for r in results if r.get("status") not in ("ok", None)]
    ok_count = len([r for r in results if r.get("status") == "ok"])

    return {
        "pool_gallons": pool_gallons,
        "readings_analyzed": len(results),
        "issues_found": len(issues),
        "all_ok": len(issues) == 0 and ok_count > 0,
        "dosing": results,
    }
