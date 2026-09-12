"""
models/__init__.py
--------------------
SQLAlchemy only creates tables for models it has actually imported. This
file imports every model exactly once so that a single
`from models import *` (used in database/init_db.py) registers the entire
schema with `db.metadata` before `db.create_all()` runs.

If you add a new model file in Phase 3+, add its import here too, or
db.create_all() will silently skip that table.
"""

from models.base import TimestampMixin
from models.user import User
from models.zone import Zone
from models.location import Location
from models.rainfall import RainfallRecord
from models.weather_forecast import WeatherForecast
from models.drain import Drain
from models.drain_reading import DrainReading
from models.flood_prediction import FloodPrediction
from models.flood_event import FloodEvent
from models.alert import Alert
from models.route_segment import RouteSegment
from models.simulation_result import SimulationResult

__all__ = [
    "TimestampMixin",
    "User",
    "Zone",
    "Location",
    "RainfallRecord",
    "WeatherForecast",
    "Drain",
    "DrainReading",
    "FloodPrediction",
    "FloodEvent",
    "Alert",
    "RouteSegment",
    "SimulationResult",
]
