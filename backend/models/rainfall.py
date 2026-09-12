"""
models/rainfall.py
-------------------
One row per zone per timestamp. `source` is the field that lets the whole
system honestly distinguish real recorded rain ("observed") from Open-Meteo's
forecast values ("forecast") -- this is what the frontend uses to badge
every rainfall number instead of presenting it all as one undifferentiated
number.

Connects to:
- services/weather_service.py -> writes rows here after cleaning a pull
- flood_engine/runoff.py       -> reads recent rows to compute rainfall
                                   intensity / cumulative rainfall
"""

from extensions import db
from models.base import TimestampMixin

# "observed"  -> a real rain-gauge reading (not yet wired up in this prototype)
# "forecast"  -> a real Open-Meteo forecast value, ingested live
# "demo"      -> synthetic data used only when the live API call failed and
#                a demo fallback was explicitly requested (see
#                services/weather_service.py). Never silently mixed with
#                "forecast" so the frontend can always show an honest badge.
VALID_SOURCES = ("observed", "forecast", "demo")


class RainfallRecord(db.Model, TimestampMixin):
    __tablename__ = "rainfall_records"

    id = db.Column(db.Integer, primary_key=True)
    zone_id = db.Column(db.Integer, db.ForeignKey("zones.id"), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, nullable=False, index=True)
    rainfall_mm = db.Column(db.Float, nullable=False)
    source = db.Column(db.String(10), nullable=False)  # "observed" or "forecast"

    zone = db.relationship("Zone", back_populates="rainfall_records")

    __table_args__ = (
        db.Index("ix_rainfall_zone_time", "zone_id", "timestamp"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "zone_id": self.zone_id,
            "timestamp": self.timestamp.isoformat(),
            "rainfall_mm": self.rainfall_mm,
            "source": self.source,
        }

    def __repr__(self):
        return f"<RainfallRecord zone={self.zone_id} {self.timestamp} {self.rainfall_mm}mm ({self.source})>"
