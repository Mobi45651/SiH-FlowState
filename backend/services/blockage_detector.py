"""
services/blockage_detector.py
---------------------------------
Two operations, both writing a new DrainReading row and syncing the
parent Drain's denormalized `status` field:

1. detect_blockage_for_drain() -- runs the rule-based estimator from
   flood_engine/blockage.py using the drain's condition, inspection age,
   and (if available) its most recent flow reading. This is the "as if we
   had a detection algorithm running on a schedule" path.

2. simulate_blockage_for_drain() -- lets the SIH demo directly SET a
   blockage percentage (the NORMAL -> 10% -> 30% -> 60% walkthrough from
   the spec), writing a row explicitly flagged is_simulated=True so it's
   never confused with a "detected" value.

Connects to:
- flood_engine/blockage.py, flood_engine/drainage.py -> the actual math
- models/drain.py, models/drain_reading.py -> what gets written
- routes/drain_routes.py -> exposes simulate_blockage_for_drain() over HTTP
- app.py -> `flask --app app detect-blockages` runs detect_blockage_for_drain()
  for every drain
"""

from datetime import datetime, date

from extensions import db
from models import Drain, DrainReading
from flood_engine.blockage import estimate_blockage, categorize_drain_status
from flood_engine.drainage import compute_effective_capacity
from utils.time_utils import utc_now


def _days_since(inspection_date) -> float | None:
    if inspection_date is None:
        return None
    if isinstance(inspection_date, datetime):
        inspection_date = inspection_date.date()
    return (date.today() - inspection_date).days


def detect_blockage_for_drain(drain: Drain) -> dict:
    """Runs the rule-based estimator for one drain and persists the result
    as a new (non-simulated) DrainReading."""
    latest_reading = drain.readings.first()
    current_flow = latest_reading.current_flow_m3s if latest_reading else None

    estimate = estimate_blockage(
        condition=drain.condition,
        days_since_inspection=_days_since(drain.last_inspection_date),
        current_flow_m3s=current_flow,
        normal_capacity_m3s=drain.normal_capacity_m3s,
    )
    effective_capacity = compute_effective_capacity(
        drain.normal_capacity_m3s, estimate["estimated_blockage_percent"]
    )

    reading = DrainReading(
        drain_id=drain.id,
        timestamp=utc_now(),
        current_flow_m3s=current_flow if current_flow is not None else effective_capacity,
        blockage_percent=estimate["estimated_blockage_percent"],
        estimated_capacity_m3s=effective_capacity,
        blockage_probability=estimate["blockage_probability"],
        status=estimate["status"],
        is_simulated=False,
    )
    db.session.add(reading)

    drain.status = estimate["status"]
    db.session.commit()

    return {
        "drain_id": drain.id,
        "drain_code": drain.drain_code,
        **estimate,
        "estimated_capacity_m3s": effective_capacity,
    }


def detect_blockage_for_all_drains() -> list:
    return [detect_blockage_for_drain(drain) for drain in Drain.query.all()]


def simulate_blockage_for_drain(drain: Drain, blockage_percent: float) -> dict:
    """Directly SETS a drain's blockage percentage for demo purposes (the
    NORMAL -> 10% -> 30% -> 60% walkthrough). Always written with
    is_simulated=True -- never mistaken for a "detected" estimate."""
    blockage_percent = max(0.0, min(100.0, blockage_percent))
    effective_capacity = compute_effective_capacity(drain.normal_capacity_m3s, blockage_percent)
    status = categorize_drain_status(blockage_percent)

    reading = DrainReading(
        drain_id=drain.id,
        timestamp=utc_now(),
        current_flow_m3s=effective_capacity,  # simulated: assume flow now matches reduced capacity
        blockage_percent=blockage_percent,
        estimated_capacity_m3s=effective_capacity,
        blockage_probability=1.0,  # directly set, not inferred -- full confidence by definition
        status=status,
        is_simulated=True,
    )
    db.session.add(reading)

    drain.status = status
    db.session.commit()

    return {
        "drain_id": drain.id,
        "drain_code": drain.drain_code,
        "estimated_blockage_percent": blockage_percent,
        "estimated_capacity_m3s": effective_capacity,
        "blockage_probability": 1.0,
        "status": status,
        "is_simulated": True,
    }
