"""
config.py
---------
Single source of truth for app configuration. Everything is read from
environment variables (loaded from ".env" via python-dotenv) so no secret
or environment-specific value is ever hardcoded in the codebase.

Connects to:
- extensions.py     -> SQLALCHEMY_DATABASE_URI is read when db is initialised
- app.py            -> create_app(Config) applies this to the Flask app
- services/*.py     -> read WEATHER_API_URL / ROUTING_API_KEY from here
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load ".env" from the backend/ directory regardless of the current working
# directory the app is started from.
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    """Base configuration, shared by all environments."""

    # --- Core Flask ---
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
    DEBUG = os.environ.get("FLASK_DEBUG", "False").lower() in ("1", "true", "yes")

    # --- Database ---
    # Defaults to a SQLite file inside backend/ if DATABASE_URL isn't set.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'flood_nowcasting.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False  # silences an unneeded SQLAlchemy warning
    # SQLite: wait for short-lived concurrent writes instead of failing immediately.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"timeout": 30},
        "pool_pre_ping": True,
    }

    # --- External services ---
    WEATHER_API_URL = os.environ.get(
        "WEATHER_API_URL", "https://api.open-meteo.com/v1/forecast"
    )
    ROUTING_API_KEY = os.environ.get("ROUTING_API_KEY", "")

    # --- Demo admin account ---
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@admin.com").strip().lower()
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@123")

    # --- CORS ---
    # Comma-separated list of origins allowed to call /api/*. Defaults to
    # the most common local Vite (5173) and CRA (3000) dev ports so the
    # frontend works out of the box locally. Set this to your real
    # deployed frontend URL(s) in production -- see .env.example.
    ALLOWED_ORIGINS = [
        origin.strip() for origin in os.environ.get(
            "ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000"
        ).split(",") if origin.strip()
    ]

    # --- App-level constants used across the flood engine ---
    # How long a weather API response is cached before being re-fetched.
    WEATHER_CACHE_TTL_SECONDS = int(os.environ.get("WEATHER_CACHE_TTL_SECONDS", 60))
    # Use the nearest weather grid cell for dashboard current conditions.
    # Open-Meteo defaults to a terrain/elevation-aware land-cell selection,
    # which can intentionally choose a different cell than the requested
    # coordinate. For a city dashboard, nearest is easier to audit.
    WEATHER_CELL_SELECTION = os.environ.get("WEATHER_CELL_SELECTION", "nearest")
    # Leave model selection on Open-Meteo's automatic best-match unless
    # explicitly overridden.
    WEATHER_MODEL = os.environ.get("WEATHER_MODEL", "")

    # Nowcast horizon: current time + these offsets (minutes)
    NOWCAST_OFFSETS_MINUTES = [0, 30, 60, 90, 120, 150, 180]

    # Flood-risk probability thresholds -> category
    # (used by flood_engine/risk.py so thresholds live in one place)
    RISK_THRESHOLDS = {
        "LOW": 0.25,
        "MODERATE": 0.5,
        "HIGH": 0.75,
        # >= 0.75 -> SEVERE
    }


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    # Tests run against an in-memory database so they never touch real data.
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


class ProductionConfig(Config):
    DEBUG = False


# Maps FLASK_ENV values to config classes, used by app.py's app factory.
config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
