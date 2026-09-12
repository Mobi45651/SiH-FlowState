"""
tests/test_runoff.py
-----------------------
Run with: pytest backend/tests/test_runoff.py -v
No app/DB fixture needed -- runoff.py is a pure-function module.
"""

import pytest
from flood_engine.runoff import (
    compute_runoff_coefficient,
    compute_runoff,
    compute_cumulative_rainfall,
)


def test_coefficient_fully_impervious():
    assert compute_runoff_coefficient(100) == 0.90


def test_coefficient_fully_pervious():
    assert compute_runoff_coefficient(0) == 0.20


def test_coefficient_blend_is_linear():
    assert compute_runoff_coefficient(50) == pytest.approx(0.55, abs=0.001)


def test_coefficient_clamps_out_of_range_input():
    assert compute_runoff_coefficient(150) == compute_runoff_coefficient(100)
    assert compute_runoff_coefficient(-20) == compute_runoff_coefficient(0)


def test_compute_runoff_basic():
    result = compute_runoff(rainfall_intensity_mm_per_hr=20, area_km2=2.0, impervious_surface_percent=80)
    assert result["runoff_m3s"] > 0
    assert result["runoff_coefficient"] == compute_runoff_coefficient(80)
    assert result["method"] == "rational_method"


def test_compute_runoff_zero_rain_gives_zero_runoff():
    result = compute_runoff(0, 2.0, 80)
    assert result["runoff_m3s"] == 0


def test_compute_runoff_scales_with_area():
    small = compute_runoff(20, 1.0, 80)
    large = compute_runoff(20, 2.0, 80)
    assert large["runoff_m3s"] == pytest.approx(small["runoff_m3s"] * 2, rel=1e-6)


def test_compute_runoff_rejects_negative_rainfall():
    with pytest.raises(ValueError):
        compute_runoff(-5, 2.0, 80)


def test_compute_runoff_rejects_nonpositive_area():
    with pytest.raises(ValueError):
        compute_runoff(10, 0, 80)


def test_cumulative_rainfall_sums_and_ignores_none():
    assert compute_cumulative_rainfall([1.0, 2.5, None, 3.0]) == 6.5


def test_cumulative_rainfall_empty_list_is_zero():
    assert compute_cumulative_rainfall([]) == 0.0
