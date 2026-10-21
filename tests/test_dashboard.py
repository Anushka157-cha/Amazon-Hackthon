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


def test_tv_status_endpoint(client):
    client.post("/api/clear_failures")
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert "devices" in data
    assert "dependency_graph" in data
    assert "router" in data["dependency_graph"]
    assert "wifi_extender" in data["dependency_graph"]["router"]["downstream"]
    assert data["devices"]["router"]["status"] == "online"


def test_tv_diagnosis_endpoint(client):
    # Healthy check
    client.post("/api/clear_failures")
    diag_res = client.get("/api/diagnosis")
    assert diag_res.status_code == 200
    diag = diag_res.json()
    assert diag["has_incident"] is False
    assert diag["root_cause"] is None
    assert diag["confidence"] == 1.0

    # Injected outage check
    client.post(
        "/api/inject_failure",
        json={"device_id": "wifi_extender", "mode": "offline", "fail_verification": False},
    )
    diag_res2 = client.get("/api/diagnosis")
    assert diag_res2.status_code == 200
    diag2 = diag_res2.json()
    assert diag2["has_incident"] is True
    assert diag2["root_cause"] == "wifi_extender"
    assert "ring_doorbell" in diag2["victims"]
    assert "fire_tv" in diag2["victims"]
    assert "echo_speaker" in diag2["victims"]
    assert diag2["confidence"] >= 0.8
    assert len(diag2["summary"]) > 0


def test_tv_proposal_endpoint(client):
    client.post(
        "/api/inject_failure",
        json={"device_id": "wifi_extender", "mode": "offline", "fail_verification": False},
    )
    prop_res = client.get("/api/proposal")
    assert prop_res.status_code == 200
    prop = prop_res.json()
    assert prop["has_proposal"] is True
    assert prop["target_device"] == "wifi_extender"
    assert prop["action"] == "restart"
    assert "wifi_extender" in prop["devices_affected"]
    assert prop["duration"] > 0
    assert prop["tier"] in {"LOW", "MEDIUM", "HIGH"}
    assert prop["confirmation_required"] is True


def test_tv_approve_safety_rules(client):
    client.post("/api/clear_failures")

    # Safety Rule 1: Attempt approve when NO proposal exists
    refuse_res = client.post("/api/approve", json={"user_confirmed": True})
    assert refuse_res.status_code == 200
    assert refuse_res.json()["executed"] is False
    assert refuse_res.json()["error"] == "NO_PROPOSAL"

    # Now inject failure and generate proposal
    client.post(
        "/api/inject_failure",
        json={"device_id": "wifi_extender", "mode": "offline", "fail_verification": False},
    )
    prop_res = client.get("/api/proposal")
    inc_id = prop_res.json()["incident_id"]

    # Safety Rule 2: Attempt approve with user_confirmed = False
    reject_res = client.post(
        "/api/approve",
        json={"incident_id": inc_id, "user_confirmed": False},
    )
    assert reject_res.status_code == 200
    assert reject_res.json()["executed"] is False
    assert reject_res.json()["reason"] == "USER_NOT_CONFIRMED"

    # Need a fresh proposal now since previous was rejected
    prop_res2 = client.get("/api/proposal")
    inc_id2 = prop_res2.json()["incident_id"]

    # Safety Rule 3: Valid execution ONLY with user_confirmed = True
    exec_res = client.post(
        "/api/approve",
        json={"incident_id": inc_id2, "user_confirmed": True},
    )
    assert exec_res.status_code == 200
    assert exec_res.json()["executed"] is True
    assert exec_res.json()["verified"] is True


def test_tv_rollback_endpoint(client):
    # Setup failure and execute fix
    client.post(
        "/api/inject_failure",
        json={"device_id": "wifi_extender", "mode": "offline", "fail_verification": False},
    )
    prop = client.get("/api/proposal").json()
    client.post(
        "/api/approve",
        json={"incident_id": prop["incident_id"], "user_confirmed": True},
    )
    # Check that devices are online now
    assert client.get("/api/status").json()["devices"]["wifi_extender"]["status"] == "online"

    # Trigger rollback
    roll_res = client.post("/api/rollback", json={"incident_id": prop["incident_id"]})
    assert roll_res.status_code == 200
    assert roll_res.json()["rolled_back"] is True

    # Wi-Fi extender should be back to pre-fix state (offline)
    status_after = client.get("/api/status").json()
    assert status_after["devices"]["wifi_extender"]["status"] == "offline"


def test_tv_audit_endpoint(client):
    res = client.get("/api/audit")
    assert res.status_code == 200
    data = res.json()
    assert "entries" in data
    assert isinstance(data["entries"], list)
    assert len(data["entries"]) <= 20
    if data["entries"]:
        entry = data["entries"][-1]
        assert "timestamp" in entry
        assert "actor" in entry
        assert "action" in entry


def test_cors_headers(client):
    res = client.get("/api/status", headers={"Origin": "http://localhost:8081"})
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") in {"*", "http://localhost:8081"}

