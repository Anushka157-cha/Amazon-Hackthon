"""HomeGuard MCP Server.

Exposes official MCP tools using FastMCP / Streamable-HTTP transport.
Each tool returns structured data and a short 'spoken' field for voice agents (Alexa+).

HARD RULES:
- ALL devices are SIMULATED.
- A fix must NEVER run without explicit user confirmation after impact is stated.
- Actions allowlist: only 'restart'.
"""

from __future__ import annotations

import os
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


def create_mcp_server(engine: HomeGuardEngine | None = None) -> tuple[FastMCP, HomeGuardEngine]:
    """Factory to create and configure the HomeGuard MCP server."""
    if engine is None:
        log_path = os.getenv("HOMEGUARD_AUDIT_LOG_PATH", "audit_log.jsonl")
        engine = HomeGuardEngine(audit_log_path=log_path)

    mcp = FastMCP(
        "HomeGuard",
        instructions="HomeGuard MCP Server: Diagnose smart home root causes, explain impact in plain language, and safely execute confirmed fixes with verification and rollback.",
    )

    @mcp.tool()
    def home_status() -> dict[str, Any]:
        """Check the health status of every simulated home device in plain words."""
        devices = engine.get_devices()
        unhealthy = [d for d in devices.values() if d["status"] != "online"]
        online_count = len(devices) - len(unhealthy)

        if not unhealthy:
            spoken = "All 5 simulated devices in your home are online and working normally."
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

        return {
            "simulated": True,
            "total_devices": len(devices),
            "online_count": online_count,
            "unhealthy_count": len(unhealthy),
            "devices": devices,
            "spoken": spoken,
        }

    @mcp.tool()
    def diagnose_home() -> dict[str, Any]:
        """Find the single root cause device and separate it from victim devices."""
        diag = engine.diagnose_home()
        return diag

    @mcp.tool()
    def propose_fix(incident_id: str | None = None) -> dict[str, Any]:
        """Propose a fix for the detected root cause and state its impact, ending with a confirmation request."""
        # Validate that proposal is only for the supported action 'restart'
        proposal = engine.propose_fix(incident_id=incident_id, actor="user_voice")
        if proposal.get("state") == "NO_INCIDENT":
            return proposal

        action = proposal.get("action")
        target_device = proposal.get("target_device")
        if action not in VALID_ACTIONS:
            return {
                "simulated": True,
                "error": "INVALID_ACTION",
                "message": f"Action '{action}' is not permitted. Only 'restart' is allowed.",
                "spoken": "I can only perform restart actions.",
            }
        if target_device not in VALID_DEVICES:
            return {
                "simulated": True,
                "error": "UNKNOWN_DEVICE",
                "message": f"Device '{target_device}' is unknown.",
                "spoken": "I cannot find that device in your simulated home.",
            }

        return proposal

    @mcp.tool()
    def approve_fix(incident_id: str, user_confirmed: bool) -> dict[str, Any]:
        """Execute a proposed fix ONLY if user_confirmed is true and propose_fix was called first."""
        result = engine.approve_fix(
            incident_id=incident_id,
            user_confirmed=user_confirmed,
            actor="user_voice",
        )
        return result

    @mcp.tool()
    def verify_fix(incident_id: str) -> dict[str, Any]:
        """Run stabilization checks across 3 consecutive ticks to verify full home recovery."""
        ticks = int(os.getenv("HOMEGUARD_STABILIZATION_TICKS", "3"))
        result = engine.verify_fix(
            incident_id=incident_id,
            consecutive_ticks=ticks,
            actor="user_voice",
        )
        return result

    @mcp.tool()
    def rollback_fix(incident_id: str) -> dict[str, Any]:
        """Restore the pre-fix snapshot to roll back changes."""
        result = engine.rollback_fix(incident_id=incident_id, actor="user_voice")
        return result

    return mcp, engine


# Default shared server and engine singleton
default_mcp_server, default_engine = create_mcp_server()


if __name__ == "__main__":
    # Can run standalone with streamable-http or stdio
    import asyncio
    print("Starting HomeGuard MCP Server (Streamable-HTTP)...")
    asyncio.run(default_mcp_server.run_streamable_http_async())
