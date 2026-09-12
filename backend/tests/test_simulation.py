"""
tests/test_simulation.py
----------------------------
Run with: pytest backend/tests/test_simulation.py -v
"""

from extensions import db
from models import Zone, Drain
from services.simulation_service import run_simulation


def make_zone(code="ZS01"):
    zone = Zone(
        zone_code=code, name=f"Sim {code}", latitude=19.1, longitude=72.85,
        elevation_m=200, slope_percent=2, impervious_surface_percent=75,
        area_km2=2.0, historical_flood_frequency="LOW",
    )
    db.session.add(zone)
    db.session.commit()
    return zone


def add_drain(zone, capacity=5.0):
    drain = Drain(drain_code=f"{zone.zone_code}-D01", zone_id=zone.id, latitude=19.1,
                   longitude=72.85, normal_capacity_m3s=capacity, condition="GOOD", status="NORMAL")
    db.session.add(drain)
    db.session.commit()
    return drain


def test_run_simulation_returns_baseline_and_simulated(app):
    zone = make_zone()
    add_drain(zone)

    result = run_simulation(zone, rainfall_mm_per_hour=80, duration_hours=2, drainage_blockage_percent=40)

    assert result["zone_id"] == zone.id
    assert "baseline" in result and "simulated" in result
    assert result["simulated"]["risk_category"] in ("LOW", "MODERATE", "HIGH", "SEVERE")
    assert 0 <= result["simulated"]["flood_probability"] <= 1


def test_run_simulation_persists_result(app):
    from models import SimulationResult

    zone = make_zone("ZS02")
    add_drain(zone)
    result = run_simulation(zone, rainfall_mm_per_hour=60, duration_hours=1, drainage_blockage_percent=20)

    saved = SimulationResult.query.get(result["simulation_id"])
    assert saved is not None
    assert saved.is_demo is True
    assert saved.drainage_blockage_percent == 20


def test_heavier_scenario_produces_more_water_depth(app):
    zone = make_zone("ZS03")
    add_drain(zone, capacity=5.0)

    light = run_simulation(zone, rainfall_mm_per_hour=10, duration_hours=1, drainage_blockage_percent=0)
    heavy = run_simulation(zone, rainfall_mm_per_hour=100, duration_hours=3, drainage_blockage_percent=70)

    assert heavy["simulated"]["water_depth_cm"] > light["simulated"]["water_depth_cm"]
    assert heavy["simulated"]["affected_area_percent"] >= light["simulated"]["affected_area_percent"]


def test_zone_with_no_drains_does_not_crash(app):
    zone = make_zone("ZS04")
    result = run_simulation(zone, rainfall_mm_per_hour=50, duration_hours=1, drainage_blockage_percent=30)
    assert result["simulated"]["drainage_capacity_m3s"] == 0.0
