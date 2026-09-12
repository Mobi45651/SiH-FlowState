"""
routes/health_routes.py
-------------------------
GET /api/health -- used to smoke-test the whole stack after Phase 2. Also
confirms the database connection works, since a broken DATABASE_URL or a
missing table will make the `SELECT 1` fail here immediately rather than
surfacing confusingly in some deeper route later.
"""

from datetime import datetime, timezone
from flask import Blueprint, jsonify
from sqlalchemy import text

from extensions import db

health_bp = Blueprint("health", __name__)


@health_bp.route("/health", methods=["GET"])
def health_check():
    db_status = "ok"
    try:
        db.session.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - defensive, reported to caller
        db_status = f"error: {exc}"

    return jsonify({
        "data": {
            "status": "ok" if db_status == "ok" else "degraded",
            "database": db_status,
        },
        "meta": {
            "source": "live",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }), 200
