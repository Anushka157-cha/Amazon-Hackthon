"""HomeGuard Professional MCP Server.

Exposes official MCP tools using FastMCP / Streamable-HTTP transport.
Each tool returns structured data, status codes, correlation IDs, timestamps,
and a short 'spoken' field for voice agents (Alexa+ in English & Hindi).

Tools contract:
- get_status / home_status: Device inventory, health metrics, last-seen timestamps
- diagnose / diagnose_home: Ranked root causes, evidence, confidence, affected devices
- propose_fix: Proposal ID, action, risk, estimated impact, expiry, safer alternatives
- approve_fix: Approval result, validated proposal, execution job ID, idempotency
- verify_fix: Multi-tick check results, recovery status, remaining failures
- rollback_fix: Recovery action, restored state, rollback verification
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any

# Support both MCP SDK v1 (FastMCP) and v2 (MCPServer)
try:
    from mcp.server.fastmcp import FastMCP
except (ImportError, ModuleNotFoundError):
    from mcp.server.mcpserver import MCPServer as FastMCP

from homeguard.core import (
    DEVICE_FRIENDLY_NAMES,
    VALID_ACTIONS,
    VALID_DEVICES,
    HomeGuardEngine,
)

SCHEMA_VERSION = "2.0.0"


def _meta(correlation_id: str | None = None) -> dict[str, Any]:
    return {
        "version": SCHEMA_VERSION,
        "correlation_id": correlation_id or f"corr-{uuid.uuid4().hex[:10]}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "simulated": True,
    }


def create_mcp_server(engine: HomeGuardEngine | None = None) -> tuple[FastMCP, HomeGuardEngine]:
    """Factory to create and configure the HomeGuard MCP server."""
    if engine is None:
        log_path = os.getenv("HOMEGUARD_AUDIT_LOG_PATH", "audit_log.jsonl")
        engine = HomeGuardEngine(audit_log_path=log_path)

    mcp = FastMCP(
        "HomeGuard-Pro",
        instructions=(
            "HomeGuard Pro MCP Server: Production-oriented home network reliability platform. "
            "Inspect digital twin status, run deterministic root cause diagnosis, propose policy-controlled "
            "fixes with impact calculations, execute approved repairs, verify recovery, and rollback safely."
        ),
    )

    def _get_status_impl(correlation_id: str | None = None) -> dict[str, Any]:
        cid = correlation_id or f"corr-{uuid.uuid4().hex[:10]}"
        devices = engine.get_devices()
        unhealthy = [d for d in devices.values() if d["status"] != "online"]
        online_count = len(devices) - len(unhealthy)

        if not unhealthy:
            spoken = "All 5 simulated devices in your home are online and working normally."
            spoken_hindi = "आपके घर के सभी 5 सिमुलेटेड उपकरण ऑनलाइन हैं और सामान्य रूप से काम कर रहे हैं।"
        else:
            offline_names = [
                d["name"].replace(" (Simulated)", "")
                for d in unhealthy
                if d["status"] == "offline"
            ]
            degraded_names = [
                d["name"].replace(" (Simulated)", "")
                for d in unhealthy
                if d["status"] == "degraded"
            ]

            parts = []
            if offline_names:
                parts.append(f"{', '.join(offline_names)} {'is' if len(offline_names) == 1 else 'are'} offline")
            if degraded_names:
                parts.append(f"{', '.join(degraded_names)} {'is' if len(degraded_names) == 1 else 'are'} buffering")

            spoken = f"Your simulated {' and '.join(parts)}. Your main router is online."
            spoken_hindi = f"उपकरण समस्या: {' तथा '.join(parts)}। मुख्य गेटवे ऑनलाइन है।"

        meta = _meta(cid)
        return {
            **meta,
            "success": True,
            "total_devices": len(devices),
            "online_count": online_count,
            "unhealthy_count": len(unhealthy),
            "devices": devices,
            "spoken": spoken,
            "spoken_hindi": spoken_hindi,
        }

    @mcp.tool()
    def get_status() -> dict[str, Any]:
        """Check the health status, inventory, metrics, and last-seen times of every home device."""
        return _get_status_impl()

    @mcp.tool()
    def home_status() -> dict[str, Any]:
        """Check the health status of every simulated home device in plain words (backward compatibility)."""
        return _get_status_impl()

    def _diagnose_impl(correlation_id: str | None = None) -> dict[str, Any]:
        cid = correlation_id or f"corr-{uuid.uuid4().hex[:10]}"
        diag = engine.diagnose_home()
        meta = _meta(cid)
        return {**meta, **diag}

    @mcp.tool()
    def diagnose() -> dict[str, Any]:
        """Find the ranked root cause devices and separate them from dependent victim devices."""
        return _diagnose_impl()

    @mcp.tool()
    def diagnose_home() -> dict[str, Any]:
        """Find the single root cause device and separate it from victim devices (backward compatibility)."""
        return _diagnose_impl()

    @mcp.tool()
    def propose_fix(incident_id: str | None = None) -> dict[str, Any]:
        """Propose a safe fix for the detected root cause with downtime, blast radius, and expiry."""
        cid = f"corr-{uuid.uuid4().hex[:10]}"
        proposal = engine.propose_fix(incident_id=incident_id, actor="user_voice")
        if proposal.get("state") == "NO_INCIDENT":
            return {**_meta(cid), **proposal}

        action = proposal.get("action")
        target_device = proposal.get("target_device")
        if action not in VALID_ACTIONS:
            return {
                **_meta(cid),
                "success": False,
                "error": "INVALID_ACTION",
                "message": f"Action '{action}' is not permitted. Only 'restart' is allowed.",
                "spoken": "I can only perform restart actions.",
            }
        if target_device not in VALID_DEVICES:
            return {
                **_meta(cid),
                "success": False,
                "error": "UNKNOWN_DEVICE",
                "message": f"Device '{target_device}' is unknown.",
                "spoken": "I cannot find that device in your simulated home.",
            }

        return {**_meta(cid), **proposal}

    @mcp.tool()
    def approve_fix(
        incident_id: str,
        user_confirmed: bool,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Execute a proposed fix ONLY if user_confirmed is true, proposal is unexpired, and state matches."""
        cid = f"corr-{uuid.uuid4().hex[:10]}"
        result = engine.approve_fix(
            incident_id=incident_id,
            user_confirmed=user_confirmed,
            actor="user_voice",
            idempotency_key=idempotency_key,
        )
        return {**_meta(cid), **result}

    @mcp.tool()
    def verify_fix(incident_id: str, consecutive_ticks: int = 3) -> dict[str, Any]:
        """Run stabilization checks across consecutive ticks to verify full recovery, or trigger rollback."""
        cid = f"corr-{uuid.uuid4().hex[:10]}"
        result = engine.verify_fix(
            incident_id=incident_id,
            consecutive_ticks=consecutive_ticks,
            actor="user_voice",
        )
        return {**_meta(cid), **result}

    @mcp.tool()
    def rollback_fix(incident_id: str) -> dict[str, Any]:
        """Restore the pre-fix snapshot to roll back changes safely."""
        cid = f"corr-{uuid.uuid4().hex[:10]}"
        result = engine.rollback_fix(incident_id=incident_id, actor="user_voice")
        return {**_meta(cid), **result}

    return mcp, engine


# Default shared server and engine singleton
default_mcp_server, default_engine = create_mcp_server()


if __name__ == "__main__":
    import asyncio
    print("Starting HomeGuard Pro MCP Server (Streamable-HTTP)...")
    asyncio.run(default_mcp_server.run_streamable_http_async())
