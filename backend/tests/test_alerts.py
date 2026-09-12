"""
tests/test_alerts.py
------------------------
Run with: pytest backend/tests/test_alerts.py -v
"""

from unittest.mock import patch

from extensions import db
from models import Zone, Drain, DrainReading, Alert
from services.alert_service import generate_alerts_for_zone
from utils.time_utils import utc_now


def make_zone(code="ZA01", impervious=85):
    zone = Zone(
        zone_code=code, name=f"Alert {code}", latitude=19.1, longitude=72.85,
        elevation_m=180, slope_percent=1, impervious_surface_percent=impervious,
        area_km2=2.0, historical_flood_frequency="HIGH",
    )
    db.session.add(zone)
    db.session.commit()
    return zone


def add_drain_with_reading(zone, capacity=3.0, blockage_percent=0, blockage_probability=0.1):
    drain = Drain(drain_code=f"{zone.zone_code}-D01", zone_id=zone.id, latitude=19.1,
                   longitude=72.85, normal_capacity_m3s=capacity, condition="GOOD", status="NORMAL")
    db.session.add(drain)
    db.session.commit()
    db.session.add(DrainReading(
        drain_id=drain.id, timestamp=utc_now(),
        current_flow_m3s=1.0, blockage_percent=blockage_percent,
        estimated_capacity_m3s=capacity * (1 - blockage_percent / 100),
        blockage_probability=blockage_probability, status="NORMAL", is_simulated=True,
    ))
    db.session.commit()
    return drain


def fake_nowcast(risk_category, flood_probability, drainage_utilization_pct, water_depth_cm):
    return {
        "zone_id": 1, "zone_code": "ZA01", "zone_name": "Alert Zone",
        "forecast": [
            {
                "offset_minutes": 0, "risk_category": risk_category,
                "flood_probability": flood_probability,
                "drainage_utilization_pct": drainage_utilization_pct,
                "water_depth_cm": water_depth_cm,
            },
            {"offset_minutes": 180, "risk_category": "SEVERE"},
        ],
    }


@patch("services.nowcast_engine.build_zone_nowcast")
def test_high_risk_creates_flood_alert(mock_nowcast, app):
    zone = make_zone()
    mock_nowcast.return_value = fake_nowcast("HIGH", 0.7, 60, 5)

    created = generate_alerts_for_zone(zone)

    types = {a.alert_type for a in created}
    assert "FLOOD_RISK" in types
    active = Alert.query.filter_by(zone_id=zone.id, alert_type="FLOOD_RISK", status="active").all()
    assert len(active) == 1


@patch("services.nowcast_engine.build_zone_nowcast")
def test_low_risk_creates_no_flood_alert(mock_nowcast, app):
    zone = make_zone("ZA02")
    mock_nowcast.return_value = fake_nowcast("LOW", 0.1, 20, 0)

    created = generate_alerts_for_zone(zone)

    assert not any(a.alert_type == "FLOOD_RISK" for a in created)


@patch("services.nowcast_engine.build_zone_nowcast")
def test_drainage_overload_alert(mock_nowcast, app):
    zone = make_zone("ZA03")
    mock_nowcast.return_value = fake_nowcast("HIGH", 0.6, 150, 10)

    created = generate_alerts_for_zone(zone)

    assert any(a.alert_type == "DRAINAGE_OVERLOAD" for a in created)


@patch("services.nowcast_engine.build_zone_nowcast")
def test_water_depth_alert(mock_nowcast, app):
    zone = make_zone("ZA04")
    mock_nowcast.return_value = fake_nowcast("HIGH", 0.6, 50, 25)

    created = generate_alerts_for_zone(zone)

    assert any(a.alert_type == "WATER_DEPTH" for a in created)


@patch("services.nowcast_engine.build_zone_nowcast")
def test_rerun_resolves_old_alert_instead_of_duplicating(mock_nowcast, app):
    zone = make_zone("ZA05")
    mock_nowcast.return_value = fake_nowcast("HIGH", 0.7, 60, 5)

    generate_alerts_for_zone(zone)
    generate_alerts_for_zone(zone)  # re-run with the same still-high conditions

    active = Alert.query.filter_by(zone_id=zone.id, alert_type="FLOOD_RISK", status="active").all()
    resolved = Alert.query.filter_by(zone_id=zone.id, alert_type="FLOOD_RISK", status="resolved").all()
    assert len(active) == 1  # not 2 -- the first run's alert was resolved, not left active
    assert len(resolved) == 1


@patch("services.nowcast_engine.build_zone_nowcast")
def test_conditions_improving_resolves_alert(mock_nowcast, app):
    zone = make_zone("ZA06")
    mock_nowcast.return_value = fake_nowcast("HIGH", 0.7, 60, 5)
    generate_alerts_for_zone(zone)

    mock_nowcast.return_value = fake_nowcast("LOW", 0.1, 20, 0)
    generate_alerts_for_zone(zone)

    active = Alert.query.filter_by(zone_id=zone.id, alert_type="FLOOD_RISK", status="active").all()
    assert len(active) == 0


@patch("services.nowcast_engine.build_zone_nowcast")
def test_drain_blockage_alert(mock_nowcast, app):
    zone = make_zone("ZA07")
    add_drain_with_reading(zone, blockage_percent=60, blockage_probability=0.8)
    mock_nowcast.return_value = fake_nowcast("LOW", 0.1, 20, 0)

    created = generate_alerts_for_zone(zone)

    assert any(a.alert_type == "DRAIN_BLOCKAGE" for a in created)
