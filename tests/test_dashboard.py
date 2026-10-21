"""Tests for HomeGuard Dashboard API and combined server."""

import pytest
from starlette.testclient import TestClient
from homeguard.dashboard import app


@pytest.fixture
def client():
    return TestClient(app)


def test_dashboard_homepage(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "HomeGuard" in res.text
    assert "SIMULATED DEVICES" in res.text


def test_status_api(client):
    # Ensure fresh online state
    client.post("/api/clear_failures")
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert data["simulated"] is True
    assert "devices" in data
    assert "router" in data["devices"]
    assert "diagnosis" in data
    assert "audit_log" in data


def test_inject_and_clear_failure_api(client):
    res = client.post(
        "/api/inject_failure",
        json={"device_id": "wifi_extender", "mode": "offline", "fail_verification": False},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "failure_injected"

    # Check status
    res2 = client.get("/api/status")
    status_data = res2.json()
    assert status_data["devices"]["wifi_extender"]["status"] == "offline"
    assert status_data["devices"]["ring_doorbell"]["status"] == "offline"
    assert status_data["devices"]["fire_tv"]["status"] == "degraded"
    assert status_data["diagnosis"]["root_cause"] == "wifi_extender"

    # Clear
    clear_res = client.post("/api/clear_failures")
    assert clear_res.status_code == 200
    status_data_cleared = client.get("/api/status").json()
    assert status_data_cleared["devices"]["wifi_extender"]["status"] == "online"
    assert status_data_cleared["diagnosis"]["has_incident"] is False


def test_propose_and_approve_api(client):
    client.post(
        "/api/inject_failure",
        json={"device_id": "wifi_extender", "mode": "offline", "fail_verification": False},
    )
    prop_res = client.post("/api/propose_fix", json={"simulate_verification_failure": False})
    assert prop_res.status_code == 200
    prop_data = prop_res.json()
    inc_id = prop_data["incident_id"]

    # Approve
    appr_res = client.post("/api/approve_fix", json={"incident_id": inc_id, "user_confirmed": True})
    assert appr_res.status_code == 200
    assert appr_res.json()["executed"] is True

    # Verify
    ver_res = client.post("/api/verify_fix", json={"incident_id": inc_id})
    assert ver_res.status_code == 200
    assert ver_res.json()["verified"] is True
