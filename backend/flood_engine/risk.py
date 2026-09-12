"""
flood_engine/risk.py
-----------------------
Two jobs:

1. Turn physical-model outputs (drainage utilization, water depth) into a
   flood_probability (0-1) and a risk_category (LOW/MODERATE/HIGH/SEVERE).
   This is a RULE-BASED score for now -- documented as such everywhere it
   surfaces (model_version="rule_based_v1"). Phase 6 trains a Random
   Forest and this file will BLEND the rule-based score with the ML
   prediction rather than replacing it outright, so the system degrades
   gracefully if the ML model or its features are ever unavailable.

2. Orchestrate the full runoff -> drainage -> accumulation -> risk
   pipeline in one call (evaluate_zone_risk), since Phases 5 and 13
   (nowcast + simulation) both need to run that exact sequence repeatedly.

Connects to:
- flood_engine/runoff.py, drainage.py, accumulation.py -> the pipeline
  this file orchestrates
- config.py -> RISK_THRESHOLDS (single source of truth for LOW/MODERATE/
  HIGH/SEVERE cutoffs, shared with any frontend copy that needs to match)
- routes/nowcast_routes.py (Phase 5) -> calls evaluate_zone_risk() per
  timestep to build the 7-step forecast
- routes/simulation_routes.py (Phase 13) -> calls evaluate_zone_risk()
  for the single what-if timestep a user configures
- ml/predict.py (Phase 6) -> supplies an ML probability that
  blend_with_ml_prediction() combines with the rule-based score
"""

from config import Config
from flood_engine.runoff import compute_runoff
from flood_engine.drainage import compute_effective_capacity, compute_drainage_utilization
from flood_engine.accumulation import compute_excess_flow, accumulate_water_depth

RULE_BASED_MODEL_VERSION = "rule_based_v1"

# How much weight the utilization-vs-depth rule score gives to each factor.
# Both are normalized to 0-1 before this weighting is applied.
UTILIZATION_WEIGHT = 0.55
DEPTH_WEIGHT = 0.45

# Reference depth (cm) treated as "as bad as it gets" for normalization --
# not a hard ceiling, values above this are simply clamped to 1.0.
SEVERE_DEPTH_REFERENCE_CM = 30.0


def rule_based_flood_probability(drainage_utilization_pct: float, water_depth_cm: float) -> float:
    """A simple, explainable heuristic -- NOT a calibrated statistical
    model. It exists so the system produces a sensible risk number even
    before Phase 6's ML model is trained, and so the pipeline keeps working
    if the ML model is ever missing/fails to load.

    utilization_score: 0 at 0% utilization, 1.0 at 100% utilization,
    allowed to exceed 1.0 slightly for over-capacity drains (capped below).
    depth_score: 0 at 0cm, 1.0 at SEVERE_DEPTH_REFERENCE_CM or deeper.
    """
    utilization_score = min(max(drainage_utilization_pct, 0.0) / 100.0, 1.3)
    depth_score = min(max(water_depth_cm, 0.0) / SEVERE_DEPTH_REFERENCE_CM, 1.0)

    combined = UTILIZATION_WEIGHT * min(utilization_score, 1.0) + DEPTH_WEIGHT * depth_score
    # Small extra bump when a drain is genuinely over capacity (utilization
    # > 100%), since that's a materially worse situation than "at capacity".
    if utilization_score > 1.0:
        combined += 0.1 * (utilization_score - 1.0)

    return round(min(max(combined, 0.0), 1.0), 4)


def blend_with_ml_prediction(rule_based_probability: float, ml_probability: float | None, ml_weight: float = 0.6) -> tuple[float, str]:
    """Combines the rule-based score with an ML prediction, if one is
    available. Returns (blended_probability, model_version_label).

    If ml_probability is None (model not trained yet, or predict.py raised
    an error the caller chose to swallow), falls back to the rule-based
    score alone and labels it accordingly -- the caller should still log
    why ML was unavailable, this function only handles the numbers.
    """
    if ml_probability is None:
        return rule_based_probability, RULE_BASED_MODEL_VERSION

    blended = ml_weight * ml_probability + (1 - ml_weight) * rule_based_probability
    return round(min(max(blended, 0.0), 1.0), 4), "rf_v1_blended"


def categorize_risk(flood_probability: float) -> str:
    """Maps a 0-1 probability to LOW/MODERATE/HIGH/SEVERE using the single
    set of thresholds defined in config.py, so the API, the ML training
    labels, and any frontend copy never disagree on what "HIGH" means."""
    thresholds = Config.RISK_THRESHOLDS
    if flood_probability < thresholds["LOW"]:
        return "LOW"
    if flood_probability < thresholds["MODERATE"]:
        return "MODERATE"
    if flood_probability < thresholds["HIGH"]:
        return "HIGH"
    return "SEVERE"


def evaluate_zone_risk(
    rainfall_intensity_mm_per_hr: float,
    area_km2: float,
    impervious_surface_percent: float,
    drain_normal_capacities_m3s: list,
    drain_blockage_percents: list,
    previous_water_depth_cm: float = 0.0,
    duration_minutes: float = 60.0,
    ml_probability: float | None = None,
) -> dict:
    """Runs the full pipeline for one zone at one timestep:
    runoff -> per-drain effective capacity -> aggregate capacity ->
    utilization -> excess flow -> water depth -> risk probability/category.

    drain_normal_capacities_m3s and drain_blockage_percents must be
    parallel lists (same order, same length) -- one entry per drain in the
    zone. Pass empty lists for a zone with no drains recorded; the
    resulting 0.0 effective capacity is handled explicitly, not silently
    treated as "infinite capacity" or divided-by-zero.
    """
    if len(drain_normal_capacities_m3s) != len(drain_blockage_percents):
        raise ValueError("drain_normal_capacities_m3s and drain_blockage_percents must be the same length")

    runoff_result = compute_runoff(rainfall_intensity_mm_per_hr, area_km2, impervious_surface_percent)

    effective_capacities = [
        compute_effective_capacity(cap, blockage)
        for cap, blockage in zip(drain_normal_capacities_m3s, drain_blockage_percents)
    ]
    total_capacity = round(sum(effective_capacities), 4) if effective_capacities else 0.0

    utilization_pct = compute_drainage_utilization(runoff_result["runoff_m3s"], total_capacity)
    excess_flow = compute_excess_flow(runoff_result["runoff_m3s"], total_capacity)
    water_depth_cm = accumulate_water_depth(
        previous_water_depth_cm, excess_flow, duration_minutes, area_km2
    )

    rule_probability = rule_based_flood_probability(utilization_pct, water_depth_cm)
    flood_probability, model_version = blend_with_ml_prediction(rule_probability, ml_probability)
    risk_category = categorize_risk(flood_probability)

    return {
        "rainfall_mm": rainfall_intensity_mm_per_hr,
        "runoff_m3s": runoff_result["runoff_m3s"],
        "runoff_coefficient": runoff_result["runoff_coefficient"],
        "drainage_capacity_m3s": total_capacity,
        "drainage_utilization_pct": utilization_pct,
        "excess_flow_m3s": excess_flow,
        "water_depth_cm": water_depth_cm,
        "flood_probability": flood_probability,
        "risk_category": risk_category,
        "model_version": model_version,
        "rule_based_probability": rule_probability,  # kept for explainability even after blending
    }
