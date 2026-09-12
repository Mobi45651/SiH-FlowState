"""
tests/test_nowcast.py
------------------------
Pre-seeds WeatherForecast rows aligned to the real current hour (since
nowcast_engine works off datetime.now()) so results are deterministic,
then exercises build_zone_nowcast() end-to-end against the in-memory test
database. ingest_zone_rainfall is patched as a safety net only -- it
should never actually be called here since we pre-seed enough hourly data
to cover the full 3-hour window.

Run with: pytest backend/tests/test_nowcast.py -v
"""

from datetime import timedelta
from unittest.mock import patch

from extensions import db
from models import Zone, Drain, WeatherForecast, FloodPrediction
from services.nowcast_engine import build_zone_nowcast, build_all_zones_nowcast
from utils.time_utils import utc_now


def _floor_to_hour(dt):
    return dt.replace(minute=0, second=0, microsecond=0)


def make_zone(code="ZN01", impervious=80):
    zone = Zone(
        zone_code=code, name=f"Nowcast {code}", latitude=1.0, longitude=1.0,
        elevation_m=200, slope_percent=1, impervious_surface_percent=impervious,
        area_km2=2.0, historical_flood_frequency="LOW",
    )
    db.session.add(zone)
    db.session.commit()
    return zone


def add_drain(zone, capacity=3.0, code_suffix="01"):
    drain = Drain(drain_code=f"{zone.zone_code}-D{code_suffix}", zone_id=zone.id, latitude=1.0,
                   longitude=1.0, normal_capacity_m3s=capacity, condition="GOOD", status="NORMAL")
    db.session.add(drain)
    db.session.commit()
    return drain


def seed_hourly_weather(zone, hourly_rainfall_mm: dict):
    """hourly_rainfall_mm maps an hour-offset-from-now (int) -> rainfall mm
    for that hour bucket, e.g. {0: 5.0, 1: 40.0, 2: 40.0, 3: 10.0}."""
    now_hour = _floor_to_hour(utc_now())
    for offset_hours, mm in hourly_rainfall_mm.items():
        db.session.add(WeatherForecast(
            zone_id=zone.id,
            forecast_time=now_hour + timedelta(hours=offset_hours),
            precipitation_mm=mm,
            precipitation_probability=50,
            temperature_c=27, humidity_percent=80, wind_kmh=10, pressure_hpa=1008,
            source="open-meteo",
        ))
    db.session.commit()


@patch("services.nowcast_engine.ingest_zone_rainfall")
def test_build_zone_nowcast_returns_seven_steps(mock_ingest, app):
    zone = make_zone("ZN01")
    add_drain(zone)
    seed_hourly_weather(zone, {0: 5.0, 1: 5.0, 2: 5.0, 3: 5.0})

    result = build_zone_nowcast(zone)

    assert result["zone_code"] == "ZN01"
    assert len(result["forecast"]) == 7
    assert [s["offset_minutes"] for s in result["forecast"]] == [0, 30, 60, 90, 120, 150, 180]
    assert mock_ingest.call_count == 0  # pre-seeded data means no auto-ingest was needed


@patch("services.nowcast_engine.ingest_zone_rainfall")
def test_build_zone_nowcast_persists_flood_predictions(mock_ingest, app):
    zone = make_zone("ZN02")
    add_drain(zone)
    seed_hourly_weather(zone, {0: 5.0, 1: 5.0, 2: 5.0, 3: 5.0})

    build_zone_nowcast(zone)

    predictions = FloodPrediction.query.filter_by(zone_id=zone.id).all()
    assert len(predictions) == 7
    assert all(p.risk_category in ("LOW", "MODERATE", "HIGH", "SEVERE") for p in predictions)


@patch("services.nowcast_engine.ingest_zone_rainfall")
def test_rerun_does_not_duplicate_predictions(mock_ingest, app):
    zone = make_zone("ZN03")
    add_drain(zone)
    seed_hourly_weather(zone, {0: 5.0, 1: 5.0, 2: 5.0, 3: 5.0})

    build_zone_nowcast(zone)
    build_zone_nowcast(zone)  # re-run over the same window

    assert FloodPrediction.query.filter_by(zone_id=zone.id).count() == 7


@patch("services.nowcast_engine.ingest_zone_rainfall")
def test_heavy_rain_produces_higher_risk_than_light_rain(mock_ingest, app):
    light_zone = make_zone("ZN04", impervious=80)
    add_drain(light_zone, capacity=5.0)
    seed_hourly_weather(light_zone, {0: 2.0, 1: 2.0, 2: 2.0, 3: 2.0})

    heavy_zone = make_zone("ZN05", impervious=80)
    add_drain(heavy_zone, capacity=5.0)
    seed_hourly_weather(heavy_zone, {0: 60.0, 1: 60.0, 2: 60.0, 3: 60.0})

    light_result = build_zone_nowcast(light_zone)
    heavy_result = build_zone_nowcast(heavy_zone)

    # Compare the last step, where accumulated depth has had time to build.
    assert heavy_result["forecast"][-1]["flood_probability"] > light_result["forecast"][-1]["flood_probability"]
    assert heavy_result["forecast"][-1]["water_depth_cm"] > light_result["forecast"][-1]["water_depth_cm"]


@patch("services.nowcast_engine.ingest_zone_rainfall")
def test_build_all_zones_nowcast_covers_every_zone(mock_ingest, app):
    z1 = make_zone("ZN06")
    add_drain(z1)
    seed_hourly_weather(z1, {0: 5.0, 1: 5.0, 2: 5.0, 3: 5.0})

    z2 = make_zone("ZN07")
    add_drain(z2)
    seed_hourly_weather(z2, {0: 5.0, 1: 5.0, 2: 5.0, 3: 5.0})

    results = build_all_zones_nowcast()
    zone_codes = {r["zone_code"] for r in results}
    assert {"ZN06", "ZN07"}.issubset(zone_codes)
