"""
app.py
-------
Application factory. Running `python app.py` starts the dev server; running
`flask --app app init-db` or `flask --app app seed-db` (CLI commands
registered below) sets up the database. Every later phase adds its
blueprint registration here and nowhere else.

Connects to:
- config.py       -> supplies the Config object
- extensions.py   -> db, cors get bound to this specific app here
- models/__init__ -> imported (indirectly, via database/init_db.py) so
                     db.create_all() knows about every table
- routes/__init__ -> register_blueprints(app) wires up every blueprint
"""

import os
from flask import Flask, jsonify
from sqlalchemy import event, text

from config import config_by_name
from extensions import db, cors


def create_app(env: str | None = None) -> Flask:
    env = env or os.environ.get("FLASK_ENV", "development")
    app = Flask(__name__)
    app.config.from_object(config_by_name.get(env, config_by_name["development"]))

    # --- Bind extensions to this app instance ---
    db.init_app(app)

    # SQLite concurrency settings. WAL improves read/write concurrency and
    # busy_timeout lets a request wait briefly for another transaction.
    with app.app_context():
        try:
            db.session.execute(text("PRAGMA journal_mode=WAL"))
            db.session.execute(text("PRAGMA busy_timeout=30000"))
            db.session.commit()
        except Exception:
            db.session.rollback()
    cors.init_app(app, resources={r"/api/*": {"origins": app.config["ALLOWED_ORIGINS"]}})
    # Origins come from ALLOWED_ORIGINS in .env (comma-separated). Defaults
    # to common local Vite/CRA dev ports so `npm run dev` works out of the
    # box. Set this to your actual deployed frontend URL(s) in production
    # -- see .env.example.

    # --- Register blueprints ---
    from routes import register_blueprints
    register_blueprints(app)

    @app.teardown_request
    def cleanup_failed_transaction(exception=None):
        # Never leave a failed transaction holding a SQLite connection/lock.
        if exception is not None:
            try:
                db.session.rollback()
            except Exception:
                pass

    # --- Friendly root route so visiting http://localhost:5000/ isn't a 404 ---
    @app.route("/")
    def index():
        return jsonify({
            "service": "SIH26085 Urban Flood Nowcasting System — Backend",
            "status": "running",
            "health_check": "/api/health",
        })

    # --- CLI commands: `flask --app app init-db` / `flask --app app seed-db` ---
    @app.cli.command("init-db")
    def init_db_command():
        """Create all tables (does not drop existing ones)."""
        from database.init_db import init_db
        init_db(app)
        print("Database tables created.")

    @app.cli.command("seed-db")
    def seed_db_command():
        """Populate demo zones, drains, rainfall, events, and roads."""
        from database.seed import seed_db
        seed_db(app)
        print("Database seeded with demo data.")

    @app.cli.command("fix-gurugram-coordinates")
    def fix_gurugram_coordinates_command():
        """Verify/correct the canonical Gurugram monitoring coordinates.

        This is intentionally an explicit maintenance command so an old
        SQLite database can be repaired without deleting the rest of the
        demo data.
        """
        from models import Zone
        canonical = {
            "Z001": ("Gurugram City Centre", 28.4595, 77.0266),
            "Z002": ("Sector 15", 28.4597, 77.0520),
            "Z003": ("Sector 29", 28.4676, 77.0645),
            "Z004": ("Sector 31", 28.4486, 77.0550),
            "Z005": ("Sector 40", 28.4470, 77.0400),
            "Z006": ("Sector 44", 28.4424, 77.0515),
            "Z007": ("Sector 46", 28.4300, 77.0660),
            "Z008": ("Sector 52", 28.4476, 77.0905),
            "Z009": ("Sector 56", 28.4239, 77.1025),
            "Z010": ("Sector 57", 28.4146, 77.0912),
            "Z011": ("Sector 62", 28.4148, 77.1392),
            "Z012": ("DLF Cyber City", 28.4947, 77.0895),
            "Z013": ("Palam Vihar", 28.5152, 77.0780),
            "Z014": ("Golf Course Road", 28.4389, 77.1020),
            "Z015": ("Badshahpur", 28.4089, 77.0412),
            "Z016": ("Manesar", 28.3558, 76.9360),
        }
        with app.app_context():
            changed = 0
            for code, (name, lat, lng) in canonical.items():
                zone = Zone.query.filter_by(zone_code=code).first()
                if zone is None:
                    continue
                if zone.latitude != lat or zone.longitude != lng or zone.name != name:
                    zone.name = name
                    zone.latitude = lat
                    zone.longitude = lng
                    changed += 1
            db.session.commit()
        print(f"Verified canonical Gurugram coordinates. Updated {changed} zone(s).")

    @app.cli.command("run-pipeline")
    def run_pipeline_command():
        """Pull live weather (Open-Meteo) for every zone and store it.
        Falls back to clearly-labeled demo data per zone if the API call
        fails, instead of aborting the whole run."""
        from services.rainfall_pipeline import run_pipeline_for_all_zones
        with app.app_context():
            results = run_pipeline_for_all_zones()
        for r in results:
            tag = " [DEMO FALLBACK]" if r.get("used_demo_fallback") else ""
            print(f"{r['zone_code']}: {r['records_ingested']} records ({r['source']}){tag}")

    @app.cli.command("train-model")
    def train_model_command():
        """Trains the flood-risk Random Forest (on the synthetic demo
        dataset by default -- see ml/train.py for training on real data)."""
        from ml.train import train_model
        train_model()

    @app.cli.command("detect-blockages")
    def detect_blockages_command():
        """Runs the rule-based blockage estimator for every drain and
        writes a fresh (non-simulated) DrainReading for each."""
        from services.blockage_detector import detect_blockage_for_all_drains
        with app.app_context():
            results = detect_blockage_for_all_drains()
        for r in results:
            print(f"{r['drain_code']}: {r['estimated_blockage_percent']}% blocked -> {r['status']}")

    @app.cli.command("refresh-alerts")
    def refresh_alerts_command():
        """Run weather ingestion, model nowcasts and alert generation in one pass."""
        from services.rainfall_pipeline import run_pipeline_for_all_zones
        from services.alert_service import generate_alerts_for_all_zones
        with app.app_context():
            pipeline = run_pipeline_for_all_zones()
            created = generate_alerts_for_all_zones()
        print(f"Weather pipeline completed for {len(pipeline)} zones; {len(created)} alerts created.")

    @app.cli.command("generate-alerts")
    def generate_alerts_command():
        """Checks every zone/drain against the alert thresholds and
        creates/resolves alerts accordingly."""
        from services.alert_service import generate_alerts_for_all_zones
        with app.app_context():
            created = generate_alerts_for_all_zones()
        print(f"{len(created)} new alert(s) created.")
        for a in created:
            print(f"  [{a.severity}] {a.alert_type} -- {a.message}")

    return app


# Allows `python app.py` for local development in addition to `flask run`.
if __name__ == "__main__":
    application = create_app()
    application.run(host="0.0.0.0", port=5000, debug=application.config["DEBUG"], use_reloader=False, threaded=True)
