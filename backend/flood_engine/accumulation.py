"""
flood_engine/accumulation.py
--------------------------------
Estimates how much water builds up (or drains away) in a zone once runoff
exceeds effective drainage capacity.

    excess_flow_m3s = runoff_m3s - effective_capacity_m3s

This is deliberately a PROTOTYPE APPROXIMATION, not a hydrodynamic/hydraulic
model: it does not model actual overland flow, terrain-following ponding
shape, or pipe backup. It answers "roughly how deep might standing water
get if this excess flow continued for this long, assuming a plausible
share of the zone is low-lying enough to pond" -- good enough to rank
zones against each other and to drive the nowcast demo, not good enough
for engineering design decisions. This limitation is repeated in the
README and should be repeated again in the frontend UI copy in Phase 10.

Key assumptions (override via function arguments if you have better data):
- PONDING_AREA_FRACTION: only this fraction of a zone's area is assumed to
  be low-lying enough to actually collect standing water. Default 4%.
- RECESSION_RATE_CM_PER_HOUR: once excess_flow drops to zero or below
  (drainage capacity now exceeds runoff again), accumulated water is
  assumed to recede at this fixed rate via drainage + natural
  infiltration. Default 2.0 cm/hr.
- MAX_PLAUSIBLE_DEPTH_CM: a hard safety cap so a bad/extreme input can't
  produce an absurd, un-demoable number.

Connects to:
- flood_engine/drainage.py -> supplies effective_capacity_m3s
- flood_engine/runoff.py   -> supplies runoff_m3s (via drainage.py's
                               utilization calc)
- nowcast (Phase 5) / risk.py (Phase 6) -> calls accumulate_water_depth()
  once per timestep to build the 7-step (0..3hr) timeline, carrying
  previous_depth_cm forward from one step to the next
"""

PONDING_AREA_FRACTION = 0.04          # fraction of zone area assumed to pond
RECESSION_RATE_CM_PER_HOUR = 2.0      # assumed drain-down rate once excess clears
MAX_PLAUSIBLE_DEPTH_CM = 200.0        # safety cap on the output


def compute_excess_flow(runoff_m3s: float, effective_capacity_m3s: float) -> float:
    """Positive = capacity exceeded (water piling up). Negative = spare
    capacity available. Deliberately NOT clamped to >= 0 here so callers
    can tell how much spare capacity exists -- accumulate_water_depth()
    uses a negative value to drain previously-accumulated water back down.
    """
    return round(runoff_m3s - effective_capacity_m3s, 4)


def _rise_cm(excess_flow_m3s: float, duration_minutes: float, zone_area_km2: float,
             ponding_fraction: float) -> float:
    ponding_area_m2 = zone_area_km2 * 1_000_000 * ponding_fraction
    if ponding_area_m2 <= 0:
        return 0.0
    volume_m3 = excess_flow_m3s * duration_minutes * 60
    depth_m = volume_m3 / ponding_area_m2
    return depth_m * 100  # metres -> centimetres


def accumulate_water_depth(
    previous_depth_cm: float,
    excess_flow_m3s: float,
    duration_minutes: float,
    zone_area_km2: float,
    ponding_fraction: float = PONDING_AREA_FRACTION,
    recession_rate_cm_per_hour: float = RECESSION_RATE_CM_PER_HOUR,
) -> float:
    """Steps water depth forward by one nowcast timestep. Rises while
    excess_flow_m3s > 0, recedes at a fixed rate otherwise. Result is
    floored at 0 and capped at MAX_PLAUSIBLE_DEPTH_CM."""
    if excess_flow_m3s > 0:
        increment = _rise_cm(excess_flow_m3s, duration_minutes, zone_area_km2, ponding_fraction)
        new_depth = previous_depth_cm + increment
    else:
        recession = recession_rate_cm_per_hour * (duration_minutes / 60.0)
        new_depth = previous_depth_cm - recession

    new_depth = max(0.0, min(new_depth, MAX_PLAUSIBLE_DEPTH_CM))
    return round(new_depth, 2)


def compute_water_depth_cm(excess_flow_m3s: float, duration_minutes: float, zone_area_km2: float,
                            ponding_fraction: float = PONDING_AREA_FRACTION) -> float:
    """Convenience wrapper for a single-shot depth estimate starting from
    zero -- used by the what-if Simulation feature (Phase 13), which has no
    "previous" state to build on."""
    return accumulate_water_depth(0.0, excess_flow_m3s, duration_minutes, zone_area_km2, ponding_fraction)
