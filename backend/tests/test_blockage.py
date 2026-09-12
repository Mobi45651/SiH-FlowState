"""
tests/test_blockage.py
--------------------------
No app/DB fixture needed -- flood_engine/blockage.py is pure functions.

Run with: pytest backend/tests/test_blockage.py -v
"""

from flood_engine.blockage import estimate_blockage, categorize_drain_status


def test_categorize_drain_status_thresholds():
    assert categorize_drain_status(0) == "NORMAL"
    assert categorize_drain_status(19.9) == "NORMAL"
    assert categorize_drain_status(20) == "WARNING"
    assert categorize_drain_status(49.9) == "WARNING"
    assert categorize_drain_status(50) == "CRITICAL"
    assert categorize_drain_status(95) == "CRITICAL"


def test_good_recently_inspected_drain_is_normal():
    result = estimate_blockage("GOOD", days_since_inspection=5)
    assert result["status"] == "NORMAL"
    assert 0 <= result["blockage_probability"] <= 1


def test_poor_long_overdue_drain_is_worse_than_good_recent():
    poor = estimate_blockage("POOR", days_since_inspection=400)
    good = estimate_blockage("GOOD", days_since_inspection=5)
    assert poor["estimated_blockage_percent"] > good["estimated_blockage_percent"]
    assert poor["status"] in ("WARNING", "CRITICAL")


def test_flow_deficit_increases_estimated_blockage():
    low_flow = estimate_blockage("FAIR", days_since_inspection=60, current_flow_m3s=0.5, normal_capacity_m3s=5.0)
    healthy_flow = estimate_blockage("FAIR", days_since_inspection=60, current_flow_m3s=4.5, normal_capacity_m3s=5.0)
    assert low_flow["estimated_blockage_percent"] > healthy_flow["estimated_blockage_percent"]


def test_missing_condition_defaults_without_crashing():
    result = estimate_blockage(None)
    assert result["status"] == "NORMAL"
    assert result["estimated_blockage_percent"] >= 0


def test_estimated_blockage_percent_never_exceeds_95():
    result = estimate_blockage("POOR", days_since_inspection=100000, current_flow_m3s=0.0, normal_capacity_m3s=5.0)
    assert result["estimated_blockage_percent"] <= 95.0


def test_blockage_probability_bounded_0_to_1():
    for condition in ("GOOD", "FAIR", "POOR", None):
        for days in (0, 30, 365, 5000):
            result = estimate_blockage(condition, days_since_inspection=days)
            assert 0.0 <= result["blockage_probability"] <= 1.0
