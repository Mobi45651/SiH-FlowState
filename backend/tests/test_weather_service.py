"""
tests/test_weather_service.py
--------------------------------
Every test here mocks requests.get -- these tests must pass with zero
network access, which also means they'll run the same in CI as on a judge's
laptop with wifi off.

Run with: pytest backend/tests/test_weather_service.py -v
"""

from unittest.mock import patch, Mock

import pytest
import requests

from services.weather_service import (
    get_weather_for_coordinates,
    fetch_weather_for_zone,
    WeatherServiceError,
)
from utils import cache
from models import Zone


def fake_open_meteo_payload():
    return {
        "latitude": 21.1, "longitude": 79.1,
        "hourly": {
            "time": ["2026-08-27T00:00", "2026-08-27T01:00"],
            "precipitation": [0.0, 12.5],
            "precipitation_probability": [10, 60],
            "temperature_2m": [26.0, 25.5],
            "relative_humidity_2m": [80, 85],
            "wind_speed_10m": [10.0, 12.0],
            "pressure_msl": [1008.0, 1007.5],
        },
    }


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


def test_get_weather_success(app):
    mock_response = Mock(raise_for_status=Mock(), json=Mock(return_value=fake_open_meteo_payload()))
    with patch("services.weather_service.requests.get", return_value=mock_response) as mock_get:
        result = get_weather_for_coordinates(21.1, 79.1)

    assert result["source"] == "live"
    assert len(result["hourly"]) == 2
    assert result["hourly"][1]["precipitation_mm"] == 12.5
    mock_get.assert_called_once()


def test_get_weather_uses_cache_on_second_call(app):
    mock_response = Mock(raise_for_status=Mock(), json=Mock(return_value=fake_open_meteo_payload()))
    with patch("services.weather_service.requests.get", return_value=mock_response) as mock_get:
        get_weather_for_coordinates(21.2, 79.2)
        second = get_weather_for_coordinates(21.2, 79.2)

    assert second["source"] == "cache"
    mock_get.assert_called_once()  # only one real HTTP call across both requests


def test_get_weather_raises_typed_error_on_network_failure(app):
    with patch("services.weather_service.requests.get", side_effect=requests.exceptions.ConnectionError("no network")):
        with pytest.raises(WeatherServiceError):
            get_weather_for_coordinates(0.0, 0.0)


def test_fetch_weather_for_zone_falls_back_to_demo_on_failure(app):
    zone = Zone(
        zone_code="ZT01", name="Test Zone", latitude=1.0, longitude=1.0,
        elevation_m=200, slope_percent=1, impervious_surface_percent=50,
        area_km2=1, historical_flood_frequency="LOW",
    )
    zone.id = 999  # not persisted -- only attributes are needed here

    with patch("services.weather_service.requests.get", side_effect=requests.exceptions.ConnectionError("no network")):
        result = fetch_weather_for_zone(zone, allow_demo_fallback=True)

    assert result["source"] == "demo"
    assert result["error"]  # original failure reason is preserved, not hidden
    assert len(result["hourly"]) > 0


def test_fetch_weather_for_zone_raises_without_fallback(app):
    zone = Zone(
        zone_code="ZT02", name="Test Zone 2", latitude=2.0, longitude=2.0,
        elevation_m=200, slope_percent=1, impervious_surface_percent=50,
        area_km2=1, historical_flood_frequency="LOW",
    )
    zone.id = 998

    with patch("services.weather_service.requests.get", side_effect=requests.exceptions.ConnectionError("no network")):
        with pytest.raises(WeatherServiceError):
            fetch_weather_for_zone(zone, allow_demo_fallback=False)
