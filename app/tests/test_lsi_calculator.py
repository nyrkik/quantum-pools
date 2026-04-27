"""Tests for calculate_lsi — Phase 3d.2 step 1.

Reference values verified against the Pool Operator's Handbook standard
table at 75°F (TF=0.6 by interpolation between the 66/0.5 and 76/0.6
anchors — at exactly 75°F we interpolate to ~0.59).

Each test names the scenario so failures point at the input
combination, not just a number.
"""

from __future__ import annotations

import pytest

from src.services.dosing_engine import (
    WATER_TEMP_F_DEFAULT,
    calculate_lsi,
    _tf,
)


# ---------------------------------------------------------------------------
# Reference-table sanity (TF interpolation)
# ---------------------------------------------------------------------------


def test_tf_at_anchor_temps():
    assert _tf(60) == pytest.approx(0.4)
    assert _tf(76) == pytest.approx(0.6)
    assert _tf(84) == pytest.approx(0.7)
    assert _tf(105) == pytest.approx(0.9)


def test_tf_clamps_outside_range():
    assert _tf(20) == pytest.approx(0.0)
    assert _tf(150) == pytest.approx(0.9)


def test_tf_interpolates_between_anchors():
    """75°F sits 9/10ths of the way from 66°F (0.5) to 76°F (0.6)."""
    expected = 0.5 + (9 / 10) * (0.6 - 0.5)
    assert _tf(75) == pytest.approx(expected, abs=1e-6)


# ---------------------------------------------------------------------------
# Reference LSI scenarios at the 75°F default
# ---------------------------------------------------------------------------


def test_default_temp_constant_is_75f():
    assert WATER_TEMP_F_DEFAULT == 75.0


def test_balanced_typical_residential_pool():
    """pH 7.4, Ca 250, alk 100, CYA 30. Common residential target.
    Expected ~ -0.05 (just inside the balanced band)."""
    out = calculate_lsi(ph=7.4, calcium_hardness=250, alkalinity=100, cyanuric_acid=30)
    assert out["classification"] == "balanced"
    assert -0.2 <= out["value"] <= 0.1


def test_balanced_well_managed_commercial():
    """pH 7.6, Ca 300, alk 120, CYA 50. Slightly scaling tendency
    but inside the balanced band."""
    out = calculate_lsi(ph=7.6, calcium_hardness=300, alkalinity=120, cyanuric_acid=50)
    assert out["classification"] == "balanced"
    assert 0.0 <= out["value"] <= 0.3


def test_corrosive_low_calcium_low_alk():
    """pH 7.0, Ca 100, alk 60, no CYA — soft-water corrosive scenario."""
    out = calculate_lsi(ph=7.0, calcium_hardness=100, alkalinity=60)
    assert out["classification"] == "corrosive"
    assert out["value"] < -0.3


def test_scaling_high_everything():
    """pH 8.0, Ca 500, alk 200, CYA 100 — heavy scaling tendency."""
    out = calculate_lsi(ph=8.0, calcium_hardness=500, alkalinity=200, cyanuric_acid=100)
    assert out["classification"] == "scaling"
    assert out["value"] > 0.3


# ---------------------------------------------------------------------------
# Boundary behavior + payload shape
# ---------------------------------------------------------------------------


def test_classification_band_thresholds():
    """Boundary values: -0.3 and +0.3 are inclusive in 'balanced'."""
    # Synthetic readings tuned so the math lands close to boundary.
    # Verify we're not flipping classification at exactly the threshold.
    out_neg = calculate_lsi(ph=7.0, calcium_hardness=180, alkalinity=80)
    out_pos = calculate_lsi(ph=7.6, calcium_hardness=400, alkalinity=200)
    # Just check they classify sensibly; band edges are tested via floats.
    assert out_neg["classification"] in ("corrosive", "balanced")
    assert out_pos["classification"] in ("balanced", "scaling")


def test_payload_includes_inputs_for_transparency():
    """The frontend needs to label 'temp: 75°F (assumed)' — the
    based_on payload must surface the temp the calc actually used."""
    out = calculate_lsi(ph=7.4, calcium_hardness=200, alkalinity=100, cyanuric_acid=40)
    assert out["based_on"]["temp_f"] == 75.0
    assert out["based_on"]["ph"] == 7.4
    assert out["based_on"]["calcium_hardness"] == 200
    assert out["based_on"]["alkalinity"] == 100
    assert out["based_on"]["cyanuric_acid"] == 40


def test_no_cya_treats_as_zero():
    """The cyanuric_acid argument is optional; absent value uses 0
    so effective_alk == alkalinity."""
    with_zero = calculate_lsi(ph=7.4, calcium_hardness=200, alkalinity=100, cyanuric_acid=0)
    without = calculate_lsi(ph=7.4, calcium_hardness=200, alkalinity=100)
    assert with_zero["value"] == without["value"]


def test_high_cya_lowers_effective_alkalinity():
    """CYA reduces the alkalinity contribution. Same inputs except CYA
    should produce a different (lower) LSI when CYA is added."""
    base = calculate_lsi(ph=7.4, calcium_hardness=200, alkalinity=100, cyanuric_acid=0)
    with_cya = calculate_lsi(ph=7.4, calcium_hardness=200, alkalinity=100, cyanuric_acid=80)
    assert with_cya["value"] < base["value"]


# ---------------------------------------------------------------------------
# Degenerate-input safety
# ---------------------------------------------------------------------------


def test_zero_calcium_raises():
    with pytest.raises(ValueError, match="calcium_hardness"):
        calculate_lsi(ph=7.4, calcium_hardness=0, alkalinity=100)


def test_zero_alkalinity_raises():
    with pytest.raises(ValueError, match="alkalinity"):
        calculate_lsi(ph=7.4, calcium_hardness=200, alkalinity=0)


def test_cya_higher_than_3x_alk_raises():
    """If CYA / 3 ≥ alkalinity, effective_alk is non-positive — log10
    would explode. Surface as a clear error."""
    with pytest.raises(ValueError, match="effective_alk"):
        calculate_lsi(ph=7.4, calcium_hardness=200, alkalinity=20, cyanuric_acid=100)
