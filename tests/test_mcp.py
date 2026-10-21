"""Unit tests for HomeGuard MCP Server tools."""

import json
import pytest
from homeguard.core import (
    DEVICE_ROUTER,
    DEVICE_WIFI_EXTENDER,
    DEVICE_RING_DOORBELL,
    DEVICE_FIRE_TV,
    DEVICE_ECHO_SPEAKER,
    HomeGuardEngine,
)
from homeguard.mcp_server import create_mcp_server


@pytest.fixture
def test_setup(tmp_path):
    log_path = str(tmp_path / "test_mcp_audit.jsonl")
    engine = HomeGuardEngine(audit_log_path=log_path)
    mcp_server, _ = create_mcp_server(engine)
    return mcp_server, engine


async def call_tool_json(mcp_server, tool_name: str, arguments: dict):
    res = await mcp_server.call_tool(tool_name, arguments)
    assert not res.is_error
    # Parse json text content
    return json.loads(res.content[0].text)


@pytest.mark.asyncio
async def test_home_status_tool(test_setup):
    mcp_server, engine = test_setup
    data = await call_tool_json(mcp_server, "home_status", {})
    assert data["simulated"] is True
    assert data["online_count"] == 5
    assert "online and working normally" in data["spoken"]

    # Inject failure and check spoken wording
    engine.inject_failure(DEVICE_WIFI_EXTENDER, mode="offline")
    data2 = await call_tool_json(mcp_server, "home_status", {})
    assert data2["unhealthy_count"] == 4
    assert "Wi-Fi Extender" in data2["spoken"]
    assert "Fire TV" in data2["spoken"]


@pytest.mark.asyncio
async def test_diagnose_home_tool(test_setup):
    mcp_server, engine = test_setup
    engine.inject_failure(DEVICE_WIFI_EXTENDER, mode="offline")

    diag = await call_tool_json(mcp_server, "diagnose_home", {})
    assert diag["simulated"] is True
    assert diag["has_incident"] is True
    assert diag["root_cause"] == DEVICE_WIFI_EXTENDER
    assert set(diag["victims"]) == {DEVICE_RING_DOORBELL, DEVICE_FIRE_TV, DEVICE_ECHO_SPEAKER}
    assert diag["confidence"] >= 0.90
    assert "spoken" in diag
    assert "Wi-Fi Extender" in diag["spoken"]


@pytest.mark.asyncio
async def test_propose_and_approve_fix_flow(test_setup):
    mcp_server, engine = test_setup
    engine.inject_failure(DEVICE_WIFI_EXTENDER, mode="offline")

    # 1. Propose fix
    prop = await call_tool_json(mcp_server, "propose_fix", {})
    assert prop["simulated"] is True
    assert prop["action"] == "restart"
    assert prop["target_device"] == DEVICE_WIFI_EXTENDER
    assert prop["confirmation_required"] is True
    assert prop["spoken"].endswith("?")  # Ends by asking user to confirm
    inc_id = prop["incident_id"]

    # 2. Refusal when user_confirmed is False
    rejected = await call_tool_json(
        mcp_server, "approve_fix", {"incident_id": inc_id, "user_confirmed": False}
    )
    assert rejected["executed"] is False
    assert rejected["reason"] == "USER_NOT_CONFIRMED"

    # 3. Create fresh proposal and approve with user_confirmed=True
    prop2 = await call_tool_json(mcp_server, "propose_fix", {})
    inc_id2 = prop2["incident_id"]
    approved = await call_tool_json(
        mcp_server, "approve_fix", {"incident_id": inc_id2, "user_confirmed": True}
    )
    assert approved["executed"] is True
    assert "restarted" in approved["spoken"]

    # 4. Verify fix succeeds
    verified = await call_tool_json(
        mcp_server, "verify_fix", {"incident_id": inc_id2}
    )
    assert verified["verified"] is True
    assert verified["state"] == "RESOLVED"
    assert "stabilized" in verified["spoken"]


@pytest.mark.asyncio
async def test_approve_fix_refused_without_prior_propose(test_setup):
    mcp_server, _ = test_setup
    res = await call_tool_json(
        mcp_server, "approve_fix", {"incident_id": "random_fake_id", "user_confirmed": True}
    )
    assert res["executed"] is False
    assert res["error"] == "INCIDENT_NOT_FOUND"
    assert "couldn't find" in res["spoken"].lower()


@pytest.mark.asyncio
async def test_verification_failure_and_auto_rollback(test_setup):
    mcp_server, engine = test_setup
    engine.inject_failure(DEVICE_WIFI_EXTENDER, mode="offline")

    # Set up failure scenario
    prop = engine.propose_fix(simulate_verification_failure=True)
    inc_id = prop["incident_id"]

    # Approve fix
    appr = await call_tool_json(
        mcp_server, "approve_fix", {"incident_id": inc_id, "user_confirmed": True}
    )
    assert appr["executed"] is True

    # Verify fails and auto-rolls back
    ver = await call_tool_json(
        mcp_server, "verify_fix", {"incident_id": inc_id}
    )
    assert ver["verified"] is False
    assert ver["auto_rollback"] is True
    assert "automatically rolled back" in ver["spoken"]

    # Check device states restored
    devices = engine.get_devices()
    assert devices[DEVICE_WIFI_EXTENDER]["status"] == "offline"


@pytest.mark.asyncio
async def test_manual_rollback_tool(test_setup):
    mcp_server, engine = test_setup
    engine.inject_failure(DEVICE_WIFI_EXTENDER, mode="offline")
    prop = engine.propose_fix()
    inc_id = prop["incident_id"]
    await call_tool_json(
        mcp_server, "approve_fix", {"incident_id": inc_id, "user_confirmed": True}
    )

    # Rollback
    rb = await call_tool_json(mcp_server, "rollback_fix", {"incident_id": inc_id})
    assert rb["rolled_back"] is True
    assert "restored your devices" in rb["spoken"]
    devices = engine.get_devices()
    assert devices[DEVICE_WIFI_EXTENDER]["status"] == "offline"


@pytest.mark.asyncio
async def test_reject_unknown_device_and_action_mcp(test_setup):
    mcp_server, engine = test_setup
    with pytest.raises(ValueError, match="Unknown simulated device"):
        engine.inject_failure("unknown_thermostat", mode="offline")

    with pytest.raises(ValueError, match="Unknown fix action"):
        engine.estimate_fix_impact(DEVICE_WIFI_EXTENDER, action="factory_reset")

