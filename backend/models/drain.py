"""
models/drain.py
----------------
Static metadata for a physical (or, for the demo, simulated) storm drain.
`normal_capacity_m3s` is the design flow rate when the drain is 100% clear;
`drainage.py` (Phase 4) combines this with the latest DrainReading's
blockage_percent to compute effective_capacity.
"""

from extensions import db
from models.base import TimestampMixin


class Drain(db.Model, TimestampMixin):
    __tablename__ = "drains"

    id = db.Column(db.Integer, primary_key=True)
    drain_code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    zone_id = db.Column(db.Integer, db.ForeignKey("zones.id"), nullable=False, index=True)

    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    normal_capacity_m3s = db.Column(db.Float, nullable=False)

    condition = db.Column(db.String(20), nullable=False, default="GOOD")  # GOOD / FAIR / POOR
    last_inspection_date = db.Column(db.Date, nullable=True)

    # NORMAL / WARNING / CRITICAL — mirrors the latest DrainReading.status
    # (denormalized here so /api/drains can list all drains without an N+1
    # query per drain; kept in sync whenever a new reading is written)
    status = db.Column(db.String(20), nullable=False, default="NORMAL")

    zone = db.relationship("Zone", back_populates="drains")
    readings = db.relationship(
        "DrainReading", back_populates="drain", lazy="dynamic",
        order_by="DrainReading.timestamp.desc()"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "drain_code": self.drain_code,
            "zone_id": self.zone_id,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "normal_capacity_m3s": self.normal_capacity_m3s,
            "condition": self.condition,
            "last_inspection_date": self.last_inspection_date.isoformat()
            if self.last_inspection_date else None,
            "status": self.status,
        }

    def __repr__(self):
        return f"<Drain {self.drain_code} zone={self.zone_id} status={self.status}>"
