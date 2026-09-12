"""
models/alert.py
-----------------
Rows are created automatically (Phase 11) whenever a threshold is crossed:
flood_probability, drainage_utilization_pct, blockage_probability, or
water_depth_cm exceeding configured limits. drain_id is nullable because a
pure rainfall/flood alert may not be tied to any one drain.
"""

from extensions import db
from models.base import TimestampMixin


class Alert(db.Model, TimestampMixin):
    __tablename__ = "alerts"

    id = db.Column(db.Integer, primary_key=True)
    zone_id = db.Column(db.Integer, db.ForeignKey("zones.id"), nullable=False, index=True)
    drain_id = db.Column(db.Integer, db.ForeignKey("drains.id"), nullable=True)

    alert_type = db.Column(db.String(30), nullable=False)  # e.g. "FLOOD_RISK", "DRAIN_BLOCKAGE"
    severity = db.Column(db.String(10), nullable=False)  # LOW/MODERATE/HIGH/SEVERE
    message = db.Column(db.Text, nullable=False)
    recommended_action = db.Column(db.Text, nullable=True)
    time_to_critical_minutes = db.Column(db.Integer, nullable=True)

    status = db.Column(db.String(10), nullable=False, default="active")  # active / resolved

    zone = db.relationship("Zone", back_populates="alerts")
    drain = db.relationship("Drain")

    def to_dict(self):
        return {
            "id": self.id,
            "zone_id": self.zone_id,
            "drain_id": self.drain_id,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "message": self.message,
            "recommended_action": self.recommended_action,
            "time_to_critical_minutes": self.time_to_critical_minutes,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self):
        return f"<Alert zone={self.zone_id} {self.alert_type} {self.severity}>"
