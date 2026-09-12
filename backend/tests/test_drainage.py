"""
tests/test_drainage.py
--------------------------
Run with: pytest backend/tests/test_drainage.py -v
Pure-function module, no app/DB fixture needed.
"""

import pytest
from flood_engine.drainage import (
    compute_effective_capacity,
    aggregate_zone_capacity,
    compute_drainage_utilization,
)


def test_effective_capacity_no_blockage():
    assert compute_effective_capacity(5.0, 0) == 5.0


def test_effective_capacity_full_blockage():
    assert compute_effective_capacity(5.0, 100) == 0.0


def test_effective_capacity_partial_blockage():
    assert compute_effective_capacity(5.0, 40) == 3.0


def test_effective_capacity_clamps_blockage_over_100():
    assert compute_effective_capacity(5.0, 150) == 0.0


def test_effective_capacity_rejects_negative_normal_capacity():
    with pytest.raises(ValueError):
        compute_effective_capacity(-1, 10)


def test_aggregate_zone_capacity_sums_and_ignores_none():
    assert aggregate_zone_capacity([1.0, 2.0, None, 1.5]) == 4.5


def test_aggregate_zone_capacity_empty_list_is_zero():
    assert aggregate_zone_capacity([]) == 0.0


def test_utilization_normal_case():
    assert compute_drainage_utilization(2.0, 4.0) == 50.0


def test_utilization_can_exceed_100_when_overloaded():
    assert compute_drainage_utilization(6.0, 4.0) == 150.0


def test_utilization_zero_capacity_with_runoff_is_flagged_high():
    assert compute_drainage_utilization(2.0, 0) == 1000.0


def test_utilization_zero_capacity_zero_runoff_is_zero():
    assert compute_drainage_utilization(0, 0) == 0.0
