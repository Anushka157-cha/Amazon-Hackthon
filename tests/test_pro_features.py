"""Comprehensive test suite for HomeGuard Pro production features.

Tests:
1. 8 Simulated Fault Scenarios & Benchmark Accuracy (>= 90%)
2. 0 Unauthorized Repair Executions & 0 Duplicate Executions
3. Tamper-Evident Relational Database Hash Chain Validation
4. Explainable Bilingual (English + Hindi) Root Cause Diagnosis
5. Predictive Health Monitoring & Metric Anomaly Attribution
6. Safe Repair Policy State Machine, Concurrency Locking & Idempotency
7. Voice Assistant Intent Parsing (English & Hindi)
8. Device Adapters (Simulated, AsusWRT, Home Assistant, UniFi) & Subnet Discovery
9. MCP Tool Contracts (Metadata, Correlation IDs, Error Codes)
"""

import json
import pytest
from homeguard.adapters import (
    AsusWrtRouterAdapter,
    HomeAssistantAdapter,
    NetworkDiscoveryService,
    SimulatedDeviceAdapter,
    UniFiAdapter,
)
from homeguard.core import (
    DEVICE_ECHO_SPEAKER,
    DEVICE_FIRE_TV,
    DEVICE_RING_DOORBELL,
    DEVICE_ROUTER,
    DEVICE_WIFI_EXTENDER,
    HomeGuardEngine,
)
from homeguard.database import HomeGuardDatabase
from homeguard.diagnosis import ExplainableDiagnosisEngine
from homeguard.mcp_server import create_mcp_server
from homeguard.predictive import PredictiveHealthMonitor
from homeguard.repair_policy import RepairPolicyEngine
from homeguard.scenarios import BENCHMARK_SCENARIOS, run_benchmark_suite
from homeguard.voice_assistant import VoiceAssistant


@pytest.fixture
def pro_engine(tmp_path):
    log_path = str(tmp_path / "pro_audit.jsonl")
    db_path = str(tmp_path / "pro_test.db")
    return HomeGuardEngine(audit_log_path=log_path, db_path=db_path)


# 1. Benchmark Scenarios & RCA Accuracy Test
def test_all_8_benchmark_scenarios_and_accuracy(pro_engine):
    bench = run_benchmark_suite(pro_engine)
    assert bench["total_scenarios"] == 8
    assert bench["rca_accuracy_pct"] >= 90.0
    assert bench["meets_accuracy_target"] is True
    assert bench["unauthorized_executions"] == 0
    assert bench["duplicate_executions"] == 0


# 2. Database Relational Integrity & Cryptographic Hash Chain Test
def test_database_tamper_evident_audit_chain(tmp_path):
    db_path = str(tmp_path / "chain_test.db")
    log_path = str(tmp_path / "chain_log.jsonl")
    engine = HomeGuardEngine(audit_log_path=log_path, db_path=db_path)

    engine.inject_failure(DEVICE_WIFI_EXTENDER, mode="offline")
    prop = engine.propose_fix()
    engine.approve_fix(prop["incident_id"], user_confirmed=True)
    engine.verify_fix(prop["incident_id"], consecutive_ticks=3)

    # Verify cryptographic integrity
    integrity = engine.database.verify_audit_chain_integrity()
    assert integrity["valid"] is True
    assert integrity["count"] >= 4
    assert integrity["head_hash"] is not None


# 3. Explainable Bilingual Diagnosis Test
def test_bilingual_explainable_diagnosis(pro_engine):
    pro_engine.inject_failure(DEVICE_WIFI_EXTENDER, mode="offline")
    diag = pro_engine.diagnose_home()

    # English & Hindi presence
    assert "explanation_hindi" in diag
    assert "spoken_hindi" in diag
    assert "वाई-फाई एक्सटेंडर" in diag["explanation_hindi"] or "ऑफलाइन" in diag["explanation_hindi"]
    assert "Wi-Fi Extender" in diag["spoken"]

    # Facts vs Hypotheses separation
    assert "observed_facts" in diag
    assert len(diag["observed_facts"]) >= 2
    assert "inferred_hypotheses" in diag
    assert len(diag["inferred_hypotheses"]) >= 1

    # Candidate ranking
    assert len(diag["candidates"]) >= 1
    top_cand = diag["candidates"][0]
    assert top_cand["device_id"] == DEVICE_WIFI_EXTENDER
    assert top_cand["rank"] == 1
    assert top_cand["confidence"] >= 0.90


