"""
routes/__init__.py
--------------------
register_blueprints(app) is the ONE place that wires up every route module.
In Phase 2 only health_routes exists; Phases 3-8 & 11-13 will each add one
import + one register_blueprint() line here and nowhere else in app.py.
"""

from flask import Flask


def register_blueprints(app: Flask) -> None:
    from routes.auth_routes import auth_bp
    app.register_blueprint(auth_bp, url_prefix="/api")

    from routes.admin_routes import admin_bp
    app.register_blueprint(admin_bp, url_prefix="/api")

    from routes.health_routes import health_bp
    app.register_blueprint(health_bp, url_prefix="/api")

    from routes.weather_routes import weather_bp
    app.register_blueprint(weather_bp, url_prefix="/api")

    from routes.rainfall_routes import rainfall_bp
    app.register_blueprint(rainfall_bp, url_prefix="/api")

    from routes.zone_routes import zone_bp
    app.register_blueprint(zone_bp, url_prefix="/api")

    from routes.flood_routes import flood_bp
    app.register_blueprint(flood_bp, url_prefix="/api")

    from routes.nowcast_routes import nowcast_bp
    app.register_blueprint(nowcast_bp, url_prefix="/api")

    from routes.explain_routes import explain_bp
    app.register_blueprint(explain_bp, url_prefix="/api")

    from routes.drain_routes import drain_bp
    app.register_blueprint(drain_bp, url_prefix="/api")

    from routes.route_routes import route_bp
    app.register_blueprint(route_bp, url_prefix="/api")

    from routes.alert_routes import alert_bp
    app.register_blueprint(alert_bp, url_prefix="/api")

    from routes.simulation_routes import simulation_bp
    app.register_blueprint(simulation_bp, url_prefix="/api")
