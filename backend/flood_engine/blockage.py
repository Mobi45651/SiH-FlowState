"""
flood_engine/blockage.py
----------------------------
Estimates a drain's blockage percentage and a NORMAL/WARNING/CRITICAL
status without any real sensor network -- this prototype has no live
water-level or independent outflow sensors (see the module note in
drain_reading.py). Instead, blockage is estimated from three plausible,
explainable signals:

1. Declared physical CONDITION (GOOD/FAIR/POOR) -- a maintenance record,
   not a live reading, but a real and honest signal.
2. Days since last inspection -- risk accrues the longer a drain goes
   unchecked, a standard municipal-maintenance heuristic.
3. (Optional) a flow-deficit signal: if a drain's current_flow reading is
   well below its normal capacity, that's WEAK supporting evidence of an
   obstruction -- weak because low flow could just as easily mean it
   isn't raining. Given without rainfall context, this signal is
   deliberately weighted lightly.

HONESTY NOTE: this is a coarse, rule-based heuristic for a student
prototype -- NOT a calibrated predictive model and NOT a substitute for
physical inspection. A real deployment would use actual flow/water-level
sensors and historical maintenance records to train something better.

Connects to:
- services/blockage_detector.py -> calls estimate_blockage() to write new
  DrainReading rows on a schedule (flask --app app detect-blockages)
- routes/drain_routes.py         -> simulate-blockage also reuses
  categorize_drain_status() for consistent status labeling
- flood_engine/drainage.py       -> compute_effective_capacity() is reused
  once a blockage_percent (estimated or simulated) is known
"""

CONDITION_BASE_RISK = {"GOOD": 5.0, "FAIR": 20.0, "POOR": 40.0}
DEFAULT_CONDITION_RISK = 10.0  # used if condition is missing/unrecognized

MAX_INSPECTION_PENALTY = 25.0   # cap on the "long overdue inspection" risk boost
INSPECTION_PENALTY_PER_DAYS = 30  # +1 percentage point of risk per this many days

MAX_FLOW_DEFICIT_PENALTY = 20.0  # cap on the flow-deficit boost


def categorize_drain_status(blockage_percent: float) -> str:
    """Single source of truth for the NORMAL/WARNING/CRITICAL thresholds,
    used by both the estimator below and the demo blockage slider so the
    two paths can never disagree about what "WARNING" means."""
    if blockage_percent < 20:
        return "NORMAL"
    if blockage_percent < 50:
        return "WARNING"
    return "CRITICAL"


def estimate_blockage(
    condition: str,
    days_since_inspection: float | None = None,
    current_flow_m3s: float | None = None,
    normal_capacity_m3s: float | None = None,
) -> dict:
    """Returns {estimated_blockage_percent, blockage_probability, status}.

    All inputs except `condition` are optional -- a brand-new drain with no
    reading history yet and an unknown inspection date still gets a
    reasonable (low-confidence, condition-only) estimate rather than
    crashing on missing data.
    """
    condition_key = (condition or "GOOD").upper()
    base_risk = CONDITION_BASE_RISK.get(condition_key, DEFAULT_CONDITION_RISK)

    inspection_penalty = 0.0
    if days_since_inspection is not None and days_since_inspection > 0:
        inspection_penalty = min(days_since_inspection / INSPECTION_PENALTY_PER_DAYS, MAX_INSPECTION_PENALTY)

    flow_penalty = 0.0
    if current_flow_m3s is not None and normal_capacity_m3s and normal_capacity_m3s > 0:
        ratio = current_flow_m3s / normal_capacity_m3s
        # Flow well under half of design capacity is treated as weak
        # supporting evidence of an obstruction -- see module docstring.
        flow_penalty = max(0.0, 0.5 - ratio) * (MAX_FLOW_DEFICIT_PENALTY / 0.5)

    estimated_blockage_percent = min(max(base_risk + inspection_penalty + flow_penalty, 0.0), 95.0)
    # Saturates to full confidence around 80% estimated blockage -- beyond
    # that, additional estimated severity doesn't meaningfully add
    # confidence that SOME blockage exists.
    blockage_probability = round(min(estimated_blockage_percent / 80.0, 1.0), 3)

    return {
        "estimated_blockage_percent": round(estimated_blockage_percent, 1),
        "blockage_probability": blockage_probability,
        "status": categorize_drain_status(estimated_blockage_percent),
    }
