"""
models/location.py
-------------------
A named, searchable point (e.g. "City Bus Stand", "Railway Station") used
as the FROM/TO input for the Safe Route Planner (Phase 8). Every location
belongs to a Zone so its flood-risk context can be looked up instantly.
"""

from extensions import db
from models.base import TimestampMixin


class Location(db.Model, TimestampMixin):
    __tablename__ = "locations"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    address = db.Column(db.String(255), nullable=True)

    zone_id = db.Column(db.Integer, db.ForeignKey("zones.id"), nullable=False)
    zone = db.relationship("Zone", back_populates="locations")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "address": self.address,
            "zone_id": self.zone_id,
        }

    def __repr__(self):
        return f"<Location {self.name}>"
