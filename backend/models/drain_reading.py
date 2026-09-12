"""
models/drain_reading.py
------------------------
Time-series readings for a drain. `is_simulated` is critical for honesty in
the SIH demo: when a judge moves the blockage slider (Phase 7/13), the
resulting row is written with is_simulated=True so the system never implies
it has a real IoT sensor network it doesn't have.
"""

from extensions import db
from models.base import TimestampMixin


class DrainReading(db.Model, TimestampMixin):
    __tablename__ = "drain_readings"

    id = db.Column(db.Integer, primary_key=True)
    drain_id = db.Column(db.Integer, db.ForeignKey("drains.id"), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, nullable=False, index=True)

    current_flow_m3s = db.Column(db.Float, nullable=False)
    blockage_percent = db.Column(db.Float, nullable=False, default=0.0)  # 0-100
    estimated_capacity_m3s = db.Column(db.Float, nullable=False)
    blockage_probability = db.Column(db.Float, nullable=False, default=0.0)  # 0-1

    status = db.Column(db.String(20), nullable=False, default="NORMAL")  # NORMAL/WARNING/CRITICAL
    is_simulated = db.Column(db.Boolean, nullable=False, default=False)

    drain = db.relationship("Drain", back_populates="readings")

    __table_args__ = (
        db.Index("ix_drain_reading_drain_time", "drain_id", "timestamp"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "drain_id": self.drain_id,
            "timestamp": self.timestamp.isoformat(),
            "current_flow_m3s": self.current_flow_m3s,
            "blockage_percent": self.blockage_percent,
            "estimated_capacity_m3s": self.estimated_capacity_m3s,
            "blockage_probability": self.blockage_probability,
            "status": self.status,
            "is_simulated": self.is_simulated,
        }

    def __repr__(self):
        return f"<DrainReading drain={self.drain_id} {self.timestamp} blockage={self.blockage_percent}%>"
