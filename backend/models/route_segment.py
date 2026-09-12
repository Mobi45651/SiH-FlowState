"""
models/route_segment.py
-------------------------
A simple edge in the demo road graph used by services/routing_service.py
(Phase 8) when no real routing API key is configured. Storing segments
in the DB (rather than hardcoding them in Python) lets risk_category be
updated live as flood predictions change, so the route planner's notion
of "risky road" stays consistent with the rest of the system.
"""

from extensions import db
from models.base import TimestampMixin


class RouteSegment(db.Model, TimestampMixin):
    __tablename__ = "route_segments"

    id = db.Column(db.Integer, primary_key=True)
    road_name = db.Column(db.String(150), nullable=False)

    start_lat = db.Column(db.Float, nullable=False)
    start_lng = db.Column(db.Float, nullable=False)
    end_lat = db.Column(db.Float, nullable=False)
    end_lng = db.Column(db.Float, nullable=False)

    zone_id = db.Column(db.Integer, db.ForeignKey("zones.id"), nullable=False, index=True)
    risk_category = db.Column(db.String(10), nullable=False, default="LOW")
    distance_km = db.Column(db.Float, nullable=False)
    is_flood_prone = db.Column(db.Boolean, nullable=False, default=False)

    zone = db.relationship("Zone", back_populates="route_segments")

    def to_dict(self):
        return {
            "id": self.id,
            "road_name": self.road_name,
            "start_lat": self.start_lat,
            "start_lng": self.start_lng,
            "end_lat": self.end_lat,
            "end_lng": self.end_lng,
            "zone_id": self.zone_id,
            "risk_category": self.risk_category,
            "distance_km": self.distance_km,
            "is_flood_prone": self.is_flood_prone,
        }

    def __repr__(self):
        return f"<RouteSegment {self.road_name} risk={self.risk_category}>"
