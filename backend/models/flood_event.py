"""
models/flood_event.py
-----------------------
Historical (or clearly-labeled demo) flood occurrences per zone. Two jobs:
1. Seeds the `historical_flood_frequency` label on Zone.
2. Supplies the `historical_flood_frequency` feature to ml/train.py.

`source` must always be "historical" or "demo" -- never blank -- so
train.py and the frontend can both tell real records from synthetic ones.
"""

from extensions import db
from models.base import TimestampMixin


class FloodEvent(db.Model, TimestampMixin):
    __tablename__ = "flood_events"

    id = db.Column(db.Integer, primary_key=True)
    zone_id = db.Column(db.Integer, db.ForeignKey("zones.id"), nullable=False, index=True)
    event_date = db.Column(db.Date, nullable=False)

    severity = db.Column(db.String(10), nullable=False)  # LOW/MODERATE/HIGH/SEVERE
    water_depth_cm = db.Column(db.Float, nullable=True)
    description = db.Column(db.Text, nullable=True)

    source = db.Column(db.String(15), nullable=False, default="demo")  # "historical" or "demo"

    zone = db.relationship("Zone", back_populates="flood_events")

    def to_dict(self):
        return {
            "id": self.id,
            "zone_id": self.zone_id,
            "event_date": self.event_date.isoformat(),
            "severity": self.severity,
            "water_depth_cm": self.water_depth_cm,
            "description": self.description,
            "source": self.source,
        }

    def __repr__(self):
        return f"<FloodEvent zone={self.zone_id} {self.event_date} {self.severity} ({self.source})>"
