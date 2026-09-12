"""
services/weather_service.py
-----------------------------
This is the ONLY file in the whole backend allowed to call the Open-Meteo
API. Everything else -- routes, the rainfall pipeline, the flood engine --
goes through the functions here, so there is exactly one place to change
if the weather provider is ever swapped.

Behaviour on failure (network error, timeout, bad response, malformed
payload): the error is detected, logged, and raised as a typed
WeatherServiceError. Callers that want the app to keep functioning during a
demo can opt into `allow_demo_fallback=True`, in which case a clearly
source="demo" payload is returned WITH the original error attached --
never silently swapped in as if it were live data.

Connects to:
- routes/weather_routes.py     -> GET /api/weather
- services/rainfall_pipeline.py -> pulls hourly data to store in the DB
- utils/cache.py               -> avoids re-calling Open-Meteo every request
- utils/validators.py          -> validates the raw API shape before parsing
- utils/demo_data_generator.py -> supplies the demo fallback data
"""

import logging
from datetime import datetime, timezone

import requests

from flask import current_app
from utils import cache
from utils.validators import validate_weather_api_response, ValidationError
from utils.demo_data_generator import generate_demo_hourly_weather

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 8
HOURLY_VARIABLES = [
    "precipitation",
    "precipitation_probability",
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "pressure_msl",
]

CURRENT_VARIABLES = [
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "precipitation",
    "rain",
    "showers",
    "wind_speed_10m",
    "pressure_msl",
    "weather_code",
]


class WeatherServiceError(Exception):
    """Raised whenever the Open-Meteo call or response parsing fails."""


def _cache_key(latitude: float, longitude: float) -> str:
    # Round to ~100m precision so nearby zones share one cached call.
    return f"weather:{round(latitude, 3)}:{round(longitude, 3)}"


