"""
tests/test_health.py
----------------------
Smoke test for Phase 2: confirms the Flask app boots, the database
connection works, and /api/health returns the expected envelope shape.

Run with:  pytest backend/tests/test_health.py -v
"""


def test_health_check_returns_ok(client):
    response = client.get("/api/health")
    assert response.status_code == 200

    body = response.get_json()
    assert body["data"]["status"] == "ok"
    assert body["data"]["database"] == "ok"
    assert "generated_at" in body["meta"]


def test_root_route_returns_service_info(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.get_json()
    assert body["service"].startswith("SIH26085")
