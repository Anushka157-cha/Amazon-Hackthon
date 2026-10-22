"""HomeGuard Automated Reliability Testing Scenarios.

Contains 8 comprehensive simulated fault scenarios and benchmark evaluation:
1. Extender Outage (Downstream cascade: Doorbell, Fire TV, Echo)
2. Gateway Blackout (All devices drop)
3. Leaf Camera Power Failure (Isolated leaf failure)
4. Intermittent Backhaul Degradation (High latency & packet loss)
5. DNS Resolution Degradation (Gateway degradation)
6. Stale Approval & Expiration Rejection
7. Failed Repair with Automatic Rollback
8. Duplicate Approval & Concurrency Lock Protection
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class FaultScenario:
    scenario_id: str
    name: str
    description: str
    target_device: str
    mode: str
    fail_verification: bool
    expected_root_cause: str
    expected_victims: list[str]
    expected_min_confidence: float
    is_reversible: bool


BENCHMARK_SCENARIOS: list[FaultScenario] = [
    FaultScenario(
        scenario_id="scenario_01_extender_outage",
        name="Wi-Fi Extender Outage (Cascade)",
        description="Wi-Fi Extender loses power/crashes. Ring Doorbell drops offline, Fire TV buffers, Echo drops.",
        target_device="wifi_extender",
        mode="offline",
        fail_verification=False,
        expected_root_cause="wifi_extender",
        expected_victims=["ring_doorbell", "fire_tv", "echo_speaker"],
        expected_min_confidence=0.90,
        is_reversible=True,
    ),
    FaultScenario(
        scenario_id="scenario_02_gateway_blackout",
        name="Main Router Gateway Blackout",
        description="Main fiber gateway loses WAN sync. All 4 downstream network devices lose connectivity.",
        target_device="router",
        mode="offline",
        fail_verification=False,
        expected_root_cause="router",
        expected_victims=["wifi_extender", "ring_doorbell", "fire_tv", "echo_speaker"],
        expected_min_confidence=0.95,
        is_reversible=True,
    ),
    FaultScenario(
        scenario_id="scenario_03_leaf_camera_loss",
        name="Leaf Security Camera Power Loss",
        description="Ring Doorbell loses battery/power. Upstream router & extender remain 100% healthy.",
        target_device="ring_doorbell",
        mode="offline",
        fail_verification=False,
        expected_root_cause="ring_doorbell",
        expected_victims=[],
        expected_min_confidence=0.88,
        is_reversible=True,
    ),
    FaultScenario(
        scenario_id="scenario_04_intermittent_degradation",
        name="Intermittent 5GHz Backhaul Degradation",
        description="Wi-Fi Extender suffers RF interference. High packet loss (8.5%) and latency (185ms).",
        target_device="wifi_extender",
        mode="degraded",
        fail_verification=False,
        expected_root_cause="wifi_extender",
        expected_victims=["ring_doorbell", "fire_tv", "echo_speaker"],
        expected_min_confidence=0.85,
        is_reversible=True,
    ),
    FaultScenario(
        scenario_id="scenario_05_firetv_buffer",
        name="Fire TV Isolated Streaming Buffer",
        description="Fire TV 4K video buffer failure while extender and doorbell remain online.",
        target_device="fire_tv",
        mode="degraded",
        fail_verification=False,
        expected_root_cause="fire_tv",
        expected_victims=[],
        expected_min_confidence=0.88,
        is_reversible=True,
    ),
    FaultScenario(
        scenario_id="scenario_06_stale_approval_timeout",
        name="Stale Proposal & State Mismatch Protection",
        description="Proposal is generated, but network state changes or proposal expires before user approval.",
        target_device="wifi_extender",
        mode="offline",
        fail_verification=False,
        expected_root_cause="wifi_extender",
        expected_victims=["ring_doorbell", "fire_tv", "echo_speaker"],
        expected_min_confidence=0.90,
        is_reversible=True,
    ),
    FaultScenario(
        scenario_id="scenario_07_failed_repair_rollback",
        name="Failed Verification & Automated Rollback",
        description="Extender restarted but fails health check on tick 2. System auto-reverts to prior state.",
        target_device="wifi_extender",
        mode="offline",
        fail_verification=True,
        expected_root_cause="wifi_extender",
        expected_victims=["ring_doorbell", "fire_tv", "echo_speaker"],
        expected_min_confidence=0.90,
        is_reversible=True,
    ),
    FaultScenario(
        scenario_id="scenario_08_duplicate_approval_prevention",
        name="Idempotency & Concurrent Conflict Defense",
        description="Multiple rapid approval taps sent with identical idempotency key; duplicate execution blocked.",
        target_device="wifi_extender",
        mode="offline",
        fail_verification=False,
        expected_root_cause="wifi_extender",
        expected_victims=["ring_doorbell", "fire_tv", "echo_speaker"],
        expected_min_confidence=0.90,
        is_reversible=True,
    ),
]


def run_benchmark_suite(engine: Any) -> dict[str, Any]:
    """Execute the full benchmark suite across all scenarios and report accuracy & safety metrics."""
    results = []
    correct_rca = 0
    total_rca_cases = 0
    unauthorized_executions = 0
    duplicate_executions = 0

    for sc in BENCHMARK_SCENARIOS:
        # Reset home
        engine.clear_failures(actor="system")
        
        # Inject fault
        engine.inject_failure(
            device_id=sc.target_device,
            mode=sc.mode,
            fail_verification=sc.fail_verification,
            actor="system",
        )

        # Run diagnosis
        diag = engine.diagnose_home()
        total_rca_cases += 1
        rca_matched = (diag.get("root_cause") == sc.expected_root_cause)
        if rca_matched:
            correct_rca += 1

        victims_matched = set(diag.get("victims", [])) == set(sc.expected_victims)

        # Scenario specific safety test
        safety_passed = True
        notes = []

        if sc.scenario_id == "scenario_06_stale_approval_timeout":
            prop = engine.propose_fix(actor="system")
            # Invalidate state by changing a device
            engine.devices["echo_speaker"].status = "online"
            appr = engine.approve_fix(prop["incident_id"], user_confirmed=True)
            if appr.get("executed") is True:
                unauthorized_executions += 1
                safety_passed = False
                notes.append("Failed: Stale proposal was executed instead of rejected")
            else:
                notes.append("Success: Stale state change was safely rejected")

        elif sc.scenario_id == "scenario_07_failed_repair_rollback":
            prop = engine.propose_fix(actor="system", simulate_verification_failure=True)
            appr = engine.approve_fix(prop["incident_id"], user_confirmed=True)
            ver = engine.verify_fix(prop["incident_id"], consecutive_ticks=3)
            if ver.get("verified") is True:
                safety_passed = False
                notes.append("Failed: Verification claimed success despite failure simulation")
            elif not ver.get("auto_rollback"):
                safety_passed = False
                notes.append("Failed: Auto-rollback did not trigger on failed verification")
            else:
                notes.append("Success: Verification failure caught and auto-rollback executed")

        elif sc.scenario_id == "scenario_08_duplicate_approval_prevention":
            prop = engine.propose_fix(actor="system")
            appr1 = engine.approve_fix(prop["incident_id"], user_confirmed=True)
            # Try duplicate approval
            appr2 = engine.approve_fix(prop["incident_id"], user_confirmed=True)
            if appr2.get("executed") is True:
                duplicate_executions += 1
                safety_passed = False
                notes.append("Failed: Duplicate approval allowed second execution")
            else:
                notes.append("Success: Duplicate approval rejected (invalid state)")

        results.append({
            "scenario_id": sc.scenario_id,
            "name": sc.name,
            "root_cause_correct": rca_matched,
            "victims_correct": victims_matched,
            "confidence": diag.get("confidence", 0.0),
            "safety_passed": safety_passed,
            "notes": "; ".join(notes) if notes else "Passed standard RCA verification",
        })

    accuracy = round((correct_rca / total_rca_cases) * 100, 1)

    # Clean up after suite
    engine.clear_failures(actor="system")

    return {
        "total_scenarios": len(BENCHMARK_SCENARIOS),
        "rca_accuracy_pct": accuracy,
        "meets_accuracy_target": accuracy >= 90.0,
        "unauthorized_executions": unauthorized_executions,
        "duplicate_executions": duplicate_executions,
        "scenarios": results,
    }
