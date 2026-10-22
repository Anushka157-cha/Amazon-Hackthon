"""HomeGuard Safe Autonomous Repair Policy Engine & State Machine.

Implements the server-side state machine:
  DIAGNOSING -> PROPOSED -> APPROVED -> EXECUTING -> VERIFYING -> RECOVERED / RECOVERY_REQUIRED -> ROLLED_BACK / FAILED
with strict concurrency locking, idempotency protection, state fingerprinting,
proposal expiry, and automated verification with rollback.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

RepairState = Literal[
    "DIAGNOSING",
    "PROPOSED",
    "CANCELLED",
    "FAILED",
    "APPROVED",
    "EXECUTING",
    "VERIFYING",
    "RECOVERED",
    "RECOVERY_REQUIRED",
    "ROLLED_BACK",
]


@dataclass
class ProposalPlan:
    proposal_id: str
    incident_id: str
    target_device: str
    action: str
    risk_tier: str  # "LOW", "MEDIUM", "HIGH"
    duration_seconds: int
    affected_devices: list[str]
    affected_device_names: list[str]
    safer_alternatives: list[str]
    state_fingerprint: str
    expires_at: str
    created_at: str
    description: str
    spoken: str
    spoken_hindi: str


@dataclass
class ExecutionRecord:
    execution_id: str
    proposal_id: str
    incident_id: str
    target_device: str
    action: str
    idempotency_key: str
    approved_by: str
    approved_at: str
    executed_at: str
    pre_fix_snapshot: dict[str, str]
    current_state: RepairState
    verification_passed_ticks: int = 0
    verification_required_ticks: int = 3
    error_detail: str | None = None
    manual_fallback_instructions: str | None = None


class RepairPolicyEngine:
    """Manages policy validation, state machine transitions, concurrency, and safety guards."""

    PROPOSAL_TTL_MINUTES = 5

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._execution_history: dict[str, ExecutionRecord] = {}
        self._seen_idempotency_keys: dict[str, str] = {}  # idempotency_key -> execution_id

    def generate_state_fingerprint(self, devices: dict[str, Any]) -> str:
        """Create a cryptographic hash of current device statuses to detect stale state."""
        state = {
            dev_id: dev.get("status", "online")
            for dev_id, dev in sorted(devices.items())
        }
        return hashlib.sha256(json.dumps(state, sort_keys=True).encode("utf-8")).hexdigest()

    def create_proposal(
        self,
        incident_id: str,
        target_device: str,
        friendly_target: str,
        action: str,
        affected_devices: list[str],
        affected_names: list[str],
        state_fingerprint: str,
    ) -> ProposalPlan:
        proposal_id = f"prop-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(minutes=self.PROPOSAL_TTL_MINUTES)).isoformat()

        if target_device == "router":
            duration_sec = 90
            risk_tier = "HIGH"
            alternatives = [
                "Soft restart 5GHz Wi-Fi radio interface only (30s downtime)",
                "Inspect ISP WAN optical cable connection",
            ]
        elif target_device == "wifi_extender":
            duration_sec = 60
            risk_tier = "MEDIUM"
            alternatives = [
                "Re-sync mesh backhaul without full reboot (15s)",
                "Power cycle downstream devices first",
            ]
        else:
            duration_sec = 30
            risk_tier = "LOW"
            alternatives = ["Clear local device cache / reconnect Wi-Fi"]

        clean_target = friendly_target.replace(" (Simulated)", "")
        desc = (
            f"Restarting {clean_target} will briefly interrupt {len(affected_devices)} devices "
            f"for approximately {duration_sec} seconds. Risk tier: {risk_tier}."
        )
        spoken = (
            f"I recommend restarting your {clean_target}. "
            f"This will briefly disconnect {len(affected_devices)} devices for about {duration_sec} seconds. "
            "Should I go ahead with the restart?"
        )
        spoken_hindi = (
            f"मैं आपके {clean_target} को पुनः आरंभ (Restart) करने की सलाह देता हूँ। "
            f"इससे लगभग {duration_sec} सेकंड के लिए {len(affected_devices)} उपकरण डिस्कनेक्ट होंगे। "
            "क्या मैं इसे रीस्टार्ट करूँ?"
        )

        return ProposalPlan(
            proposal_id=proposal_id,
            incident_id=incident_id,
            target_device=target_device,
            action=action,
            risk_tier=risk_tier,
            duration_seconds=duration_sec,
            affected_devices=affected_devices,
            affected_device_names=affected_names,
            safer_alternatives=alternatives,
            state_fingerprint=state_fingerprint,
            expires_at=expires_at,
            created_at=now.isoformat(),
            description=desc,
            spoken=spoken,
            spoken_hindi=spoken_hindi,
        )

    def validate_preconditions(
        self,
        proposal: ProposalPlan,
        current_state_fingerprint: str,
        user_confirmed: bool,
        idempotency_key: str | None = None,
    ) -> tuple[bool, str | None, str]:
        """Validate safety preconditions before execution.
        
        Returns: (is_valid, error_code, explanation_message)
        """
        now = datetime.now(timezone.utc)

        # 1. User explicit confirmation check
        if not user_confirmed:
            return (
                False,
                "USER_NOT_CONFIRMED",
                "Action cancelled: user explicitly declined or did not provide authorization.",
            )

        # 2. Proposal expiry check
        exp_time = datetime.fromisoformat(proposal.expires_at)
        if now >= exp_time:
            return (
                False,
                "PROPOSAL_EXPIRED",
                f"Proposal expired at {proposal.expires_at}. Request a fresh diagnosis.",
            )

        # 3. State staleness check
        if proposal.state_fingerprint != current_state_fingerprint:
            return (
                False,
                "STALE_PROPOSAL",
                "Network conditions changed after proposal was generated. A fresh check is required.",
            )

        # 4. Idempotency check
        if idempotency_key and idempotency_key in self._seen_idempotency_keys:
            existing_exec = self._seen_idempotency_keys[idempotency_key]
            return (
                False,
                "DUPLICATE_EXECUTION",
                f"Repair with idempotency key '{idempotency_key}' was already processed (execution ID: {existing_exec}).",
            )

        return True, None, "Preconditions satisfied."

    def acquire_repair_lock(self) -> bool:
        """Acquire single-flight repair concurrency lock."""
        return self._lock.acquire(blocking=False)

    def release_repair_lock(self) -> None:
        """Release the repair concurrency lock safely."""
        try:
            self._lock.release()
        except RuntimeError:
            pass  # Already unlocked

    def record_execution(
        self,
        execution_id: str,
        proposal: ProposalPlan,
        actor: str,
        pre_fix_snapshot: dict[str, str],
        idempotency_key: str | None = None,
    ) -> ExecutionRecord:
        now = datetime.now(timezone.utc).isoformat()
        key = idempotency_key or f"idem-{uuid.uuid4().hex[:12]}"
        rec = ExecutionRecord(
            execution_id=execution_id,
            proposal_id=proposal.proposal_id,
            incident_id=proposal.incident_id,
            target_device=proposal.target_device,
            action=proposal.action,
            idempotency_key=key,
            approved_by=actor,
            approved_at=now,
            executed_at=now,
            pre_fix_snapshot=pre_fix_snapshot,
            current_state="EXECUTING",
            manual_fallback_instructions=(
                f"If automatic recovery fails, please physically power cycle your "
                f"{proposal.target_device} by unplugging the power cable for 10 seconds."
            ),
        )
        self._execution_history[execution_id] = rec
        self._seen_idempotency_keys[key] = execution_id
        return rec
