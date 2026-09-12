"""
services/rainfall_pipeline.py
--------------------------------
Implements the pipeline described in the architecture doc:

    Open-Meteo API -> weather_service -> validation -> pandas/numpy
        -> database (weather_forecasts + rainfall_records)

This is intentionally the ONLY file that writes to WeatherForecast /
RainfallRecord as a batch. Routes call into here; they never build these
rows themselves, so there's one place that enforces validation and
idempotent re-ingestion.

Connects to:
- services/weather_service.py -> supplies the raw hourly data (live or demo)
- utils/validators.py         -> per-row rainfall validation
- models/weather_forecast.py, models/rainfall.py -> what gets written
- routes/weather_routes.py    -> triggers ingestion for one zone on request
- app.py                      -> `flask --app app run-pipeline` runs it for all zones
"""

import logging

import pandas as pd

from extensions import db
from models import Zone, WeatherForecast, RainfallRecord
from services.db_lock import DB_WRITE_LOCK
from services.weather_service import fetch_weather_for_zone
from utils.validators import validate_rainfall_mm, ValidationError

logger = logging.getLogger(__name__)


def _rainfall_source_for(weather_source: str) -> str:
    """Open-Meteo's hourly data is always a forecast value in this
    prototype (no real rain-gauge feed is wired up), so a live pull maps to
    "forecast". A demo fallback maps to "demo", never "forecast" -- see
    the VALID_SOURCES note in models/rainfall.py for why that matters."""
    return "demo" if weather_source == "demo" else "forecast"


def _clean_hourly_dataframe(hourly_records: list[dict]) -> tuple[pd.DataFrame, int]:
    """Validates and cleans the raw hourly records with pandas/numpy.
    Returns (clean_dataframe, rows_skipped_count). Rows that fail
    validation are dropped, not silently zeroed, so the ingestion summary
    can honestly report how many were rejected."""
    df = pd.DataFrame(hourly_records)
    if df.empty:
        return df, 0

    # Parse as UTC-aware first (so any timezone info Open-Meteo includes is
    # interpreted correctly), then strip tzinfo immediately -- SQLite loses
    # timezone info on write/read anyway, and a fresh aware "now" compared
    # later against these values would silently never match if we left
    # them aware. See utils/time_utils.py for the full story.
    df["time"] = pd.to_datetime(df["time"], utc=True).dt.tz_localize(None)

    valid_mask = []
    for value in df["precipitation_mm"]:
        try:
            validate_rainfall_mm(value)
            valid_mask.append(True)
        except ValidationError as exc:
            logger.warning("Dropping hourly record with invalid rainfall: %s", exc)
            valid_mask.append(False)

    skipped = len(valid_mask) - sum(valid_mask)
    clean_df = df[valid_mask].reset_index(drop=True)
    return clean_df, skipped


def _ingest_zone_rainfall_locked(zone: Zone, allow_demo_fallback: bool = True, force_refresh: bool = False) -> dict:
    """Fetches, validates, and stores weather/rainfall data for one zone.
    Re-running this for the same zone replaces overlapping timestamps
    instead of duplicating them, so the pipeline can be safely re-run on a
    schedule (e.g. every WEATHER_CACHE_TTL_SECONDS)."""
    weather_data = fetch_weather_for_zone(
        zone, allow_demo_fallback=allow_demo_fallback, force_refresh=force_refresh
    )

    clean_df, skipped = _clean_hourly_dataframe(weather_data["hourly"])
    if clean_df.empty:
        return {
            "zone_id": zone.id, "zone_code": zone.zone_code,
            "records_ingested": 0, "records_skipped": skipped,
            "source": weather_data["source"],
        }

    # --- Idempotent re-ingestion: clear any existing rows in this batch's
    # time range for this zone before inserting the fresh batch. ---
    time_min, time_max = clean_df["time"].min(), clean_df["time"].max()
    WeatherForecast.query.filter(
        WeatherForecast.zone_id == zone.id,
        WeatherForecast.forecast_time >= time_min,
        WeatherForecast.forecast_time <= time_max,
    ).delete(synchronize_session=False)
    RainfallRecord.query.filter(
        RainfallRecord.zone_id == zone.id,
        RainfallRecord.timestamp >= time_min,
        RainfallRecord.timestamp <= time_max,
    ).delete(synchronize_session=False)

    rainfall_source = _rainfall_source_for(weather_data["source"])
    forecast_source_label = "demo" if weather_data["source"] == "demo" else "open-meteo"

    for _, row in clean_df.iterrows():
        ts = row["time"].to_pydatetime()

        db.session.add(WeatherForecast(
            zone_id=zone.id,
            forecast_time=ts,
            precipitation_mm=float(row["precipitation_mm"]),
            precipitation_probability=row.get("precipitation_probability"),
            temperature_c=row.get("temperature_c"),
            humidity_percent=row.get("humidity_percent"),
            wind_kmh=row.get("wind_kmh"),
            pressure_hpa=row.get("pressure_hpa"),
            source=forecast_source_label,
        ))

        db.session.add(RainfallRecord(
            zone_id=zone.id,
            timestamp=ts,
            rainfall_mm=float(row["precipitation_mm"]),
            source=rainfall_source,
        ))

    db.session.commit()

    return {
        "zone_id": zone.id,
        "zone_code": zone.zone_code,
        "records_ingested": len(clean_df),
        "records_skipped": skipped,
        "source": weather_data["source"],
        "used_demo_fallback": weather_data["source"] == "demo",
        "error": weather_data.get("error"),
    }


def ingest_zone_rainfall(zone: Zone, allow_demo_fallback: bool = True, force_refresh: bool = False) -> dict:
    with DB_WRITE_LOCK:
        return _ingest_zone_rainfall_locked(zone, allow_demo_fallback=allow_demo_fallback, force_refresh=force_refresh)


def run_pipeline_for_all_zones(allow_demo_fallback: bool = True) -> list[dict]:
    """Runs ingest_zone_rainfall() for every zone in the database. Meant to
    be called from an app context (e.g. the `run-pipeline` CLI command)."""
    results = []
    for zone in Zone.query.all():
        try:
            results.append(ingest_zone_rainfall(zone, allow_demo_fallback=allow_demo_fallback))
        except Exception as exc:  # noqa: BLE001 -- one zone failing shouldn't stop the rest
            logger.error("Pipeline failed for zone %s: %s", zone.zone_code, exc)
            results.append({
                "zone_id": zone.id, "zone_code": zone.zone_code,
                "records_ingested": 0, "records_skipped": 0,
                "source": "error", "error": str(exc),
            })
    return results
