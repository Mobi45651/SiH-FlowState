"""
models/simulation_result.py
------------------------------
Stores every what-if run from the Simulation page (Phase 13) so judges can
show a BEFORE/AFTER comparison and so results aren't lost on page refresh.
input_params is stored as a JSON string (portable on SQLite; migrate to a
native JSON/JSONB column on Postgres later) holding the raw request body.
"""

import json
from extensions import db
from models.base import TimestampMixin


class SimulationResult(db.Model, TimestampMixin):
    __tablename__ = "simulation_results"

    id = db.Column(db.Integer, primary_key=True)
    zone_id = db.Column(db.Integer, db.ForeignKey("zones.id"), nullable=False, index=True)

    input_params = db.Column(db.Text, nullable=False)  # JSON-encoded request body

    rainfall_mm_per_hour = db.Column(db.Float, nullable=False)
    duration_hours = db.Column(db.Float, nullable=False)
    drainage_blockage_percent = db.Column(db.Float, nullable=False)

    runoff_m3s = db.Column(db.Float, nullable=False)
    excess_flow_m3s = db.Column(db.Float, nullable=False)
    water_depth_cm = db.Column(db.Float, nullable=False)
    flood_probability = db.Column(db.Float, nullable=False)
    risk_category = db.Column(db.String(10), nullable=False)

    is_demo = db.Column(db.Boolean, nullable=False, default=True)

    zone = db.relationship("Zone", back_populates="simulation_results")

    def set_input_params(self, params: dict) -> None:
        self.input_params = json.dumps(params)

    def get_input_params(self) -> dict:
        return json.loads(self.input_params) if self.input_params else {}

    def to_dict(self):
        return {
            "id": self.id,
            "zone_id": self.zone_id,
            "input_params": self.get_input_params(),
            "rainfall_mm_per_hour": self.rainfall_mm_per_hour,
            "duration_hours": self.duration_hours,
            "drainage_blockage_percent": self.drainage_blockage_percent,
            "runoff_m3s": self.runoff_m3s,
            "excess_flow_m3s": self.excess_flow_m3s,
            "water_depth_cm": self.water_depth_cm,
            "flood_probability": self.flood_probability,
            "risk_category": self.risk_category,
            "is_demo": self.is_demo,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self):
        return f"<SimulationResult zone={self.zone_id} risk={self.risk_category}>"
