"""HomeGuard Core Engine.

Models the smart home as a dependency graph, performs root-cause analysis,
evaluates fix impact, executes safe fixes with explicit confirmation,
verifies stabilization across consecutive ticks, and supports rollback.

NOTE: ALL DEVICES ARE SIMULATED.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

# Supported devices and valid actions
DEVICE_ROUTER = "router"
DEVICE_WIFI_EXTENDER = "wifi_extender"
DEVICE_RING_DOORBELL = "ring_doorbell"
DEVICE_FIRE_TV = "fire_tv"
DEVICE_ECHO_SPEAKER = "echo_speaker"

VALID_DEVICES = {
    DEVICE_ROUTER,
    DEVICE_WIFI_EXTENDER,
    DEVICE_RING_DOORBELL,
    DEVICE_FIRE_TV,
    DEVICE_ECHO_SPEAKER,
}

VALID_ACTIONS = {"restart"}

DEVICE_FRIENDLY_NAMES = {
    DEVICE_ROUTER: "Main Router (Simulated)",
    DEVICE_WIFI_EXTENDER: "Wi-Fi Extender (Simulated)",
    DEVICE_RING_DOORBELL: "Ring Video Doorbell (Simulated)",
    DEVICE_FIRE_TV: "Fire TV 4K (Simulated)",
    DEVICE_ECHO_SPEAKER: "Echo Speaker (Simulated)",
}

StatusType = Literal["online", "degraded", "offline"]
ActorType = Literal["user_voice", "system"]
ImpactTier = Literal["LOW", "MEDIUM", "HIGH"]
IncidentState = Literal["PROPOSED", "EXECUTED", "RESOLVED", "REJECTED", "ROLLED_BACK"]


@dataclass
class Device:
    id: str
    name: str
    status: StatusType = "online"
    device_type: str = "smart_device"
    simulated: bool = True
    upstream: list[str] = field(default_factory=list)
    downstream: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AuditEntry:
    timestamp: str
    actor: ActorType
    action: str
    target: str
    result: dict[str, Any] | str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Incident:
    incident_id: str
    target_device: str
    action: str
    impact: dict[str, Any]
    state: IncidentState = "PROPOSED"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    pre_fix_snapshot: dict[str, StatusType] | None = None
    simulate_verification_failure: bool = False
    verification_ticks_passed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HomeGuardEngine:
    """Core state engine and dependency graph analyzer for HomeGuard."""

    def __init__(self, audit_log_path: str = "audit_log.jsonl") -> None:
        self.audit_log_path = audit_log_path
        self.devices: dict[str, Device] = {}
        self.incidents: dict[str, Incident] = {}
        self.audit_log: list[AuditEntry] = []
        self._init_topology()

    def _init_topology(self) -> None:
        """Initialize the simulated home device dependency graph."""
        self.devices = {
            DEVICE_ROUTER: Device(
                id=DEVICE_ROUTER,
                name=DEVICE_FRIENDLY_NAMES[DEVICE_ROUTER],
                status="online",
                device_type="network_gateway",
                simulated=True,
                upstream=[],
                downstream=[DEVICE_WIFI_EXTENDER],
            ),
            DEVICE_WIFI_EXTENDER: Device(
                id=DEVICE_WIFI_EXTENDER,
                name=DEVICE_FRIENDLY_NAMES[DEVICE_WIFI_EXTENDER],
                status="online",
                device_type="network_repeater",
                simulated=True,
                upstream=[DEVICE_ROUTER],
                downstream=[DEVICE_RING_DOORBELL, DEVICE_FIRE_TV, DEVICE_ECHO_SPEAKER],
            ),
            DEVICE_RING_DOORBELL: Device(
                id=DEVICE_RING_DOORBELL,
                name=DEVICE_FRIENDLY_NAMES[DEVICE_RING_DOORBELL],
                status="online",
                device_type="security_camera",
                simulated=True,
                upstream=[DEVICE_WIFI_EXTENDER],
                downstream=[],
            ),
            DEVICE_FIRE_TV: Device(
                id=DEVICE_FIRE_TV,
                name=DEVICE_FRIENDLY_NAMES[DEVICE_FIRE_TV],
                status="online",
                device_type="streaming_device",
                simulated=True,
                upstream=[DEVICE_WIFI_EXTENDER],
                downstream=[],
            ),
            DEVICE_ECHO_SPEAKER: Device(
                id=DEVICE_ECHO_SPEAKER,
                name=DEVICE_FRIENDLY_NAMES[DEVICE_ECHO_SPEAKER],
                status="online",
                device_type="smart_speaker",
                simulated=True,
                upstream=[DEVICE_WIFI_EXTENDER],
                downstream=[],
            ),
        }

    def _log_action(
        self,
        actor: ActorType,
        action: str,
        target: str,
        result: dict[str, Any] | str,
    ) -> AuditEntry:
        """Record an action in memory and append to the JSON-lines audit file."""
        entry = AuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor=actor,
            action=action,
            target=target,
            result=result,
        )
        self.audit_log.append(entry)
        try:
            with open(self.audit_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict()) + "\n")
        except OSError:
            # Continue even if local disk write encounters transient issue
            pass
        return entry

    def get_devices(self) -> dict[str, dict[str, Any]]:
        """Return all simulated devices and their status."""
        return {dev_id: dev.to_dict() for dev_id, dev in self.devices.items()}

    def get_downstream_descendants(self, device_id: str) -> list[str]:
        """Find all transitive downstream devices depending on device_id."""
        descendants: list[str] = []
        queue = list(self.devices[device_id].downstream)
        while queue:
            curr = queue.pop(0)
            if curr not in descendants:
                descendants.append(curr)
                queue.extend(self.devices[curr].downstream)
        return descendants

    def inject_failure(
        self,
        device_id: str,
        mode: StatusType | str = "offline",
        fail_verification: bool = False,
        actor: ActorType = "system",
    ) -> dict[str, Any]:
        """Inject a simulated failure into a device and cascade to victims."""
        if device_id not in VALID_DEVICES:
            raise ValueError(
                f"Unknown simulated device: '{device_id}'. Allowed devices: {sorted(list(VALID_DEVICES))}"
            )

        if mode == "online":
            return self.clear_failures(actor=actor)

        # Set root failure
        self.devices[device_id].status = mode if mode in {"offline", "degraded"} else "offline"

        # Cascade failure downstream
        victims_affected: list[str] = []
        if device_id == DEVICE_WIFI_EXTENDER:
            # Realistic cascade as described in product idea:
            # Ring doorbell goes offline, Fire TV buffers (degraded), Echo says 'something went wrong' (offline)
            self.devices[DEVICE_RING_DOORBELL].status = "offline"
            self.devices[DEVICE_FIRE_TV].status = "degraded"
            self.devices[DEVICE_ECHO_SPEAKER].status = "offline"
            victims_affected = [DEVICE_RING_DOORBELL, DEVICE_FIRE_TV, DEVICE_ECHO_SPEAKER]
        elif device_id == DEVICE_ROUTER:
            # Router drops everything
            for d in [DEVICE_WIFI_EXTENDER, DEVICE_RING_DOORBELL, DEVICE_FIRE_TV, DEVICE_ECHO_SPEAKER]:
                self.devices[d].status = "offline"
                victims_affected.append(d)
        else:
            # Leaf device failure only affects itself
            victims_affected = []

        result = {
            "status": "failure_injected",
            "simulated": True,
            "target_device": device_id,
            "mode": self.devices[device_id].status,
            "cascade_victims": victims_affected,
            "fail_verification": fail_verification,
        }

        self._log_action(actor=actor, action="inject_failure", target=device_id, result=result)
        return result

    def clear_failures(self, actor: ActorType = "system") -> dict[str, Any]:
        """Restore all simulated devices to healthy online status."""
        for dev in self.devices.values():
            dev.status = "online"
        result = {"status": "all_online", "simulated": True}
        self._log_action(actor=actor, action="clear_failures", target="home", result=result)
        return result

    def diagnose_home(self) -> dict[str, Any]:
        """Perform root-cause analysis (RCA) on the device dependency graph.

        Rule:
        - An unhealthy device is a ROOT_CAUSE if all its upstream dependencies are healthy.
        - Unhealthy devices below a failed ancestor are VICTIMS.
        """
        unhealthy = {k: v for k, v in self.devices.items() if v.status != "online"}

        if not unhealthy:
            return {
                "simulated": True,
                "has_incident": False,
                "root_cause": None,
                "root_cause_name": None,
                "root_cause_status": "online",
                "victims": [],
                "victim_names": [],
                "confidence": 1.0,
                "explanation": "All 5 simulated devices are online and functioning normally.",
                "spoken": "Your home is running smoothly. All simulated devices are connected and online.",
            }

        # Find devices whose upstream dependencies are all healthy
        root_cause_candidates: list[str] = []
        for dev_id in unhealthy:
            upstream = self.devices[dev_id].upstream
            # Healthy if no upstream, or all upstream are online
            upstream_healthy = all(
                self.devices[u].status == "online" for u in upstream
            )
            if upstream_healthy:
                root_cause_candidates.append(dev_id)

        # Single root cause
        if len(root_cause_candidates) == 1:
            root_cause_id = root_cause_candidates[0]
            root_cause_dev = self.devices[root_cause_id]
            descendants = set(self.get_downstream_descendants(root_cause_id))
            victims = [d for d in unhealthy if d in descendants and d != root_cause_id]
            
            # Confidence calculation based on dependency graph topology
            # If 100% of upstream is healthy and downstream explains all unhealthy nodes
            coverage = (1 + len(victims)) / len(unhealthy)
            confidence = round(min(0.98, 0.90 + 0.08 * coverage), 2)

            root_name = DEVICE_FRIENDLY_NAMES.get(root_cause_id, root_cause_id)
            victim_names = [DEVICE_FRIENDLY_NAMES.get(v, v) for v in victims]

            explanation = (
                f"Simulated device '{root_name}' is {root_cause_dev.status}, but its upstream gateway is healthy. "
                f"{len(victims)} downstream devices ({', '.join(victim_names)}) are dependent victims."
            )
            spoken = (
                f"I found the issue. Your {root_name.replace(' (Simulated)', '')} is {root_cause_dev.status}. "
                f"It is causing {len(victims)} other devices, including your "
                f"{', '.join([n.replace(' (Simulated)', '') for n in victim_names[:2]])}, to fail."
            )

            return {
                "simulated": True,
                "has_incident": True,
                "root_cause": root_cause_id,
                "root_cause_name": root_name,
                "root_cause_status": root_cause_dev.status,
                "victims": victims,
                "victim_names": victim_names,
                "confidence": confidence,
                "explanation": explanation,
                "spoken": spoken,
            }
        else:
            # Multiple uncorrelated failures
            primary = root_cause_candidates[0] if root_cause_candidates else list(unhealthy.keys())[0]
            victims = [d for d in unhealthy if d != primary]
            return {
                "simulated": True,
                "has_incident": True,
                "root_cause": primary,
                "root_cause_name": DEVICE_FRIENDLY_NAMES.get(primary, primary),
                "root_cause_status": self.devices[primary].status,
                "victims": victims,
                "victim_names": [DEVICE_FRIENDLY_NAMES.get(v, v) for v in victims],
                "confidence": 0.75,
                "explanation": f"Multiple independent issues detected. Primary focus is {primary}.",
                "spoken": f"I see multiple devices with issues. The primary one appears to be your {DEVICE_FRIENDLY_NAMES.get(primary, primary).replace(' (Simulated)', '')}.",
            }

    def estimate_fix_impact(self, target_device: str, action: str = "restart") -> dict[str, Any]:
        """Estimate outage impact when performing a simulated fix action."""
        if target_device not in VALID_DEVICES:
            raise ValueError(f"Unknown simulated device: '{target_device}'")
        if action not in VALID_ACTIONS:
            raise ValueError(f"Unknown fix action: '{action}'. Allowed actions: {sorted(list(VALID_ACTIONS))}")

        downstream = self.get_downstream_descendants(target_device)
        affected_devices = [target_device] + downstream
        affected_names = [DEVICE_FRIENDLY_NAMES.get(d, d) for d in affected_devices]

        if target_device == DEVICE_ROUTER:
            duration_sec = 90
            tier: ImpactTier = "HIGH"
        elif target_device == DEVICE_WIFI_EXTENDER:
            duration_sec = 60
            tier = "MEDIUM"
        else:
            duration_sec = 30
            tier = "LOW"

        friendly_target = DEVICE_FRIENDLY_NAMES.get(target_device, target_device).replace(" (Simulated)", "")
        return {
            "target_device": target_device,
            "action": action,
            "tier": tier,
            "duration_seconds": duration_sec,
            "affected_devices": affected_devices,
            "affected_device_names": affected_names,
            "description": (
                f"Restarting {friendly_target} will disconnect {len(affected_devices)} simulated devices "
                f"for approximately {duration_sec} seconds. Impact tier: {tier}."
            ),
        }

    def propose_fix(
        self,
        incident_id: str | None = None,
        simulate_verification_failure: bool = False,
        actor: ActorType = "system",
    ) -> dict[str, Any]:
        """Propose a fix for the current root cause, calculate impact, and require confirmation."""
        diag = self.diagnose_home()
        if not diag["has_incident"] or not diag["root_cause"]:
            return {
                "simulated": True,
                "incident_id": None,
                "state": "NO_INCIDENT",
                "message": "No issues detected. No fix needed.",
                "spoken": "Your home is all good. No repairs are needed.",
            }

        target_device = diag["root_cause"]
        action = "restart"
        impact = self.estimate_fix_impact(target_device, action)

        if not incident_id:
            incident_id = f"inc-{uuid.uuid4().hex[:6]}"

        incident = Incident(
            incident_id=incident_id,
            target_device=target_device,
            action=action,
            impact=impact,
            state="PROPOSED",
            simulate_verification_failure=simulate_verification_failure,
        )
        self.incidents[incident_id] = incident

        spoken = (
            f"I recommend restarting your {impact['affected_device_names'][0].replace(' (Simulated)', '')}. "
            f"This will briefly disconnect {len(impact['affected_devices'])} devices for about {impact['duration_seconds']} seconds. "
            "Should I go ahead with the restart?"
        )

        result = {
            "simulated": True,
            "incident_id": incident_id,
            "target_device": target_device,
            "action": action,
            "state": "PROPOSED",
            "impact": impact,
            "confirmation_required": True,
            "spoken": spoken,
        }

        self._log_action(actor=actor, action="propose_fix", target=incident_id, result=result)
        return result

    def approve_fix(
        self,
        incident_id: str,
        user_confirmed: bool,
        actor: ActorType = "user_voice",
    ) -> dict[str, Any]:
        """Execute a fix only if user explicitly confirmed and propose_fix was called first."""
        if incident_id not in self.incidents:
            result = {
                "simulated": True,
                "incident_id": incident_id,
                "executed": False,
                "error": "INCIDENT_NOT_FOUND",
                "message": f"Cannot approve fix: incident '{incident_id}' does not exist. Call propose_fix first.",
                "spoken": "I couldn't find a proposed fix to approve. Please ask me to check your home first.",
            }
            self._log_action(actor=actor, action="approve_fix_refused", target=incident_id, result=result)
            return result

        incident = self.incidents[incident_id]

        if incident.state != "PROPOSED":
            result = {
                "simulated": True,
                "incident_id": incident_id,
                "executed": False,
                "error": "INVALID_STATE",
                "message": f"Cannot approve fix: incident '{incident_id}' is in state '{incident.state}', not 'PROPOSED'.",
                "spoken": "That fix has already been processed or cancelled.",
            }
            self._log_action(actor=actor, action="approve_fix_refused", target=incident_id, result=result)
            return result

        if not user_confirmed:
            incident.state = "REJECTED"
            result = {
                "simulated": True,
                "incident_id": incident_id,
                "executed": False,
                "reason": "USER_NOT_CONFIRMED",
                "message": "Fix cancelled: user did not provide explicit confirmation.",
                "spoken": "Alright, I've cancelled the restart. Nothing was changed.",
            }
            self._log_action(actor=actor, action="approve_fix_cancelled", target=incident_id, result=result)
            return result

        # User confirmed and propose_fix was called: execute fix!
        # Save snapshot of pre-fix state for rollback
        incident.pre_fix_snapshot = {k: v.status for k, v in self.devices.items()}
        incident.state = "EXECUTED"

        # Simulate restart execution:
        # All devices temporarily restart and come back online
        # (If simulate_verification_failure is set, verification step will simulate failure)
        for d in self.devices.values():
            d.status = "online"

        result = {
            "simulated": True,
            "incident_id": incident_id,
            "executed": True,
            "target_device": incident.target_device,
            "action": incident.action,
            "message": f"Simulated {incident.action} executed on {incident.target_device}. Ready for verification.",
            "spoken": f"I've restarted your {DEVICE_FRIENDLY_NAMES[incident.target_device].replace(' (Simulated)', '')}. Checking if everything stabilizes.",
        }
        self._log_action(actor=actor, action="execute_fix", target=incident_id, result=result)
        return result

    def verify_fix(
        self,
        incident_id: str,
        consecutive_ticks: int = 3,
        actor: ActorType = "system",
    ) -> dict[str, Any]:
        """Verify stabilization across N consecutive ticks (default N=3).

        If verification fails (e.g. In the simulated failure scenario), auto-rollback triggers.
        """
        if incident_id not in self.incidents:
            return {
                "simulated": True,
                "incident_id": incident_id,
                "verified": False,
                "error": "INCIDENT_NOT_FOUND",
                "spoken": "I could not find that incident to verify.",
            }

        incident = self.incidents[incident_id]

        # Check self-checking demo failure simulation
        if incident.simulate_verification_failure:
            # Simulate a failure on tick 2
            incident.verification_ticks_passed = 1
            # Dropped back offline
            self.devices[incident.target_device].status = "offline"
            # Auto-rollback triggers!
            rollback_result = self.rollback_fix(incident_id, actor="system", auto=True)
            spoken = (
                f"Verification failed on tick 2: {DEVICE_FRIENDLY_NAMES[incident.target_device].replace(' (Simulated)', '')} "
                "did not stabilize. I automatically rolled back your settings to the previous state."
            )
            result = {
                "simulated": True,
                "incident_id": incident_id,
                "verified": False,
                "ticks_passed": 1,
                "required_ticks": consecutive_ticks,
                "auto_rollback": True,
                "rollback_details": rollback_result,
                "spoken": spoken,
            }
            self._log_action(actor=actor, action="verify_fix_failed_auto_rollback", target=incident_id, result=result)
            return result

        # Normal verification across consecutive ticks
        passed_ticks = 0
        for _ in range(consecutive_ticks):
            # Check every device is healthy
            if all(d.status == "online" for d in self.devices.values()):
                passed_ticks += 1
            else:
                break

        incident.verification_ticks_passed = passed_ticks
        if passed_ticks == consecutive_ticks:
            incident.state = "RESOLVED"
            spoken = (
                f"All devices have stabilized across {consecutive_ticks} checks. "
                "Your Ring doorbell, Fire TV, and Echo speaker are all back online."
            )
            result = {
                "simulated": True,
                "incident_id": incident_id,
                "verified": True,
                "ticks_passed": passed_ticks,
                "required_ticks": consecutive_ticks,
                "state": "RESOLVED",
                "spoken": spoken,
            }
            self._log_action(actor=actor, action="verify_fix_success", target=incident_id, result=result)
            return result
        else:
            # Verification failed without explicit simulate flag: trigger auto rollback
            rollback_result = self.rollback_fix(incident_id, actor="system", auto=True)
            result = {
                "simulated": True,
                "incident_id": incident_id,
                "verified": False,
                "ticks_passed": passed_ticks,
                "required_ticks": consecutive_ticks,
                "auto_rollback": True,
                "rollback_details": rollback_result,
                "spoken": "Verification could not confirm all devices were healthy. I rolled back to the prior state.",
            }
            self._log_action(actor=actor, action="verify_fix_failed_auto_rollback", target=incident_id, result=result)
            return result

    def rollback_fix(
        self,
        incident_id: str,
        actor: ActorType = "system",
        auto: bool = False,
    ) -> dict[str, Any]:
        """Restore device states from pre-fix snapshot."""
        if incident_id not in self.incidents:
            return {
                "simulated": True,
                "incident_id": incident_id,
                "rolled_back": False,
                "error": "INCIDENT_NOT_FOUND",
                "spoken": "I couldn't find that incident to roll back.",
            }

        incident = self.incidents[incident_id]
        if not incident.pre_fix_snapshot:
            return {
                "simulated": True,
                "incident_id": incident_id,
                "rolled_back": False,
                "error": "NO_PRE_FIX_SNAPSHOT",
                "spoken": "There is no previous snapshot to restore for this incident.",
            }

        # Restore snapshot
        for dev_id, status in incident.pre_fix_snapshot.items():
            if dev_id in self.devices:
                self.devices[dev_id].status = status

        incident.state = "ROLLED_BACK"
        action_name = "auto_rollback_fix" if auto else "rollback_fix"
        spoken = "I have rolled back the fix and restored your devices to their previous state."
        result = {
            "simulated": True,
            "incident_id": incident_id,
            "rolled_back": True,
            "auto": auto,
            "restored_state": incident.pre_fix_snapshot,
            "spoken": spoken,
        }
        self._log_action(actor=actor, action=action_name, target=incident_id, result=result)
        return result

    def get_audit_log(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent audit log entries."""
        return [entry.to_dict() for entry in self.audit_log[-limit:]]
