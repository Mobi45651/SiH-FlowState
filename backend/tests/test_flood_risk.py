"""
tests/test_flood_risk.py
---------------------------
Run with: pytest backend/tests/test_flood_risk.py -v
No app/DB fixture needed -- risk.py only imports config.py (no Flask/DB).
"""

import pytest
from flood_engine.risk import (
    categorize_risk,
    rule_based_flood_probability,
    blend_with_ml_prediction,
    evaluate_zone_risk,
    RULE_BASED_MODEL_VERSION,
)


def test_categorize_risk_thresholds():
    assert categorize_risk(0.0) == "LOW"
    assert categorize_risk(0.24) == "LOW"
    assert categorize_risk(0.25) == "MODERATE"
    assert categorize_risk(0.5) == "HIGH"
    assert categorize_risk(0.75) == "SEVERE"
    assert categorize_risk(1.0) == "SEVERE"


def test_rule_based_probability_increases_with_inputs():
    low = rule_based_flood_probability(drainage_utilization_pct=10, water_depth_cm=0)
    high = rule_based_flood_probability(drainage_utilization_pct=150, water_depth_cm=40)
    assert 0 <= low <= 1
    assert 0 <= high <= 1
    assert high > low


def test_blend_falls_back_to_rule_based_when_ml_missing():
    prob, version = blend_with_ml_prediction(0.42, None)
    assert prob == 0.42
    assert version == RULE_BASED_MODEL_VERSION


def test_blend_combines_both_scores():
    prob, version = blend_with_ml_prediction(rule_based_probability=0.2, ml_probability=0.8, ml_weight=0.6)
    assert version == "rf_v1_blended"
    assert 0.2 < prob < 0.8  # weighted average must land strictly between the two inputs


def test_evaluate_zone_risk_end_to_end_low_rain():
    result = evaluate_zone_risk(
        rainfall_intensity_mm_per_hr=5, area_km2=2.0, impervious_surface_percent=60,
        drain_normal_capacities_m3s=[3.0, 3.0], drain_blockage_percents=[0, 0],
    )
    assert result["risk_category"] in ("LOW", "MODERATE")
    assert result["model_version"] == RULE_BASED_MODEL_VERSION


def test_evaluate_zone_risk_end_to_end_severe_storm():
    result = evaluate_zone_risk(
        rainfall_intensity_mm_per_hr=60, area_km2=2.0, impervious_surface_percent=90,
        drain_normal_capacities_m3s=[3.0, 3.0], drain_blockage_percents=[50, 60],
    )
    assert result["risk_category"] in ("HIGH", "SEVERE")
    assert result["drainage_utilization_pct"] > 100


def test_evaluate_zone_risk_handles_zone_with_no_drains():
    result = evaluate_zone_risk(
        rainfall_intensity_mm_per_hr=30, area_km2=1.5, impervious_surface_percent=80,
        drain_normal_capacities_m3s=[], drain_blockage_percents=[],
    )
    assert result["drainage_capacity_m3s"] == 0.0
    assert result["risk_category"] == "SEVERE"  # any runoff at all overwhelms zero capacity


def test_evaluate_zone_risk_rejects_mismatched_drain_lists():
    with pytest.raises(ValueError):
        evaluate_zone_risk(
            rainfall_intensity_mm_per_hr=10, area_km2=1.0, impervious_surface_percent=50,
            drain_normal_capacities_m3s=[3.0, 3.0], drain_blockage_percents=[0],
        )
