"""
database/seed.py
------------------
Populates the database with the synthetic demo dataset from
utils/demo_data_generator.py: 15 zones, ~60 drains, 48 hours of hourly
rainfall history per zone, demo flood events, and a small road-segment
graph. Idempotent -- if zones already exist, it skips seeding instead of
creating duplicates, so `flask --app app seed-db` is safe to run more than
once.

Usage:
    flask --app app seed-db
or, standalone:
    python -m database.seed
"""

from flask import Flask
from extensions import db
from models import Zone, Drain, DrainReading, RainfallRecord, FloodEvent, RouteSegment
from utils.demo_data_generator import (
    generate_zones,
    generate_drains,
    generate_initial_drain_readings,
    generate_rainfall_history,
    generate_flood_events,
    generate_route_segments,
)


def seed_db(app: Flask) -> None:
    with app.app_context():
        # Keep the demo admin available even when the rest of the demo data
        # has already been seeded.
        from models import User
        admin_email = app.config["ADMIN_EMAIL"]
        if User.query.filter_by(email=admin_email).first() is None:
            admin = User(
                username=app.config["ADMIN_USERNAME"],
                email=admin_email,
                role="admin",
            )
            admin.set_password(app.config["ADMIN_PASSWORD"])
            db.session.add(admin)
            db.session.commit()
            print(f"Created admin account: {admin_email}")

        if Zone.query.first() is not None:
            print("Zones already exist -- skipping seed. Delete the .db file to reseed.")
            return

        # --- Zones ---
        zone_dicts = generate_zones()
        zone_objs = {}
        for zd in zone_dicts:
            zone = Zone(**zd)
            db.session.add(zone)
            zone_objs[zd["zone_code"]] = zone
        db.session.flush()  # assigns zone.id without committing yet

        zone_codes = list(zone_objs.keys())

        # --- Drains ---
        drain_dicts = generate_drains(zone_dicts)
        drain_objs = {}
        for dd in drain_dicts:
            zone_code = dd.pop("zone_code")
            drain = Drain(zone_id=zone_objs[zone_code].id, **dd)
            db.session.add(drain)
            drain_objs[drain.drain_code] = drain
        db.session.flush()

        drain_codes = list(drain_objs.keys())

        # --- Initial drain readings ---
        for rd in generate_initial_drain_readings(drain_dicts):
            drain_code = rd.pop("drain_code")
            db.session.add(DrainReading(drain_id=drain_objs[drain_code].id, **rd))

        # --- Rainfall history (48 hours, observed) ---
        for rr in generate_rainfall_history(zone_codes, hours_back=48):
            zone_code = rr.pop("zone_code")
            db.session.add(RainfallRecord(zone_id=zone_objs[zone_code].id, **rr))

        # --- Flood events (demo, count driven by each zone's frequency label) ---
        for zd in zone_dicts:
            for fe in generate_flood_events(zd["zone_code"], zd["historical_flood_frequency"]):
                zone_code = fe.pop("zone_code")
                db.session.add(FloodEvent(zone_id=zone_objs[zone_code].id, **fe))

        # --- Route segments ---
        for rs in generate_route_segments(zone_dicts):
            zone_code = rs.pop("zone_code")
            db.session.add(RouteSegment(zone_id=zone_objs[zone_code].id, **rs))

        db.session.commit()
        print(
            f"Seeded {len(zone_dicts)} zones, {len(drain_dicts)} drains, "
            f"{len(zone_codes) * 48} rainfall records, route segments, and demo flood events."
        )


if __name__ == "__main__":
    from app import create_app
    application = create_app()
    seed_db(application)
