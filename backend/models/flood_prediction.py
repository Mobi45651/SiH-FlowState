"""
models/flood_prediction.py
----------------------------
This is the output table of the entire flood_engine + ml pipeline (Phases
4-6). One row per zone per nowcast timestep (7 rows per zone per run: now,
+30min, +1h, +1.5h, +2h, +2.5h, +3h). /api/nowcast and /api/flood-risk both
read from here rather than recomputing on every request.
"""

from extensions import db
from models.base import TimestampMixin


class FloodPrediction(db.Model, TimestampMixin):
    __tablename__ = "flood_predictions"

    id = db.Column(db.Integer, primary_key=True)
    zone_id = db.Column(db.Integer, db.ForeignKey("zones.id"), nullable=False, index=True)
    forecast_time = db.Column(db.DateTime, nullable=False, index=True)

    rainfall_mm = db.Column(db.Float, nullable=False)
    runoff_m3s = db.Column(db.Float, nullable=False)
    drainage_capacity_m3s = db.Column(db.Float, nullable=False)
    drainage_utilization_pct = db.Column(db.Float, nullable=False)
    excess_flow_m3s = db.Column(db.Float, nullable=False)
    water_depth_cm = db.Column(db.Float, nullable=False)

    flood_probability = db.Column(db.Float, nullable=False)  # 0-1, from risk.py
    risk_category = db.Column(db.String(10), nullable=False)  # LOW/MODERATE/HIGH/SEVERE

    # Which model produced flood_probability, e.g. "rf_v1" or "rule_based_v1"
    # (Phase 6 ML model may not exist yet on first runs, so risk.py falls
    # back to a rule-based score and records that here for transparency)
    model_version = db.Column(db.String(30), nullable=False, default="rule_based_v1")

    zone = db.relationship("Zone", back_populates="flood_predictions")

    __table_args__ = (
        db.Index("ix_prediction_zone_time", "zone_id", "forecast_time"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "zone_id": self.zone_id,
            "forecast_time": self.forecast_time.isoformat(),
            "rainfall_mm": self.rainfall_mm,
            "runoff_m3s": self.runoff_m3s,
            "drainage_capacity_m3s": self.drainage_capacity_m3s,
            "drainage_utilization_pct": self.drainage_utilization_pct,
            "excess_flow_m3s": self.excess_flow_m3s,
            "water_depth_cm": self.water_depth_cm,
            "flood_probability": self.flood_probability,
            "risk_category": self.risk_category,
            "model_version": self.model_version,
        }

    def __repr__(self):
        return f"<FloodPrediction zone={self.zone_id} {self.forecast_time} risk={self.risk_category}>"
