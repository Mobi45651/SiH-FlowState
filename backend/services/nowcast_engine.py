"""
services/nowcast_engine.py
-----------------------------
Builds the 0-3 hour, 7-step flood nowcast (NOW, +30min, +1h, +1.5h, +2h,
+2.5h, +3h) for a zone by looping flood_engine.risk.evaluate_zone_risk()
across each step, carrying accumulated water depth forward from one step
to the next, and persisting every step to flood_predictions.

KEY ASSUMPTIONS (be upfront about these):
- Every nowcast run starts from previous_water_depth_cm = 0.0 -- this
  prototype has no real street-level water-depth sensor, so rather than
  guess a "current" standing-water level, each run treats "NOW" as a
  fresh baseline and projects forward from there using forecast rainfall.
  The "NOW" step's risk still reflects current drainage stress (via
  utilization %), just not a nonzero starting water depth.
- Rainfall input comes from the hourly WeatherForecast rows written by
  services/rainfall_pipeline.py (Phase 3). Because Open-Meteo is
  hourly-resolution, every half-hour step reuses its enclosing hour's
  rainfall rate rather than a true sub-hourly interpolation.
- If a zone has no forecast data at all in the nowcast window, this module
  triggers ingestion automatically (honouring the same live/demo-fallback
  rules as Phase 3) rather than silently nowcasting on zero rainfall.

Connects to:
- flood_engine/risk.py          -> evaluate_zone_risk() runs once per step
- services/rainfall_pipeline.py -> supplies/refreshes the rainfall input
- models/flood_prediction.py    -> where each step's result is stored
- routes/nowcast_routes.py, routes/flood_routes.py -> expose this over HTTP
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from threading import RLock

from extensions import db
from config import Config
from models import Zone, Drain, FloodPrediction, WeatherForecast
from flood_engine.risk import evaluate_zone_risk
from flood_engine.runoff import compute_runoff
from flood_engine.drainage import compute_effective_capacity, aggregate_zone_capacity, compute_drainage_utilization
from ml.feature_engineering import build_feature_vector
from ml.predict import predict_flood_probability
from services.rainfall_pipeline import ingest_zone_rainfall
from services.weather_service import get_weather_for_coordinates
from utils.time_utils import utc_now
from services.db_lock import DB_WRITE_LOCK


def _floor_to_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def _get_hourly_rainfall_map(zone_id: int, start: datetime, end: datetime) -> dict:
    rows = WeatherForecast.query.filter(
        WeatherForecast.zone_id == zone_id,
        WeatherForecast.forecast_time >= start,
        WeatherForecast.forecast_time <= end,
    ).all()
    return {_floor_to_hour(r.forecast_time): r.precipitation_mm for r in rows}


def _rainfall_for_target(hourly_map: dict, target_time: datetime) -> float:
    """No forecast row for this hour bucket -> treated as 0mm, never
    guessed or interpolated from a neighbouring hour."""
    return hourly_map.get(_floor_to_hour(target_time), 0.0)


def _forward_sum(hourly_map: dict, start_time: datetime, hours: int) -> float:
    total = sum(
        hourly_map.get(_floor_to_hour(start_time) + timedelta(hours=h), 0.0)
        for h in range(hours)
    )
    return round(total, 2)


def _forward_max(hourly_map: dict, start_time: datetime, hours: int) -> float:
    values = [
        hourly_map.get(_floor_to_hour(start_time) + timedelta(hours=h), 0.0)
        for h in range(hours)
    ]
    return round(max(values), 2) if values else 0.0


def build_rainfall_windows(hourly_map: dict, target_time: datetime) -> dict:
    """Builds the rainfall_30min/1h/3h/6h/intensity/cumulative features
    used by ml/feature_engineering.py. LIMITATION: these all look FORWARD
    from target_time (anticipated rainfall), not backward at trailing
    observed rainfall -- see the note at the top of ml/feature_engineering.py
    for why (only forecast data is available in this prototype)."""
    current_hour_value = hourly_map.get(_floor_to_hour(target_time), 0.0)
    return {
        "rainfall_30min": current_hour_value,
        "rainfall_1h": _forward_sum(hourly_map, target_time, 1),
        "rainfall_3h": _forward_sum(hourly_map, target_time, 3),
        "rainfall_6h": _forward_sum(hourly_map, target_time, 6),
        "rainfall_intensity": _forward_max(hourly_map, target_time, 3),
        "cumulative_rainfall": _forward_sum(hourly_map, target_time, 6),
    }


def _latest_zone_drain_state(zone_id: int):
    """Parallel lists (normal_capacities, blockage_percents), one entry per
    drain in the zone. A drain with no reading yet is assumed 0% blocked
    (a brand-new, presumed-healthy drain) -- not treated as unknown risk."""
    drains = Drain.query.filter_by(zone_id=zone_id).all()
    capacities, blockages = [], []
    for drain in drains:
        latest_reading = drain.readings.first()  # relationship is ordered desc by timestamp
        capacities.append(drain.normal_capacity_m3s)
        blockages.append(latest_reading.blockage_percent if latest_reading else 0.0)
    return capacities, blockages


def _build_zone_nowcast_locked(zone: Zone, ensure_fresh_data: bool = True, persist: bool = True) -> dict:
    """Computes and PERSISTS the 7-step nowcast for one zone. Re-running
    this for the same zone replaces predictions in the same time window
    rather than duplicating rows (same idempotent pattern as the rainfall
    pipeline)."""
    now = utc_now().replace(second=0, microsecond=0)
    offsets = Config.NOWCAST_OFFSETS_MINUTES
    target_times = [now + timedelta(minutes=m) for m in offsets]
    # Fetch 6 hours past the last nowcast step too, since build_rainfall_windows
    # looks up to 6 hours FORWARD from each step (needed for rainfall_6h /
    # cumulative_rainfall at the final +3hr step).
    fetch_end = target_times[-1] + timedelta(hours=6)

    hourly_map = _get_hourly_rainfall_map(zone.id, _floor_to_hour(now), fetch_end)
    if not hourly_map and ensure_fresh_data and persist:
        ingest_zone_rainfall(zone, allow_demo_fallback=True)
        hourly_map = _get_hourly_rainfall_map(zone.id, _floor_to_hour(now), fetch_end)

    # IMPORTANT: read-only HTTP endpoints must never write to SQLite. If the
    # database cache is missing/stale, build the forecast in memory from the
    # live Open-Meteo hourly response instead of ingesting/deleting/inserting
    # WeatherForecast or FloodPrediction rows.
    if not hourly_map:
        try:
            live_weather = get_weather_for_coordinates(
                zone.latitude, zone.longitude, force_refresh=False
            )
            ist = ZoneInfo("Asia/Kolkata")
            for item in live_weather.get("hourly", []):
                raw_ts = item.get("time")
                if not raw_ts:
                    continue
                local_dt = datetime.fromisoformat(str(raw_ts))
                if local_dt.tzinfo is None:
                    local_dt = local_dt.replace(tzinfo=ist)
                utc_dt = local_dt.astimezone(timezone.utc).replace(tzinfo=None)
                hourly_map[_floor_to_hour(utc_dt)] = float(item.get("precipitation_mm") or 0.0)
        except Exception:
            # A stale database cache is still preferable to returning no
            # forecast at all. If there is no cache, the empty map produces a
            # transparent zero-rainfall fallback rather than a DB write.
            pass

    capacities, blockages = _latest_zone_drain_state(zone.id)

    if persist:
        # Clear any previous predictions in this exact window before writing
        # fresh ones -- avoids accumulating duplicate rows on repeated calls.
        FloodPrediction.query.filter(
            FloodPrediction.zone_id == zone.id,
            FloodPrediction.forecast_time >= target_times[0],
            FloodPrediction.forecast_time <= target_times[-1],
        ).delete(synchronize_session=False)

    steps = []
    previous_depth_cm = 0.0
    previous_time = now

    for offset, target_time in zip(offsets, target_times):
        rainfall_mm = _rainfall_for_target(hourly_map, target_time)
        duration_minutes = (target_time - previous_time).total_seconds() / 60.0

        # --- Build the ML feature vector for this step ---
        # Preliminary runoff/drainage figures computed directly (same
        # functions risk.py uses internally) so we have them BEFORE calling
        # evaluate_zone_risk, since ml_probability is an input to that call,
        # not an output of it. evaluate_zone_risk() recomputes the same
        # numbers internally -- a small, harmless redundancy that keeps
        # flood_engine/risk.py's interface simple (see its module docstring).
        prelim_runoff = compute_runoff(rainfall_mm, zone.area_km2, zone.impervious_surface_percent)["runoff_m3s"]
        effective_capacities = [compute_effective_capacity(c, b) for c, b in zip(capacities, blockages)]
        total_capacity = aggregate_zone_capacity(effective_capacities)
        utilization_pct = compute_drainage_utilization(prelim_runoff, total_capacity)
        avg_blockage = round(sum(blockages) / len(blockages), 2) if blockages else 0.0

        rainfall_windows = build_rainfall_windows(hourly_map, target_time)
        feature_vector = build_feature_vector(
            rainfall_30min=rainfall_windows["rainfall_30min"],
            rainfall_1h=rainfall_windows["rainfall_1h"],
            rainfall_3h=rainfall_windows["rainfall_3h"],
            rainfall_6h=rainfall_windows["rainfall_6h"],
            rainfall_intensity=rainfall_windows["rainfall_intensity"],
            cumulative_rainfall=rainfall_windows["cumulative_rainfall"],
            runoff=prelim_runoff,
            drainage_capacity=total_capacity,
            drainage_utilization=utilization_pct,
            blockage_percentage=avg_blockage,
            elevation=zone.elevation_m,
            slope=zone.slope_percent,
            impervious_surface=zone.impervious_surface_percent,
            historical_flood_frequency=zone.historical_flood_frequency,
        )
        # Returns None if no trained model exists yet -- evaluate_zone_risk's
        # blend_with_ml_prediction() falls back to rule-based-only in that case.
        ml_probability = predict_flood_probability(feature_vector)

        result = evaluate_zone_risk(
            rainfall_intensity_mm_per_hr=rainfall_mm,
            area_km2=zone.area_km2,
            impervious_surface_percent=zone.impervious_surface_percent,
            drain_normal_capacities_m3s=capacities,
            drain_blockage_percents=blockages,
            previous_water_depth_cm=previous_depth_cm,
            duration_minutes=duration_minutes,
            ml_probability=ml_probability,
        )

        if persist:
            db.session.add(FloodPrediction(
                zone_id=zone.id,
                forecast_time=target_time,
                rainfall_mm=result["rainfall_mm"],
                runoff_m3s=result["runoff_m3s"],
                drainage_capacity_m3s=result["drainage_capacity_m3s"],
                drainage_utilization_pct=result["drainage_utilization_pct"],
                excess_flow_m3s=result["excess_flow_m3s"],
                water_depth_cm=result["water_depth_cm"],
                flood_probability=result["flood_probability"],
                risk_category=result["risk_category"],
                model_version=result["model_version"],
            ))

        steps.append({
            "time": target_time.strftime("%H:%M"),
            "iso_time": target_time.isoformat(),
            "offset_minutes": offset,
            **result,
            "feature_vector": feature_vector,
        })

        previous_depth_cm = result["water_depth_cm"]
        previous_time = target_time

    if persist:
        db.session.commit()

    return {
        "zone_id": zone.id,
        "zone_code": zone.zone_code,
        "zone_name": zone.name,
        "forecast": steps,
    }


def build_zone_nowcast(zone: Zone, ensure_fresh_data: bool = True) -> dict:
    """Write a fresh seven-step prediction window, serialized for SQLite."""
    with DB_WRITE_LOCK:
        return _build_zone_nowcast_locked(zone, ensure_fresh_data=ensure_fresh_data)


def _prediction_step(row: FloodPrediction) -> dict:
    return {
        "time": row.forecast_time.strftime("%H:%M"),
        "iso_time": row.forecast_time.isoformat(),
        "offset_minutes": None,
        "rainfall_mm": row.rainfall_mm,
        "runoff_m3s": row.runoff_m3s,
        "drainage_capacity_m3s": row.drainage_capacity_m3s,
        "drainage_utilization_pct": row.drainage_utilization_pct,
        "excess_flow_m3s": row.excess_flow_m3s,
        "water_depth_cm": row.water_depth_cm,
        "flood_probability": row.flood_probability,
        "risk_category": row.risk_category,
        "model_version": row.model_version,
    }


def _rows_to_nowcast(zone: Zone, rows: list[FloodPrediction]) -> dict:
    rows = sorted(rows, key=lambda r: r.forecast_time)
    base = rows[0].forecast_time if rows else None
    forecast = []
    for row in rows:
        step = _prediction_step(row)
        step["offset_minutes"] = int(round((row.forecast_time - base).total_seconds() / 60.0)) if base else 0
        forecast.append(step)
    return {"zone_id": zone.id, "zone_code": zone.zone_code, "zone_name": zone.name, "forecast": forecast}


def get_cached_zone_nowcast(zone: Zone, max_age_minutes: int = 5, build_if_missing: bool = True) -> dict:
    """Read cached predictions without ever writing to SQLite from a GET.

    Fresh rows are returned directly. If rows are stale or missing, the
    forecast is recomputed in memory from cached/live Open-Meteo weather.
    Database persistence is reserved for explicit refresh operations.
    """
    rows = (
        FloodPrediction.query.filter_by(zone_id=zone.id)
        .order_by(FloodPrediction.forecast_time.desc())
        .limit(len(Config.NOWCAST_OFFSETS_MINUTES))
        .all()
    )
    rows = sorted(rows, key=lambda r: r.forecast_time)
    now = utc_now()
    fresh = (
        len(rows) == len(Config.NOWCAST_OFFSETS_MINUTES)
        and rows[0].forecast_time >= now - timedelta(minutes=max_age_minutes)
    )
    if fresh:
        return _rows_to_nowcast(zone, rows)

    if build_if_missing:
        # Read-only in-memory fallback. No DELETE, INSERT, or COMMIT occurs.
        live = _build_zone_nowcast_locked(zone, ensure_fresh_data=False, persist=False)
        if live.get("forecast"):
            return live

    return _rows_to_nowcast(zone, rows) if rows else {
        "zone_id": zone.id,
        "zone_code": zone.zone_code,
        "zone_name": zone.name,
        "forecast": [],
    }


def get_cached_all_zone_nowcasts(max_age_minutes: int = 5, build_if_missing: bool = True) -> list:
    """Read all zones. HTTP GETs never trigger SQLite writes."""
    return [
        get_cached_zone_nowcast(
            zone, max_age_minutes=max_age_minutes, build_if_missing=build_if_missing
        )
        for zone in Zone.query.order_by(Zone.id).all()
    ]

def build_all_zones_nowcast(ensure_fresh_data: bool = True) -> list:
    """Explicit write operation used by CLI/refresh jobs."""
    with DB_WRITE_LOCK:
        return [_build_zone_nowcast_locked(zone, ensure_fresh_data=ensure_fresh_data) for zone in Zone.query.order_by(Zone.id).all()]
