"""
models/weather_forecast.py
---------------------------
Stores the raw hourly forecast pulled from Open-Meteo, cached so the
external API isn't called on every request (see utils/cache.py in Phase 3).
This is intentionally a superset of what RainfallRecord stores, because
weather_forecasts keeps ALL variables (temperature, humidity, wind,
pressure) for the weather dashboard, while rainfall_records is the
lean table the flood engine actually computes against.
"""

from extensions import db
from models.base import TimestampMixin


class WeatherForecast(db.Model, TimestampMixin):
    __tablename__ = "weather_forecasts"

    id = db.Column(db.Integer, primary_key=True)
    zone_id = db.Column(db.Integer, db.ForeignKey("zones.id"), nullable=False, index=True)
    forecast_time = db.Column(db.DateTime, nullable=False, index=True)

    precipitation_mm = db.Column(db.Float, nullable=True)
    precipitation_probability = db.Column(db.Float, nullable=True)  # 0-100, Open-Meteo may omit
    temperature_c = db.Column(db.Float, nullable=True)
    humidity_percent = db.Column(db.Float, nullable=True)
    wind_kmh = db.Column(db.Float, nullable=True)
    pressure_hpa = db.Column(db.Float, nullable=True)

    source = db.Column(db.String(30), nullable=False, default="open-meteo")

    zone = db.relationship("Zone", back_populates="weather_forecasts")

    def to_dict(self):
        return {
            "id": self.id,
            "zone_id": self.zone_id,
            "forecast_time": self.forecast_time.isoformat(),
            "precipitation_mm": self.precipitation_mm,
            "precipitation_probability": self.precipitation_probability,
            "temperature_c": self.temperature_c,
            "humidity_percent": self.humidity_percent,
            "wind_kmh": self.wind_kmh,
            "pressure_hpa": self.pressure_hpa,
            "source": self.source,
        }

    def __repr__(self):
        return f"<WeatherForecast zone={self.zone_id} {self.forecast_time}>"
