"""
tests/test_rainfall_pipeline.py
----------------------------------
Mocks fetch_weather_for_zone() so these tests exercise the pandas
validation/cleaning + database-write logic in isolation from the network
and from weather_service's own behaviour (already covered separately in
test_weather_service.py).

Run with: pytest backend/tests/test_rainfall_pipeline.py -v
"""

from unittest.mock import patch

from extensions import db
from models import Zone, WeatherForecast, RainfallRecord
from services.rainfall_pipeline import ingest_zone_rainfall


def make_zone(code="ZP01"):
    zone = Zone(
        zone_code=code, name=f"Pipeline {code}", latitude=5.0, longitude=5.0,
        elevation_m=200, slope_percent=1, impervious_surface_percent=50,
        area_km2=1, historical_flood_frequency="LOW",
    )
    db.session.add(zone)
    db.session.commit()
    return zone


def fake_weather(hourly, source="live"):
    return {
        "zone_id": None, "latitude": 5.0, "longitude": 5.0, "source": source,
        "fetched_at": "2026-08-27T00:00:00+00:00",
        "hourly": hourly,
    }


def test_ingest_stores_clean_records(app):
    zone = make_zone("ZP01")
    hourly = [
        {"time": "2026-08-27T00:00:00Z", "precipitation_mm": 5.0, "precipitation_probability": 40,
         "temperature_c": 26, "humidity_percent": 80, "wind_kmh": 10, "pressure_hpa": 1008},
        {"time": "2026-08-27T01:00:00Z", "precipitation_mm": 22.0, "precipitation_probability": 70,
         "temperature_c": 25, "humidity_percent": 85, "wind_kmh": 12, "pressure_hpa": 1007},
    ]
    with patch("services.rainfall_pipeline.fetch_weather_for_zone", return_value=fake_weather(hourly)):
        summary = ingest_zone_rainfall(zone)

    assert summary["records_ingested"] == 2
    assert summary["records_skipped"] == 0
    assert RainfallRecord.query.filter_by(zone_id=zone.id).count() == 2
    assert WeatherForecast.query.filter_by(zone_id=zone.id).count() == 2

    # forecast (not demo) source, since fake_weather() defaults to "live"
    sources = {r.source for r in RainfallRecord.query.filter_by(zone_id=zone.id).all()}
    assert sources == {"forecast"}


def test_ingest_skips_invalid_rainfall_rows(app):
    zone = make_zone("ZP02")
    hourly = [
        {"time": "2026-08-27T00:00:00Z", "precipitation_mm": 5.0, "precipitation_probability": 40,
         "temperature_c": 26, "humidity_percent": 80, "wind_kmh": 10, "pressure_hpa": 1008},
        # -1 mm is physically impossible and must be dropped, not clamped silently
        {"time": "2026-08-27T01:00:00Z", "precipitation_mm": -1.0, "precipitation_probability": 70,
         "temperature_c": 25, "humidity_percent": 85, "wind_kmh": 12, "pressure_hpa": 1007},
    ]
    with patch("services.rainfall_pipeline.fetch_weather_for_zone", return_value=fake_weather(hourly)):
        summary = ingest_zone_rainfall(zone)

    assert summary["records_ingested"] == 1
    assert summary["records_skipped"] == 1


def test_ingest_is_idempotent_on_rerun(app):
    zone = make_zone("ZP03")
    hourly = [
        {"time": "2026-08-27T00:00:00Z", "precipitation_mm": 5.0, "precipitation_probability": 40,
         "temperature_c": 26, "humidity_percent": 80, "wind_kmh": 10, "pressure_hpa": 1008},
    ]
    with patch("services.rainfall_pipeline.fetch_weather_for_zone", return_value=fake_weather(hourly)):
        ingest_zone_rainfall(zone)
        ingest_zone_rainfall(zone)  # re-run over the same time range

    # Second run must replace, not duplicate, the overlapping timestamp.
    assert RainfallRecord.query.filter_by(zone_id=zone.id).count() == 1
    assert WeatherForecast.query.filter_by(zone_id=zone.id).count() == 1


def test_ingest_tags_demo_source_correctly(app):
    zone = make_zone("ZP04")
    hourly = [
        {"time": "2026-08-27T00:00:00Z", "precipitation_mm": 5.0, "precipitation_probability": 40,
         "temperature_c": 26, "humidity_percent": 80, "wind_kmh": 10, "pressure_hpa": 1008},
    ]
    with patch("services.rainfall_pipeline.fetch_weather_for_zone", return_value=fake_weather(hourly, source="demo")):
        summary = ingest_zone_rainfall(zone)

    assert summary["used_demo_fallback"] is True
    record = RainfallRecord.query.filter_by(zone_id=zone.id).first()
    assert record.source == "demo"  # never mislabeled as "forecast"