# 4. Predictive Health & Anomaly Attribution Test
def test_predictive_health_monitor():
    monitor = PredictiveHealthMonitor()
    # Test normal device
    normal_alerts = monitor.evaluate_device_health("router", "Router", {"latency_ms": 20.0, "packet_loss_pct": 0.0, "reconnects_24h": 0.0})
    assert len(normal_alerts) == 0

    # Test degraded device (packet loss)
    loss_alerts = monitor.evaluate_device_health("fire_tv", "Fire TV", {"latency_ms": 190.0, "packet_loss_pct": 12.5, "reconnects_24h": 5.0})
    assert len(loss_alerts) >= 2
    metrics = {a.metric for a in loss_alerts}
    assert "packet_loss_pct" in metrics
    assert "latency_ms" in metrics
    assert "12.5%" in loss_alerts[0].explanation or "190ms" in loss_alerts[1].explanation


# 5. Repair Policy State Machine & Concurrency Lock Test
def test_repair_policy_concurrency_and_idempotency(pro_engine):
    pro_engine.inject_failure(DEVICE_WIFI_EXTENDER, mode="offline")
    prop = pro_engine.propose_fix()
    inc_id = prop["incident_id"]

    # First approval succeeds
    appr1 = pro_engine.approve_fix(inc_id, user_confirmed=True)
    assert appr1["executed"] is True
    assert appr1["execution_id"] is not None

    # Immediate second approval fails (state is already EXECUTED, not PROPOSED)
    appr2 = pro_engine.approve_fix(inc_id, user_confirmed=True)
    assert appr2["executed"] is False
    assert appr2["error"] == "INVALID_STATE"


# 6. Voice Assistant Intent Parsing Test (English & Hindi)
def test_voice_assistant_intents():
    va = VoiceAssistant()

    # English tests
    assert va.parse_intent("What is wrong with my network?") == "DIAGNOSE_HOME"
    assert va.parse_intent("Yes, go ahead and restart it") == "APPROVE_FIX"
    assert va.parse_intent("No, cancel the repair") == "CANCEL_FIX"
    assert va.parse_intent("Please undo that change") == "ROLLBACK_FIX"
    assert va.parse_intent("Why did you reboot the extender?") == "EXPLAIN_REASON"

    # Hindi tests
    assert va.detect_language("क्या वाई-फाई ठीक है?") == "hi"
    assert va.parse_intent("हाँ, रीस्टार्ट करो") == "APPROVE_FIX"
    assert va.parse_intent("नहीं, रहने दो") == "CANCEL_FIX"
    assert va.parse_intent("पहले जैसा कर दो") == "ROLLBACK_FIX"
    assert va.parse_intent("यह क्यों हुआ?") == "EXPLAIN_REASON"


# 7. Device Adapters & Discovery Test
def test_device_adapters_and_discovery():
    sim = SimulatedDeviceAdapter()
    caps = sim.get_capabilities("wifi_extender")
    assert caps.can_reboot is True
    assert caps.can_band_steer is True

    probe = sim.probe_device("router", "online")
    assert probe.is_online is True
    assert probe.latency_ms > 0

    asus = AsusWrtRouterAdapter()
    assert asus.test_connection()["connected"] is True

    ha = HomeAssistantAdapter()
    assert ha.get_capabilities("smart_plug").can_power_cycle is True

    unifi = UniFiAdapter()
    assert unifi.execute_action("ap_living_room", "restart")["poe_cycled"] is True

    # Discovery
    nodes = NetworkDiscoveryService.scan_subnet()
    assert len(nodes) == 5
    assert nodes[0]["id"] == "router"
    assert nodes[1]["parent"] == "router"


# 8. MCP Server Pro Contracts Test
@pytest.mark.asyncio
async def test_mcp_pro_contracts(tmp_path):
    log_path = str(tmp_path / "mcp_pro_audit.jsonl")
    db_path = str(tmp_path / "mcp_pro_test.db")
    engine = HomeGuardEngine(audit_log_path=log_path, db_path=db_path)
    mcp_server, _ = create_mcp_server(engine)

    # Call get_status
    res = await mcp_server.call_tool("get_status", {})
    assert not res.is_error
    data = json.loads(res.content[0].text)
    assert data["version"] == "2.0.0"
    assert "correlation_id" in data
    assert data["total_devices"] == 5
    assert "spoken_hindi" in data

    # Inject failure and call diagnose
    engine.inject_failure(DEVICE_WIFI_EXTENDER, mode="offline")
    diag_res = await mcp_server.call_tool("diagnose", {})
    assert not diag_res.is_error
    diag_data = json.loads(diag_res.content[0].text)
    assert diag_data["has_incident"] is True
    assert diag_data["root_cause"] == DEVICE_WIFI_EXTENDER
    assert "correlation_id" in diag_data
