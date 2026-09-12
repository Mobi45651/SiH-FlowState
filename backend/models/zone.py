"""
models/zone.py
---------------
Zone is the hub of the whole schema. Every time-series table (rainfall,
weather, drains, predictions, events, alerts, route segments, simulations)
has a foreign key into `zones`. Static physical attributes that the runoff
and drainage calculations need (elevation, slope, impervious surface) live
here because they change rarely, unlike rainfall or drain readings.

Connects to:
- flood_engine/runoff.py    -> reads impervious_surface_percent as the "C"
                                coefficient proxy in Q = C x I x A
- flood_engine/risk.py      -> reads elevation_m, historical_flood_frequency
                                as explainability factors
- database/seed.py          -> creates 10-20 Zone rows for the demo
"""

from extensions import db
from models.base import TimestampMixin


class Zone(db.Model, TimestampMixin):
    __tablename__ = "zones"

    id = db.Column(db.Integer, primary_key=True)
    zone_code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)

    elevation_m = db.Column(db.Float, nullable=False)
    slope_percent = db.Column(db.Float, nullable=False)
    impervious_surface_percent = db.Column(db.Float, nullable=False)
    area_km2 = db.Column(db.Float, nullable=False)

    # LOW / MEDIUM / HIGH — derived from flood_events history at seed time,
    # used as an explainability factor, not recalculated live in Phase 2.
    historical_flood_frequency = db.Column(db.String(10), nullable=False, default="LOW")

    # --- Relationships ---
    locations = db.relationship("Location", back_populates="zone", lazy="dynamic")
    rainfall_records = db.relationship("RainfallRecord", back_populates="zone", lazy="dynamic")
    weather_forecasts = db.relationship("WeatherForecast", back_populates="zone", lazy="dynamic")
    drains = db.relationship("Drain", back_populates="zone", lazy="dynamic")
    flood_predictions = db.relationship("FloodPrediction", back_populates="zone", lazy="dynamic")
    flood_events = db.relationship("FloodEvent", back_populates="zone", lazy="dynamic")
    alerts = db.relationship("Alert", back_populates="zone", lazy="dynamic")
    route_segments = db.relationship("RouteSegment", back_populates="zone", lazy="dynamic")
    simulation_results = db.relationship("SimulationResult", back_populates="zone", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "zone_code": self.zone_code,
            "name": self.name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "elevation_m": self.elevation_m,
            "slope_percent": self.slope_percent,
            "impervious_surface_percent": self.impervious_surface_percent,
            "area_km2": self.area_km2,
            "historical_flood_frequency": self.historical_flood_frequency,
        }

    def __repr__(self):
        return f"<Zone {self.zone_code} {self.name}>"
