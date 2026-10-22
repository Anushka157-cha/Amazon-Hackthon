"""HomeGuard Core Engine.

Models the smart home as a live dependency graph Digital Twin,
performs deterministic root-cause analysis with explainable bilingual AI,
detects early predictive degradation, executes policy-controlled repairs with
explicit approval, verifies recovery across consecutive ticks, and supports rollback.

NOTE: ALL DEVICES ARE SIMULATED.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from homeguard.adapters import (
    AsusWrtRouterAdapter,
    BaseDeviceAdapter,
    HomeAssistantAdapter,
    NetworkDiscoveryService,
    SimulatedDeviceAdapter,
    UniFiAdapter,
)
from homeguard.database import HomeGuardDatabase
from homeguard.diagnosis import ExplainableDiagnosisEngine
from homeguard.predictive import PredictiveHealthMonitor
from homeguard.repair_policy import ProposalPlan, RepairPolicyEngine
from homeguard.voice_assistant import VoiceAssistant

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
ActorType = Literal["user_voice", "user_tv", "system", "admin"]
ImpactTier = Literal["LOW", "MEDIUM", "HIGH"]
IncidentState = Literal[
    "PROPOSED", "APPROVED", "EXECUTING", "VERIFYING", "RESOLVED", "REJECTED", "ROLLED_BACK", "FAILED"
]


@dataclass
class Device:
    id: str
    name: str
    status: StatusType = "online"
    device_type: str = "smart_device"
    simulated: bool = True
    upstream: list[str] = field(default_factory=list)
    downstream: list[str] = field(default_factory=list)
    last_seen: str | None = None
    health_metrics: dict[str, float] = field(default_factory=dict)
    ip_address: str = "192.168.1.1"
    mac_address: str = "00:1A:2B:3C:4D:00"
    adapter_type: str = "simulated"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AuditEntry:
    timestamp: str
    actor: str
    action: str
    target: str
    result: dict[str, Any] | str
    event_id: str = field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:12]}")
    correlation_id: str | None = None
    previous_hash: str | None = None
    entry_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Incident:
    incident_id: str
    target_device: str
    action: str
    impact: dict[str, Any]
    state: str = "PROPOSED"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    pre_fix_snapshot: dict[str, StatusType] | None = None
    simulate_verification_failure: bool = False
    verification_ticks_passed: int = 0
    expires_at: str | None = None
    state_fingerprint: str | None = None
    execution_id: str | None = None
    approved_at: str | None = None
    proposal_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HomeGuardEngine:
    """Core state engine, digital twin, dependency graph analyzer, and repair orchestrator."""

    def __init__(
        self,
        audit_log_path: str = "audit_log.jsonl",
        db_path: str = "homeguard.db",
    ) -> None:
        self.audit_log_path = audit_log_path
        self.db_path = db_path
        self.database = HomeGuardDatabase(db_path=self.db_path)
        self.diagnosis_engine = ExplainableDiagnosisEngine(DEVICE_FRIENDLY_NAMES)
        self.predictive_monitor = PredictiveHealthMonitor()
        self.repair_engine = RepairPolicyEngine()
        self.voice_assistant = VoiceAssistant()

        # Device Adapters
        self.adapters: dict[str, BaseDeviceAdapter] = {
            "simulated": SimulatedDeviceAdapter(),
            "asuswrt": AsusWrtRouterAdapter(),
            "homeassistant": HomeAssistantAdapter(),
            "unifi": UniFiAdapter(),
        }

        self.devices: dict[str, Device] = {}
        self.incidents: dict[str, Incident] = {}
        self.proposals: dict[str, ProposalPlan] = {}
        self.audit_log: list[AuditEntry] = []
        self.active_fail_verification: bool = False
        self.health_history: list[dict[str, Any]] = []

        self._init_topology()
        self._record_health_snapshot()

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
                ip_address="192.168.1.1",
                mac_address="00:1A:2B:3C:4D:01",
                adapter_type="simulated",
            ),
            DEVICE_WIFI_EXTENDER: Device(
                id=DEVICE_WIFI_EXTENDER,
                name=DEVICE_FRIENDLY_NAMES[DEVICE_WIFI_EXTENDER],
                status="online",
                device_type="network_repeater",
                simulated=True,
                upstream=[DEVICE_ROUTER],
                downstream=[DEVICE_RING_DOORBELL, DEVICE_FIRE_TV, DEVICE_ECHO_SPEAKER],
                ip_address="192.168.1.15",
                mac_address="00:1A:2B:3C:4D:02",
                adapter_type="simulated",
            ),
            DEVICE_RING_DOORBELL: Device(
                id=DEVICE_RING_DOORBELL,
                name=DEVICE_FRIENDLY_NAMES[DEVICE_RING_DOORBELL],
                status="online",
                device_type="security_camera",
                simulated=True,
                upstream=[DEVICE_WIFI_EXTENDER],
                downstream=[],
                ip_address="192.168.1.52",
                mac_address="00:1A:2B:3C:4D:03",
                adapter_type="simulated",
            ),
            DEVICE_FIRE_TV: Device(
                id=DEVICE_FIRE_TV,
                name=DEVICE_FRIENDLY_NAMES[DEVICE_FIRE_TV],
                status="online",
                device_type="streaming_device",
                simulated=True,
                upstream=[DEVICE_WIFI_EXTENDER],
                downstream=[],
                ip_address="192.168.1.88",
                mac_address="00:1A:2B:3C:4D:04",
                adapter_type="simulated",
            ),
            DEVICE_ECHO_SPEAKER: Device(
                id=DEVICE_ECHO_SPEAKER,
                name=DEVICE_FRIENDLY_NAMES[DEVICE_ECHO_SPEAKER],
                status="online",
                device_type="smart_speaker",
                simulated=True,
                upstream=[DEVICE_WIFI_EXTENDER],
                downstream=[],
                ip_address="192.168.1.94",
                mac_address="00:1A:2B:3C:4D:05",
                adapter_type="simulated",
            ),
        }
        now = datetime.now(timezone.utc).isoformat()
        for device in self.devices.values():
            device.last_seen = now
            device.health_metrics = self._metrics_for_status(device.status)

    @staticmethod
    def _metrics_for_status(status: StatusType) -> dict[str, float]:
        if status == "offline":
            return {"latency_ms": 0.0, "packet_loss_pct": 100.0, "reconnects_24h": 8.0, "uptime_pct": 0.0}
        if status == "degraded":
            return {"latency_ms": 180.0, "packet_loss_pct": 8.0, "reconnects_24h": 4.0, "uptime_pct": 96.0}
        return {"latency_ms": 24.0, "packet_loss_pct": 0.0, "reconnects_24h": 0.0, "uptime_pct": 99.98}

    def _record_health_snapshot(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        snapshot = {
            "timestamp": now,
            "devices": {
                device_id: {
                    "status": device.status,
                    "metrics": dict(device.health_metrics),
                }
                for device_id, device in self.devices.items()
            },
        }
        self.health_history.append(snapshot)
        self.health_history = self.health_history[-100:]

        # Persist to database
        try:
            for dev_id, dev in self.devices.items():
                self.database.record_health_metric(dev_id, dev.health_metrics)
        except Exception:
            pass

    def _set_status(self, device_id: str, status: StatusType) -> None:
        device = self.devices[device_id]
        device.status = status
        device.health_metrics = self._metrics_for_status(status)
        if status == "online":
            device.last_seen = datetime.now(timezone.utc).isoformat()

    def _log_action(
        self,
        actor: ActorType | str,
        action: str,
        target: str,
        result: dict[str, Any] | str,
        correlation_id: str | None = None,
    ) -> AuditEntry:
        """Record an action in memory, file, and relational storage with cryptographic hash chaining."""
        previous_hash = self.audit_log[-1].entry_hash if self.audit_log else None
        unsigned = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor": actor,
            "action": action,
            "target": target,
            "result": result,
            "correlation_id": correlation_id,
            "previous_hash": previous_hash,
        }
        entry_hash = hashlib.sha256(
            json.dumps(unsigned, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        event_id = f"evt-{uuid.uuid4().hex[:12]}"
        entry = AuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor=actor,
            action=action,
            target=target,
            result=result,
            event_id=event_id,
            correlation_id=correlation_id,
            previous_hash=previous_hash,
            entry_hash=entry_hash,
        )
        self.audit_log.append(entry)

        # Append to JSONL file
        try:
            with open(self.audit_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict()) + "\n")
        except OSError:
            pass

        # Persist to relational DB
        try:
            self.database.record_audit_event(
                event_id=event_id,
                actor=actor,
                action=action,
                target=target,
                result=result,
                correlation_id=correlation_id,
                previous_hash=previous_hash,
                entry_hash=entry_hash,
            )
        except Exception:
            pass

        return entry

    def get_devices(self) -> dict[str, dict[str, Any]]:
        """Return all simulated devices and their status."""
        return {dev_id: dev.to_dict() for dev_id, dev in self.devices.items()}

    def get_health_history(self, limit: int = 24) -> list[dict[str, Any]]:
        """Return recent health snapshots for trend charts and incident reports."""
        return self.health_history[-max(1, min(limit, 100)):]

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
        actor: ActorType | str = "system",
    ) -> dict[str, Any]:
        """Inject a simulated failure into a device and cascade downstream."""
        if device_id not in VALID_DEVICES:
            raise ValueError(
                f"Unknown simulated device: '{device_id}'. Allowed devices: {sorted(list(VALID_DEVICES))}"
            )

        if mode == "online":
            return self.clear_failures(actor=actor)

        self.active_fail_verification = fail_verification
        self._set_status(
            device_id,
            mode if mode in {"offline", "degraded"} else "offline",
        )

        victims_affected: list[str] = []
        if device_id == DEVICE_WIFI_EXTENDER:
            self._set_status(DEVICE_RING_DOORBELL, "offline")
            self._set_status(DEVICE_FIRE_TV, "degraded")
            self._set_status(DEVICE_ECHO_SPEAKER, "offline")
            victims_affected = [DEVICE_RING_DOORBELL, DEVICE_FIRE_TV, DEVICE_ECHO_SPEAKER]
        elif device_id == DEVICE_ROUTER:
            for d in [DEVICE_WIFI_EXTENDER, DEVICE_RING_DOORBELL, DEVICE_FIRE_TV, DEVICE_ECHO_SPEAKER]:
                self._set_status(d, "offline")
                victims_affected.append(d)
        else:
            victims_affected = []

        result = {
            "status": "failure_injected",
            "simulated": True,
            "target_device": device_id,
            "mode": self.devices[device_id].status,
            "cascade_victims": victims_affected,
            "fail_verification": fail_verification,
        }

        self._record_health_snapshot()
        self._log_action(actor=actor, action="inject_failure", target=device_id, result=result)
        return result

    def clear_failures(self, actor: ActorType | str = "system") -> dict[str, Any]:
        """Restore all simulated devices to healthy online status."""
        self.active_fail_verification = False
        for dev in self.devices.values():
            self._set_status(dev.id, "online")
        for inc in self.incidents.values():
            if inc.state in {"PROPOSED", "EXECUTING", "FAILED"}:
                inc.state = "REJECTED"
        result = {"status": "all_online", "simulated": True}
        self._record_health_snapshot()
        self._log_action(actor=actor, action="clear_failures", target="home", result=result)
        return result

    def diagnose_home(self) -> dict[str, Any]:
        """Perform explainable bilingual root-cause analysis (RCA)."""
        res = self.diagnosis_engine.analyze(
            devices={k: v.to_dict() for k, v in self.devices.items()},
            get_downstream_fn=self.get_downstream_descendants,
        )
        return res.to_dict()

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

    def _state_fingerprint(self) -> str:
        return self.repair_engine.generate_state_fingerprint(
            {k: v.to_dict() for k, v in self.devices.items()}
        )

    def propose_fix(
        self,
        incident_id: str | None = None,
        simulate_verification_failure: bool = False,
        actor: ActorType | str = "system",
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
                "spoken_hindi": "सब कुछ सामान्य रूप से काम कर रहा है। किसी मरम्मत की आवश्यकता नहीं है।",
            }

        target_device = diag["root_cause"]
        action = "restart"
        impact = self.estimate_fix_impact(target_device, action)

        if not incident_id:
            incident_id = f"inc-{uuid.uuid4().hex[:6]}"

        effective_sim_failure = simulate_verification_failure or self.active_fail_verification
        state_fingerprint = self._state_fingerprint()

        plan = self.repair_engine.create_proposal(
            incident_id=incident_id,
            target_device=target_device,
            friendly_target=DEVICE_FRIENDLY_NAMES.get(target_device, target_device),
            action=action,
            affected_devices=impact["affected_devices"],
            affected_names=impact["affected_device_names"],
            state_fingerprint=state_fingerprint,
        )
        self.proposals[plan.proposal_id] = plan

        incident = Incident(
            incident_id=incident_id,
            target_device=target_device,
            action=action,
            impact=impact,
            state="PROPOSED",
            simulate_verification_failure=effective_sim_failure,
            expires_at=plan.expires_at,
            state_fingerprint=state_fingerprint,
            proposal_id=plan.proposal_id,
        )
        self.incidents[incident_id] = incident

        result = {
            "simulated": True,
            "incident_id": incident_id,
            "proposal_id": plan.proposal_id,
            "target_device": target_device,
            "action": action,
            "state": "PROPOSED",
            "impact": impact,
            "confirmation_required": True,
            "safer_alternatives": plan.safer_alternatives,
            "expires_at": plan.expires_at,
            "spoken": plan.spoken,
            "spoken_hindi": plan.spoken_hindi,
        }

        self._log_action(actor=actor, action="propose_fix", target=incident_id, result=result)
        return result

    def approve_fix(
        self,
        incident_id: str,
        user_confirmed: bool,
        actor: ActorType | str = "user_voice",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Execute fix only if confirmed, proposal active, unexpired, and state unmodified."""
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

        if incident.expires_at and datetime.now(timezone.utc) >= datetime.fromisoformat(incident.expires_at):
            incident.state = "REJECTED"
            result = {
                "simulated": True,
                "incident_id": incident_id,
                "executed": False,
                "error": "PROPOSAL_EXPIRED",
                "message": "Cannot approve fix: the proposal has expired. Request a fresh diagnosis.",
                "spoken": "That repair proposal has expired, so I did not make any changes.",
            }
            self._log_action(actor=actor, action="approve_fix_refused", target=incident_id, result=result)
            return result

        if incident.state_fingerprint and incident.state_fingerprint != self._state_fingerprint():
            incident.state = "REJECTED"
            result = {
                "simulated": True,
                "incident_id": incident_id,
                "executed": False,
                "error": "STALE_PROPOSAL",
                "message": "Cannot approve fix: device state changed after diagnosis.",
                "spoken": "The home changed while I was waiting. I did not run the old repair; please ask me to check again.",
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

        # Concurrency Lock protection
        if not self.repair_engine.acquire_repair_lock():
            result = {
                "simulated": True,
                "incident_id": incident_id,
                "executed": False,
                "error": "CONCURRENT_REPAIR_IN_PROGRESS",
                "message": "Another repair execution is currently in progress. Please wait.",
                "spoken": "Another repair action is running right now. Please wait a moment.",
            }
            self._log_action(actor=actor, action="approve_fix_refused", target=incident_id, result=result)
            return result

        try:
            # Save snapshot of pre-fix state
            incident.pre_fix_snapshot = {k: v.status for k, v in self.devices.items()}
            incident.state = "EXECUTED"
            incident.execution_id = f"job-{uuid.uuid4().hex[:12]}"
            incident.approved_at = datetime.now(timezone.utc).isoformat()

            for d in self.devices.values():
                self._set_status(d.id, "online")
            self._record_health_snapshot()

            result = {
                "simulated": True,
                "incident_id": incident_id,
                "executed": True,
                "target_device": incident.target_device,
                "action": incident.action,
                "execution_id": incident.execution_id,
                "message": f"Simulated {incident.action} executed on {incident.target_device}. Ready for verification.",
                "spoken": f"I've restarted your {DEVICE_FRIENDLY_NAMES[incident.target_device].replace(' (Simulated)', '')}. Checking if everything stabilizes.",
            }
            self._log_action(actor=actor, action="execute_fix", target=incident_id, result=result)
            return result
        finally:
            self.repair_engine.release_repair_lock()

    def verify_fix(
        self,
        incident_id: str,
        consecutive_ticks: int = 3,
        actor: ActorType | str = "system",
    ) -> dict[str, Any]:
        """Verify stabilization across consecutive ticks with automated rollback on failure."""
        if incident_id not in self.incidents:
            return {
                "simulated": True,
                "incident_id": incident_id,
                "verified": False,
                "error": "INCIDENT_NOT_FOUND",
                "spoken": "I could not find that incident to verify.",
            }

        incident = self.incidents[incident_id]

        if incident.simulate_verification_failure:
            incident.verification_ticks_passed = 1
            self._set_status(incident.target_device, "offline")
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
                "manual_next_step": f"Please physically power cycle the {incident.target_device} power adapter.",
            }
            self._log_action(actor=actor, action="verify_fix_failed_auto_rollback", target=incident_id, result=result)
            return result

        passed_ticks = 0
        for _ in range(consecutive_ticks):
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
        actor: ActorType | str = "system",
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

        for dev_id, status in incident.pre_fix_snapshot.items():
            if dev_id in self.devices:
                self._set_status(dev_id, status)

        self._record_health_snapshot()
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

    def get_incident_report(self, incident_id: str) -> dict[str, Any]:
        """Return a complete, export-friendly lifecycle record for an incident."""
        incident = self.incidents.get(incident_id)
        if incident is None:
            raise ValueError(f"Incident '{incident_id}' not found")
        events = [
            event for event in self.get_audit_log(limit=len(self.audit_log))
            if event["target"] == incident_id
        ]
        return {
            "report_version": "2.0-pro",
            "simulated": True,
            "incident": incident.to_dict(),
            "events": events,
            "before_state": incident.pre_fix_snapshot,
            "after_state": {device_id: device.status for device_id, device in self.devices.items()},
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
