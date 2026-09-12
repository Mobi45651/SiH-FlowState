"""
tests/test_accumulation.py
------------------------------
Run with: pytest backend/tests/test_accumulation.py -v
Pure-function module, no app/DB fixture needed.
"""

from flood_engine.accumulation import (
    compute_excess_flow,
    accumulate_water_depth,
    compute_water_depth_cm,
    MAX_PLAUSIBLE_DEPTH_CM,
)


def test_excess_flow_positive_when_runoff_exceeds_capacity():
    assert compute_excess_flow(6.0, 4.0) == 2.0


def test_excess_flow_negative_when_spare_capacity_available():
    assert compute_excess_flow(2.0, 4.0) == -2.0


def test_water_rises_when_excess_positive():
    depth = accumulate_water_depth(previous_depth_cm=0, excess_flow_m3s=2.0,
                                    duration_minutes=30, zone_area_km2=1.0)
    assert depth > 0


def test_water_recedes_when_excess_negative():
    depth = accumulate_water_depth(previous_depth_cm=10, excess_flow_m3s=-1.0,
                                    duration_minutes=30, zone_area_km2=1.0)
    assert depth < 10


def test_depth_is_floored_at_zero_not_negative():
    depth = accumulate_water_depth(previous_depth_cm=0.5, excess_flow_m3s=-5.0,
                                    duration_minutes=60, zone_area_km2=1.0)
    assert depth == 0.0


def test_depth_is_capped_at_max_plausible():
    depth = accumulate_water_depth(previous_depth_cm=0, excess_flow_m3s=1000.0,
                                    duration_minutes=180, zone_area_km2=0.001)
    assert depth == MAX_PLAUSIBLE_DEPTH_CM


def test_sequential_accumulation_across_timesteps():
    """Simulates a 3-step nowcast: rain builds up, then eases off."""
    depth = 0.0
    depth = accumulate_water_depth(depth, excess_flow_m3s=1.5, duration_minutes=30, zone_area_km2=1.0)
    after_first_burst = depth
    depth = accumulate_water_depth(depth, excess_flow_m3s=1.0, duration_minutes=30, zone_area_km2=1.0)
    after_second_burst = depth
    depth = accumulate_water_depth(depth, excess_flow_m3s=-0.5, duration_minutes=30, zone_area_km2=1.0)
    after_recession = depth

    assert after_first_burst > 0
    assert after_second_burst > after_first_burst
    assert after_recession < after_second_burst


def test_compute_water_depth_cm_matches_zero_start_accumulation():
    depth = compute_water_depth_cm(excess_flow_m3s=2.0, duration_minutes=30, zone_area_km2=1.0)
    expected = accumulate_water_depth(0.0, 2.0, 30, 1.0)
    assert depth == expected
