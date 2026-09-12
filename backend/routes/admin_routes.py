"""Authority/admin read endpoint for the existing FlowState UI.

Authentication intentionally reuses the project's existing X-User-Email
contract so the visual frontend does not need a redesign. Production should
replace this demo header contract with a real session/JWT middleware.
"""
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request
from models import User, Zone, Drain, Alert, RouteSegment

admin_bp = Blueprint("admin", __name__)

def _admin_user():
    email = request.headers.get("X-User-Email", "").strip().lower()
    user = User.query.filter_by(email=email).first() if email else None
    return user if user and user.role == "admin" else None

@admin_bp.get("/admin/overview")
def overview():
    if _admin_user() is None:
        return jsonify({"data": None, "error": "Admin authentication required."}), 403
    active = Alert.query.filter_by(status="active").count()
    high_roads = RouteSegment.query.filter(RouteSegment.risk_category.in_(["HIGH", "SEVERE"])).count()
    critical_drains = Drain.query.filter_by(status="CRITICAL").count()
    return jsonify({"data": {"zones": Zone.query.count(), "drains": Drain.query.count(), "road_segments": RouteSegment.query.count(), "active_alerts": active, "high_risk_roads": high_roads, "critical_drains": critical_drains, "generated_at": datetime.now(timezone.utc).isoformat()}, "meta": {"source": "database"}})
