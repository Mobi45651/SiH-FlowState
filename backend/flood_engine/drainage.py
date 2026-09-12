"""
flood_engine/drainage.py
----------------------------
Turns a drain's nominal design capacity into its EFFECTIVE capacity given
an estimated blockage percentage, and compares that against runoff to
produce a utilization percentage.

    effective_capacity = normal_capacity * (1 - blockage_percent / 100)
    utilization_pct    = (runoff_m3s / effective_capacity) * 100

Assumptions & limitations:
- Blockage percentage is either a rule-based estimate (Phase 7) or a demo
  slider value -- there is no real sensor behind it in this prototype.
  Treat effective_capacity as an ESTIMATE, not a measurement.
- A zone's total drainage capacity is modelled as the simple SUM of its
  drains' effective capacities. Real networks have topology (which drain
  serves which sub-area, pipe routing, overflow paths) that this ignores.
- utilization_pct is deliberately UNCAPPED (can exceed 100%) so the flood
  engine can tell "just at capacity" apart from "catastrophically
  overwhelmed" -- callers that want a bounded percentage for display
  should clamp it themselves (e.g. min(utilization_pct, 100) for a
  progress bar).

Connects to:
- models/drain.py, models/drain_reading.py -> supply normal_capacity_m3s
  and blockage_percent
- flood_engine/accumulation.py -> consumes effective_capacity to compute
  excess_flow against runoff.py's output
- flood_engine/risk.py (Phase 6) -> uses utilization_pct as an
  explainability factor
"""


def compute_effective_capacity(normal_capacity_m3s: float, blockage_percent: float) -> float:
    if normal_capacity_m3s < 0:
        raise ValueError("normal_capacity_m3s cannot be negative.")
    blockage_percent = max(0.0, min(100.0, blockage_percent))
    return round(normal_capacity_m3s * (1 - blockage_percent / 100.0), 4)


def aggregate_zone_capacity(drain_capacities_m3s: list) -> float:
    """Sums the effective capacities of every drain serving a zone. Returns
    0.0 for a zone with no drains recorded -- callers must treat that as
    "no drainage data available", never silently as infinite capacity."""
    return round(sum(c for c in drain_capacities_m3s if c is not None), 4)


def compute_drainage_utilization(runoff_m3s: float, effective_capacity_m3s: float) -> float:
    """Returns a percentage. If effective_capacity is 0 (fully blocked, or
    no drains at all) and there is any runoff, utilization is reported as a
    large fixed value (1000%) rather than raising ZeroDivisionError or
    returning infinity, both of which are awkward to serialize to JSON."""
    if effective_capacity_m3s <= 0:
        return 1000.0 if runoff_m3s > 0 else 0.0
    return round((runoff_m3s / effective_capacity_m3s) * 100, 2)
