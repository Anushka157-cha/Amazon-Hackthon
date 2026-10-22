"""Unit tests for HomeGuard Core Engine."""

import os
import pytest
from homeguard.core import (
    HomeGuardEngine,
    DEVICE_ROUTER,
    DEVICE_WIFI_EXTENDER,
    DEVICE_RING_DOORBELL,
    DEVICE_FIRE_TV,
    DEVICE_ECHO_SPEAKER,
)


@pytest.fixture
def engine(tmp_path):
    log_path = str(tmp_path / "test_audit.jsonl")
    return HomeGuardEngine(audit_log_path=log_path)


def test_initial_state_healthy(engine):
    diag = engine.diagnose_home()
    assert diag["has_incident"] is False
    assert diag["root_cause"] is None
    assert diag["confidence"] == 1.0
    assert diag["simulated"] is True


def test_rca_identifies_wifi_extender_as_root_cause(engine):
    """RCA names wifi_extender as the single root cause and the other three as victims."""
    # Inject failure on wifi_extender
    engine.inject_failure(DEVICE_WIFI_EXTENDER, mode="offline")

    devices = engine.get_devices()
    assert devices[DEVICE_WIFI_EXTENDER]["status"] == "offline"
    assert devices[DEVICE_RING_DOORBELL]["status"] == "offline"
    assert devices[DEVICE_FIRE_TV]["status"] == "degraded"
    assert devices[DEVICE_ECHO_SPEAKER]["status"] == "offline"
    assert devices[DEVICE_ROUTER]["status"] == "online"

    # Run root-cause analysis
    diag = engine.diagnose_home()
    assert diag["has_incident"] is True
    assert diag["root_cause"] == DEVICE_WIFI_EXTENDER
    assert set(diag["victims"]) == {DEVICE_RING_DOORBELL, DEVICE_FIRE_TV, DEVICE_ECHO_SPEAKER}
    assert diag["confidence"] >= 0.90
    assert "wifi_extender" in diag["explanation"].lower() or "wi-fi extender" in diag["explanation"].lower()


def test_approve_fix_without_propose_refused(engine):
    """approve_fix without a prior propose_fix is refused."""
    res = engine.approve_fix(incident_id="non_existent_id", user_confirmed=True)
    assert res["executed"] is False
    assert res["error"] == "INCIDENT_NOT_FOUND"
    assert "Call propose_fix first" in res["message"]


def test_approve_fix_without_confirmation_refused(engine):
    """approve_fix without confirmation is refused."""
    engine.inject_failure(DEVICE_WIFI_EXTENDER, mode="offline")
    prop = engine.propose_fix()
    inc_id = prop["incident_id"]

    res = engine.approve_fix(incident_id=inc_id, user_confirmed=False)
    assert res["executed"] is False
    assert res["reason"] == "USER_NOT_CONFIRMED"
    # Ensure devices are still offline / degraded
    devices = engine.get_devices()
    assert devices[DEVICE_WIFI_EXTENDER]["status"] == "offline"


def test_verification_failure_triggers_auto_rollback(engine):
    """Verification failure triggers rollback and restores the previous state."""
    engine.inject_failure(DEVICE_WIFI_EXTENDER, mode="offline")
    prop = engine.propose_fix(simulate_verification_failure=True)
    inc_id = prop["incident_id"]

    # Approve with confirmation
    exec_res = engine.approve_fix(incident_id=inc_id, user_confirmed=True)
    assert exec_res["executed"] is True

    # Verify fix
    verify_res = engine.verify_fix(incident_id=inc_id, consecutive_ticks=3)
    assert verify_res["verified"] is False
    assert verify_res["auto_rollback"] is True

    # Pre-fix state must be restored
    devices = engine.get_devices()
    assert devices[DEVICE_WIFI_EXTENDER]["status"] == "offline"
    assert devices[DEVICE_RING_DOORBELL]["status"] == "offline"
    assert devices[DEVICE_FIRE_TV]["status"] == "degraded"
    assert devices[DEVICE_ECHO_SPEAKER]["status"] == "offline"


def test_successful_fix_and_verification(engine):
    """Normal flow: propose -> confirm -> execute -> verify succeeds."""
    engine.inject_failure(DEVICE_WIFI_EXTENDER, mode="offline")
    prop = engine.propose_fix(simulate_verification_failure=False)
    inc_id = prop["incident_id"]

    exec_res = engine.approve_fix(incident_id=inc_id, user_confirmed=True)
    assert exec_res["executed"] is True

    verify_res = engine.verify_fix(incident_id=inc_id, consecutive_ticks=3)
    assert verify_res["verified"] is True
    assert verify_res["state"] == "RESOLVED"

    devices = engine.get_devices()
    assert all(d["status"] == "online" for d in devices.values())


def test_reject_unknown_device_and_action(engine):
    """Unknown device or action is rejected."""
    with pytest.raises(ValueError, match="Unknown simulated device"):
        engine.inject_failure("smart_toaster", mode="offline")

    with pytest.raises(ValueError, match="Unknown simulated device"):
        engine.estimate_fix_impact("smart_toaster", action="restart")

    with pytest.raises(ValueError, match="Unknown fix action"):
        engine.estimate_fix_impact(DEVICE_WIFI_EXTENDER, action="factory_reset")


def test_audit_log_records_actions(engine):
    """Audit log records actions with timestamp, actor, target, and result."""
    engine.inject_failure(DEVICE_WIFI_EXTENDER, mode="offline", actor="system")
    engine.propose_fix(actor="user_voice")
    
    logs = engine.get_audit_log()
    assert len(logs) >= 2
    assert any(l["action"] == "inject_failure" and l["target"] == DEVICE_WIFI_EXTENDER for l in logs)
    assert any(l["action"] == "propose_fix" for l in logs)


def test_stale_proposal_is_rejected(engine):
    engine.inject_failure(DEVICE_WIFI_EXTENDER, mode="offline")
    proposal = engine.propose_fix()
    engine.inject_failure(DEVICE_WIFI_EXTENDER, mode="degraded")

    result = engine.approve_fix(proposal["incident_id"], user_confirmed=True)

    assert result["executed"] is False
    assert result["error"] == "STALE_PROPOSAL"


def test_audit_log_is_hash_chained(engine):
    engine.inject_failure(DEVICE_WIFI_EXTENDER, mode="offline")
    entries = engine.get_audit_log()

    assert entries[0]["entry_hash"]
    if len(entries) > 1:
        assert entries[1]["previous_hash"] == entries[0]["entry_hash"]


def test_health_history_and_report(engine):
    engine.inject_failure(DEVICE_WIFI_EXTENDER, mode="offline")
    proposal = engine.propose_fix()
    report = engine.get_incident_report(proposal["incident_id"])

    assert len(engine.get_health_history()) >= 2
    assert report["incident"]["incident_id"] == proposal["incident_id"]
    assert report["events"]
