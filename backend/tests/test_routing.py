"""
tests/test_routing.py
------------------------
No app/DB fixture needed -- flood_engine/routing.py is pure functions.

Run with: pytest backend/tests/test_routing.py -v
"""

import pytest
from flood_engine.routing import (
    haversine_distance_km,
    estimate_road_distance_km,
    estimate_travel_time_minutes,
    worst_risk,
    compute_safe_route,
    build_route_explanation,
)


def test_haversine_distance_zero_for_same_point():
    assert haversine_distance_km(21.1, 79.1, 21.1, 79.1) == 0


def test_haversine_distance_matches_known_approximation():
    # Roughly 1 degree of latitude is ~111km
    d = haversine_distance_km(0.0, 0.0, 1.0, 0.0)
    assert 110 < d < 112


def test_estimate_road_distance_exceeds_straight_line():
    straight = 10.0
    road = estimate_road_distance_km(straight)
    assert road > straight


def test_estimate_travel_time_positive_and_scales_with_distance():
    short_time = estimate_travel_time_minutes(5.0)
    long_time = estimate_travel_time_minutes(20.0)
    assert short_time > 0
    assert long_time > short_time


def test_estimate_travel_time_rejects_non_positive_speed():
    with pytest.raises(ValueError):
        estimate_travel_time_minutes(10.0, avg_speed_kmh=0)


def test_worst_risk_empty_defaults_to_low():
    assert worst_risk([]) == "LOW"


def test_worst_risk_picks_the_worst():
    assert worst_risk(["LOW", "MODERATE"]) == "MODERATE"
    assert worst_risk(["LOW", "SEVERE", "HIGH"]) == "SEVERE"
    assert worst_risk(["MODERATE", "MODERATE"]) == "MODERATE"


def test_compute_safe_route_no_detour_when_nothing_avoided():
    distance, duration = compute_safe_route(10.0, 24.0, 0)
    assert (distance, duration) == (10.0, 24.0)


def test_compute_safe_route_adds_penalty_per_segment():
    base_distance, base_duration = 10.0, 24.0
    d1, t1 = compute_safe_route(base_distance, base_duration, 1)
    d3, t3 = compute_safe_route(base_distance, base_duration, 3)
    assert d1 > base_distance and t1 > base_duration
    assert d3 > d1 and t3 > t1


def test_build_route_explanation_no_detour():
    text = build_route_explanation(10.0, 10.0, 0)
    assert "No high-risk" in text


def test_build_route_explanation_with_detour_mentions_count_and_extra_distance():
    text = build_route_explanation(10.0, 12.4, 3)
    assert "3" in text
    assert "longer" in text
    assert "2.4" in text
