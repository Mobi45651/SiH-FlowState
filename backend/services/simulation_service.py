"""
services/simulation_service.py
---------------------------------
Implements the What-If Simulation feature: a user picks a zone and
proposes a hypothetical rainfall_mm_per_hour / duration_hours /
drainage_blockage_percent, and this returns what the flood engine predicts
under those exact conditions -- alongside the zone's REAL current
prediction, so the frontend can show a BEFORE/AFTER comparison (per the
spec's slider UI).

The simulated blockage_percent is applied UNIFORMLY to every drain in the
zone, overriding whatever their real current blockage readings are --
that's the point of a what-if tool. Every simulation is persisted to
SimulationResult with is_demo=True, since by definition these are
hypothetical, not measured, conditions.

Connects to:
- flood_engine/risk.py -> evaluate_zone_risk() runs the actual scenario
- services/nowcast_engine.py -> supplies the REAL "baseline" for comparison
- models/simulation_result.py -> where every run is stored
- routes/simulation_routes.py -> exposes this over POST /api/simulation
"""

from extensions import db
from models import Zone, Drain, SimulationResult
from flood_engine.risk import evaluate_zone_risk

# Above this simulated water depth, the whole zone is treated as affected
# (100%) -- a simple linear proxy, not a real inundation-extent model.
FULL_INUNDATION_DEPTH_CM = 50.0


def _affected_area(zone: Zone, water_depth_cm: float) -> dict:
    """Rough, explicitly-approximate estimate of how much of the zone is
    affected, linear in water depth up to FULL_INUNDATION_DEPTH_CM. A real
    system would use a DEM (elevation model) to compute actual inundation
    extent -- this prototype doesn't have one."""
    affected_percent = round(min(100.0, (water_depth_cm / FULL_INUNDATION_DEPTH_CM) * 100), 1)
    affected_km2 = round(zone.area_km2 * (affected_percent / 100), 3)
    return {"affected_area_percent": affected_percent, "affected_area_km2": affected_km2}


def run_simulation(zone: Zone, rainfall_mm_per_hour: float, duration_hours: float, drainage_blockage_percent: float) -> dict:
    """Runs the hypothetical scenario and returns it alongside the zone's
    real current ("baseline") prediction. Persists the simulated result."""
    from services.nowcast_engine import build_zone_nowcast

    drains = Drain.query.filter_by(zone_id=zone.id).all()
    capacities = [d.normal_capacity_m3s for d in drains]
    # Uniform hypothetical blockage across every drain -- the whole point
    # of the what-if tool is to ask "what if blockage were X%?"
    blockages = [drainage_blockage_percent] * len(drains)

    simulated = evaluate_zone_risk(
        rainfall_intensity_mm_per_hr=rainfall_mm_per_hour,
        area_km2=zone.area_km2,
        impervious_surface_percent=zone.impervious_surface_percent,
        drain_normal_capacities_m3s=capacities,
        drain_blockage_percents=blockages,
        previous_water_depth_cm=0.0,  # simulations start from a clean baseline, not real current depth
        duration_minutes=duration_hours * 60,
    )
    simulated.update(_affected_area(zone, simulated["water_depth_cm"]))

    baseline_nowcast = build_zone_nowcast(zone, ensure_fresh_data=False)
    baseline = baseline_nowcast["forecast"][0]

    result_row = SimulationResult(
        zone_id=zone.id,
        rainfall_mm_per_hour=rainfall_mm_per_hour,
        duration_hours=duration_hours,
        drainage_blockage_percent=drainage_blockage_percent,
        runoff_m3s=simulated["runoff_m3s"],
        excess_flow_m3s=simulated["excess_flow_m3s"],
        water_depth_cm=simulated["water_depth_cm"],
        flood_probability=simulated["flood_probability"],
        risk_category=simulated["risk_category"],
        is_demo=True,
    )
    result_row.set_input_params({
        "zone_id": zone.id,
        "rainfall_mm_per_hour": rainfall_mm_per_hour,
        "duration_hours": duration_hours,
        "drainage_blockage_percent": drainage_blockage_percent,
    })
    db.session.add(result_row)
    db.session.commit()

    return {
        "zone_id": zone.id,
        "zone_code": zone.zone_code,
        "zone_name": zone.name,
        "baseline": baseline,
        "simulated": simulated,
        "simulation_id": result_row.id,
    }
