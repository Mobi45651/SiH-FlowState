"""
utils/validators.py
----------------------
Small, dependency-free validation functions used before anything from an
external API or a user request is trusted enough to reach the database or
the flood engine. Each raises ValidationError with a specific message
rather than failing silently or letting bad data (negative rainfall, a
malformed API payload) flow downstream.

Connects to:
- services/rainfall_pipeline.py -> validates each Open-Meteo hourly record
- routes/simulation_routes.py (Phase 13) -> will validate what-if inputs
"""


class ValidationError(ValueError):
    """Raised when incoming data fails a validation check."""


def validate_weather_api_response(payload: dict) -> None:
    """Confirm an Open-Meteo response has the shape we depend on before we
    try to index into it. Raises ValidationError on anything unexpected."""
    if not isinstance(payload, dict):
        raise ValidationError("Weather API response was not a JSON object.")

    hourly = payload.get("hourly")
    if not isinstance(hourly, dict):
        raise ValidationError("Weather API response is missing an 'hourly' object.")

    required_keys = ("time", "precipitation")
    missing = [k for k in required_keys if k not in hourly]
    if missing:
        raise ValidationError(f"Weather API 'hourly' block is missing keys: {missing}")

    time_len = len(hourly["time"])
    for key, values in hourly.items():
        if key == "time":
            continue
        if len(values) != time_len:
            raise ValidationError(
                f"Weather API hourly array '{key}' has length {len(values)}, "
                f"expected {time_len} to match 'time'."
            )


def validate_rainfall_mm(value) -> float:
    """Rainfall must be a non-negative, finite number. Open-Meteo sometimes
    returns null for a not-yet-forecast hour -- callers should treat that
    as 0.0 mm before this function is reached, not pass None in."""
    if value is None:
        raise ValidationError("rainfall_mm cannot be None.")
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"rainfall_mm must be numeric, got {value!r}.")
    if numeric < 0:
        raise ValidationError(f"rainfall_mm cannot be negative, got {numeric}.")
    if numeric > 500:
        # 500mm/hr is far beyond any recorded rainfall rate -- this almost
        # certainly indicates a unit or parsing error, not real weather.
        raise ValidationError(f"rainfall_mm {numeric} is implausibly high, rejecting.")
    return numeric


def validate_zone_coordinates(latitude, longitude) -> None:
    if latitude is None or longitude is None:
        raise ValidationError("Zone is missing latitude/longitude.")
    if not (-90 <= latitude <= 90):
        raise ValidationError(f"latitude {latitude} is out of range.")
    if not (-180 <= longitude <= 180):
        raise ValidationError(f"longitude {longitude} is out of range.")
