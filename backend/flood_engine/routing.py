"""
flood_engine/routing.py
--------------------------
Pure math for the Safe Route Planner: distance, travel-time, and detour
estimates, plus how to combine several zones' risk categories into one
route-level risk. No DB or Flask imports, same as the rest of flood_engine
-- independently testable, and this is exactly where the honesty caveats
about "demo routing" belong since it's the actual estimation logic.

ASSUMPTIONS & LIMITATIONS (be upfront about these):
- Distance/time are DEMO ESTIMATES from straight-line (haversine) distance
  scaled by a fixed "road circuity" factor -- NOT real road-network
  routing. A real deployment would use an actual routing engine (OSRM,
  OpenRouteService, Google Directions) that knows the real street graph;
  services/routing_service.py optionally calls OpenRouteService for the
  base distance/time when ROUTING_API_KEY is configured, but the
  flood-aware detour logic here is always this prototype's own estimate,
  regardless of where the base numbers came from.
- The "safe route" detour is a flat per-avoided-segment penalty, not a
  real alternate path computed on a road graph -- this project's seeded
  RouteSegment data isn't a connected, routable graph (see
  utils/demo_data_generator.py), so a real shortest-path algorithm has
  nothing meaningful to run on yet.

Connects to:
- services/routing_service.py -> orchestrates DB lookups (zones/segments
  along the path) and calls these functions to turn that into numbers
- routes/route_routes.py -> exposes POST /api/routes/safe
"""

import math

EARTH_RADIUS_KM = 6371.0

# Straight-line distance underestimates real road distance -- urban road
# networks typically add 20-40% extra distance over a straight line
# ("circuity factor"). 1.35 is a reasonable mid-range assumption for a
# typical Indian city grid, not a measured value for any specific place.
ROAD_CIRCUITY_FACTOR = 1.35

# Assumes typical mixed urban traffic (signals, congestion) rather than
# highway speeds -- a reasonable default for a city-scale demo, not
# calibrated to any specific city's actual traffic data.
AVERAGE_URBAN_SPEED_KMH = 25.0

RISK_ORDER = {"LOW": 0, "MODERATE": 1, "HIGH": 2, "SEVERE": 3}

# Flat per-segment penalty for detouring around one flagged high-risk road
# segment -- a rough estimate, not derived from an actual alternate path
# (see module docstring).
DETOUR_DISTANCE_KM_PER_SEGMENT = 0.8
DETOUR_TIME_MIN_PER_SEGMENT = 3.0


def haversine_distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle (straight-line) distance between two points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c


def estimate_road_distance_km(straight_line_km: float) -> float:
    return round(straight_line_km * ROAD_CIRCUITY_FACTOR, 2)


def estimate_travel_time_minutes(distance_km: float, avg_speed_kmh: float = AVERAGE_URBAN_SPEED_KMH) -> float:
    if avg_speed_kmh <= 0:
        raise ValueError("avg_speed_kmh must be positive")
    return round(distance_km / avg_speed_kmh * 60, 1)


def worst_risk(risk_categories: list) -> str:
    """The single worst risk category among a list -- used to summarize a
    whole route's risk as "as bad as its worst zone/segment". Empty input
    defaults to LOW (no known risk data is not the same as high risk, but
    callers should treat an empty list as low-confidence, not a
    guarantee)."""
    if not risk_categories:
        return "LOW"
    return max(risk_categories, key=lambda c: RISK_ORDER.get(c, 0))


def compute_safe_route(base_distance_km: float, base_duration_min: float, num_segments_avoided: int) -> tuple:
    """Returns (distance_km, duration_min) for the flood-safe alternative.
    With nothing to avoid, the safe route IS the normal route (no
    fabricated detour)."""
    if num_segments_avoided <= 0:
        return base_distance_km, base_duration_min
    extra_km = DETOUR_DISTANCE_KM_PER_SEGMENT * num_segments_avoided
    extra_min = DETOUR_TIME_MIN_PER_SEGMENT * num_segments_avoided
    return round(base_distance_km + extra_km, 2), round(base_duration_min + extra_min, 1)


def build_route_explanation(normal_distance_km: float, safe_distance_km: float, num_segments_avoided: int) -> str:
    if num_segments_avoided <= 0:
        return "No high-risk road segments detected on the direct route."
    extra_km = round(safe_distance_km - normal_distance_km, 1)
    segment_word = "segment" if num_segments_avoided == 1 else "segments"
    return f"Recommended route is {extra_km} km longer but avoids {num_segments_avoided} high-risk road {segment_word}."