def _fetch_raw(latitude: float, longitude: float) -> dict:
    """Calls Open-Meteo directly. Raises WeatherServiceError on any failure
    -- network, timeout, non-200 status, or invalid JSON/shape. Never
    returns a partial or guessed result."""
    api_url = current_app.config["WEATHER_API_URL"]
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ",".join(HOURLY_VARIABLES),
        "current": ",".join(CURRENT_VARIABLES),
        "forecast_days": 2,
        "timezone": "Asia/Kolkata",
        # For a dashboard tied to a named city/zone, request the nearest
        # possible grid cell rather than allowing the default terrain/elevation
        # selector to move the forecast to a different cell.
        "cell_selection": current_app.config.get("WEATHER_CELL_SELECTION", "nearest"),
    }
    model = current_app.config.get("WEATHER_MODEL", "").strip()
    if model:
        params["models"] = model

    try:
        response = requests.get(api_url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.exceptions.Timeout as exc:
        raise WeatherServiceError(f"Open-Meteo request timed out: {exc}") from exc
    except requests.exceptions.RequestException as exc:
        raise WeatherServiceError(f"Open-Meteo request failed: {exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise WeatherServiceError(f"Open-Meteo returned invalid JSON: {exc}") from exc

    try:
        validate_weather_api_response(payload)
    except ValidationError as exc:
        raise WeatherServiceError(f"Open-Meteo response failed validation: {exc}") from exc

    return payload


def _parse_hourly(payload: dict) -> list[dict]:
    """Turns Open-Meteo's column-oriented hourly arrays into a list of
    per-timestep dicts, which is far easier for pandas/the rainfall
    pipeline and the frontend to work with than four parallel arrays."""
    hourly = payload["hourly"]
    times = hourly["time"]

    def col(key):
        return hourly.get(key, [None] * len(times))

    precipitation = col("precipitation")
    precipitation_probability = col("precipitation_probability")
    temperature = col("temperature_2m")
    humidity = col("relative_humidity_2m")
    wind = col("wind_speed_10m")
    pressure = col("pressure_msl")

    records = []
    for i, ts in enumerate(times):
        records.append({
            "time": ts,  # ISO 8601 string, Open-Meteo's native format
            # Open-Meteo returns null for precipitation on hours it can't
            # yet forecast confidently -- treat that as 0.0, not missing.
            "precipitation_mm": precipitation[i] if precipitation[i] is not None else 0.0,
            "precipitation_probability": precipitation_probability[i],
            "temperature_c": temperature[i],
            "humidity_percent": humidity[i],
            "wind_kmh": wind[i],
            "pressure_hpa": pressure[i],
        })
    return records


def get_weather_for_coordinates(latitude: float, longitude: float, force_refresh: bool = False) -> dict:
    """Live (or freshly-cached) weather only. Raises WeatherServiceError on
    failure -- use fetch_weather_for_zone() below if you want an automatic
    demo fallback instead of an exception."""
    key = _cache_key(latitude, longitude)
    ttl = current_app.config["WEATHER_CACHE_TTL_SECONDS"]

    if not force_refresh:
        cached = cache.get(key)
        if cached is not None:
            return {**cached, "source": "cache"}

    raw = _fetch_raw(latitude, longitude)
    hourly = _parse_hourly(raw)
    current = raw.get("current") or {}
    # Keep the provider's current observation/model value distinct from the
    # hourly forecast. The frontend should use current.temperature_2m for the
    # main temperature card, not hourly[0], because hourly[0] is an hourly
    # forecast bucket and can differ from the current value.
    current = {**current}
    if current.get("temperature_2m") is not None:
        current["temperature_c"] = current["temperature_2m"]
    if current.get("apparent_temperature") is not None:
        current["apparent_temperature_c"] = current["apparent_temperature"]
    if current.get("relative_humidity_2m") is not None:
        current["humidity_percent"] = current["relative_humidity_2m"]
    if current.get("wind_speed_10m") is not None:
        current["wind_kmh"] = current["wind_speed_10m"]

    result = {
        "latitude": latitude,
        "longitude": longitude,
        "provider_latitude": raw.get("latitude"),
        "provider_longitude": raw.get("longitude"),
        "provider_elevation_m": raw.get("elevation"),
        "provider_timezone": raw.get("timezone"),
        "current": current,
        "hourly": hourly,
        "timezone": raw.get("timezone", "Asia/Kolkata"),
        "cell_selection": current_app.config.get("WEATHER_CELL_SELECTION", "nearest"),
        "model": current_app.config.get("WEATHER_MODEL") or "auto",
        "source": "live",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    logger.info(
        "Open-Meteo weather: requested=(%.5f, %.5f) provider=(%s, %s) "
        "current_time=%s temperature=%s apparent=%s cell_selection=%s model=%s",
        latitude, longitude, raw.get("latitude"), raw.get("longitude"),
        current.get("time"), current.get("temperature_2m"),
        current.get("apparent_temperature"), result["cell_selection"], result["model"]
    )
    cache.set(key, result, ttl)
    return result


def fetch_weather_for_zone(zone, allow_demo_fallback: bool = True, force_refresh: bool = False) -> dict:
    """The function most callers should use. Wraps get_weather_for_coordinates
    with zone context and, on failure, either re-raises or returns a
    source="demo" payload that carries the original error message so the
    frontend can show "using demo data because: <reason>" instead of
    pretending nothing went wrong.
    """
    try:
        result = get_weather_for_coordinates(zone.latitude, zone.longitude, force_refresh=force_refresh)
        result["zone_id"] = zone.id
        return result
    except WeatherServiceError as exc:
        logger.warning("Weather fetch failed for zone %s: %s", zone.zone_code, exc)
        if not allow_demo_fallback:
            raise
        return {
            "zone_id": zone.id,
            "latitude": zone.latitude,
            "longitude": zone.longitude,
            "hourly": generate_demo_hourly_weather(),
            "current": {},
            "source": "demo",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "error": str(exc),  # always kept, never dropped, so the demo label is explainable
        }
