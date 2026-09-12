"""
services/alert_service.py
-----------------------------
Automatically generates alerts when any of these thresholds are crossed
(per the spec):
  - flood probability exceeds a threshold
  - drainage capacity is exceeded (utilization > 100%)
  - blockage probability becomes high
  - predicted water depth exceeds a threshold

Re-running generation for a zone RESOLVES that zone's previous active
alerts of the same type before creating a fresh one -- this keeps the
alerts table representing current conditions instead of accumulating
duplicates every time this is called (matches the idempotent-refresh
pattern used throughout the backend).

Connects to:
- services/nowcast_engine.py -> supplies the current prediction per zone
- models/alert.py, models/drain_reading.py -> what's read/written
- routes/alert_routes.py -> exposes this over GET /api/alerts
- app.py -> `flask --app app generate-alerts` runs this for every zone
"""

from datetime import datetime, timezone

from extensions import db
from services.db_lock import DB_WRITE_LOCK
from models import Zone, Drain, Alert

# --- Alert thresholds (all explicit, all in one place) ---
FLOOD_PROBABILITY_THRESHOLD = 0.5       # matches risk.py's HIGH cutoff
DRAINAGE_UTILIZATION_THRESHOLD_PCT = 100.0
BLOCKAGE_PROBABILITY_THRESHOLD = 0.5
WATER_DEPTH_THRESHOLD_CM = 15.0

SEVERITY_BY_RISK = {"LOW": "LOW", "MODERATE": "MODERATE", "HIGH": "HIGH", "SEVERE": "SEVERE"}


def _resolve_existing_alerts(zone_id: int, alert_type: str, drain_id: int | None = None) -> None:
    query = Alert.query.filter_by(zone_id=zone_id, alert_type=alert_type, status="active")
    if drain_id is not None:
        query = query.filter_by(drain_id=drain_id)
    for alert in query.all():
        alert.status = "resolved"


def _time_to_critical_minutes(forecast_steps: list) -> int | None:
    """Looks ahead through the zone's own nowcast steps for the first one
    that reaches SEVERE, and returns its offset in minutes. None if the
    3-hour horizon never reaches SEVERE."""
    for step in forecast_steps:
        if step["risk_category"] == "SEVERE":
            return step["offset_minutes"]
    return None


def _generate_alerts_for_zone_locked(zone: Zone) -> list:
    """Checks all thresholds for one zone and creates/resolves alerts
    accordingly. Returns the list of alerts newly created (not the full
    active set -- see GET /api/alerts for that)."""
    from services.nowcast_engine import build_zone_nowcast

    nowcast = build_zone_nowcast(zone, ensure_fresh_data=False)
    now_step = nowcast["forecast"][0]
    created = []

    # --- Flood risk / probability ---
    _resolve_existing_alerts(zone.id, "FLOOD_RISK")
    if now_step["flood_probability"] >= FLOOD_PROBABILITY_THRESHOLD:
        time_to_critical = _time_to_critical_minutes(nowcast["forecast"])
        alert = Alert(
            zone_id=zone.id,
            alert_type="FLOOD_RISK",
            severity=SEVERITY_BY_RISK.get(now_step["risk_category"], "HIGH"),
            message=(
                f"Flood probability in {zone.name} is {round(now_step['flood_probability'] * 100)}% "
                f"({now_step['risk_category']})."
            ),
            recommended_action="Avoid low-lying roads in this zone; monitor for updates.",
            time_to_critical_minutes=time_to_critical,
            status="active",
        )
        db.session.add(alert)
        created.append(alert)

    # --- 0-3 hour forecast risk ---
    # Alert before the risk becomes current. The nowcast has 7 steps from
    # NOW through +3 hours, so this provides an explicit early-warning path.
    _resolve_existing_alerts(zone.id, "FORECAST_RISK")
    forecast_risk_steps = [
        step for step in nowcast["forecast"]
        if 0 < step["offset_minutes"] <= 180
        and step["risk_category"] in ("HIGH", "SEVERE")
    ]
    if forecast_risk_steps:
        first_forecast_risk = forecast_risk_steps[0]
        alert = Alert(
            zone_id=zone.id,
            alert_type="FORECAST_RISK",
            severity=first_forecast_risk["risk_category"],
            message=(
                f"{zone.name}: {first_forecast_risk['risk_category']} flood risk is "
                f"forecast in {first_forecast_risk['offset_minutes']} minutes."
            ),
            recommended_action="Use the 3-hour forecast to avoid exposed roads and prepare an alternate route.",
            time_to_critical_minutes=first_forecast_risk["offset_minutes"],
            status="active",
        )
        db.session.add(alert)
        created.append(alert)

    # --- Drainage overload ---
    _resolve_existing_alerts(zone.id, "DRAINAGE_OVERLOAD")
    if now_step["drainage_utilization_pct"] > DRAINAGE_UTILIZATION_THRESHOLD_PCT:
        alert = Alert(
            zone_id=zone.id,
            alert_type="DRAINAGE_OVERLOAD",
            severity="HIGH" if now_step["drainage_utilization_pct"] < 200 else "SEVERE",
            message=(
                f"Drainage utilization in {zone.name} is "
                f"{round(now_step['drainage_utilization_pct'])}% of capacity."
            ),
            recommended_action="Runoff exceeds drainage capacity -- expect water accumulation.",
            status="active",
        )
        db.session.add(alert)
        created.append(alert)

    # --- Water depth ---
    _resolve_existing_alerts(zone.id, "WATER_DEPTH")
    if now_step["water_depth_cm"] > WATER_DEPTH_THRESHOLD_CM:
        alert = Alert(
            zone_id=zone.id,
            alert_type="WATER_DEPTH",
            severity=SEVERITY_BY_RISK.get(now_step["risk_category"], "HIGH"),
            message=f"Predicted water depth in {zone.name} is {now_step['water_depth_cm']} cm.",
            recommended_action="Roads in this zone may become impassable.",
            status="active",
        )
        db.session.add(alert)
        created.append(alert)

    # --- Per-drain blockage ---
    for drain in Drain.query.filter_by(zone_id=zone.id).all():
        _resolve_existing_alerts(zone.id, "DRAIN_BLOCKAGE", drain_id=drain.id)
        latest_reading = drain.readings.first()
        if latest_reading and latest_reading.blockage_probability >= BLOCKAGE_PROBABILITY_THRESHOLD:
            alert = Alert(
                zone_id=zone.id,
                drain_id=drain.id,
                alert_type="DRAIN_BLOCKAGE",
                severity=latest_reading.status,
                message=(
                    f"Drain {drain.drain_code} is estimated {latest_reading.blockage_percent}% "
                    f"blocked (confidence {round(latest_reading.blockage_probability * 100)}%)."
                ),
                recommended_action=f"Inspect drain {drain.drain_code}.",
                status="active",
            )
            db.session.add(alert)
            created.append(alert)

    db.session.commit()
    return created


def generate_alerts_for_zone(zone: Zone) -> list:
    with DB_WRITE_LOCK:
        return _generate_alerts_for_zone_locked(zone)


def generate_alerts_for_all_zones() -> list:
    with DB_WRITE_LOCK:
        created = []
        for zone in Zone.query.order_by(Zone.id).all():
            created.extend(_generate_alerts_for_zone_locked(zone))
        return created
