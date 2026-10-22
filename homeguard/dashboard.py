"""HomeGuard Dashboard and Combined MCP Server Runner.

Runs a unified FastAPI server that:
1. Exposes the live single-page dashboard UI and REST control API.
2. Mounts the MCP server Streamable-HTTP endpoint on the same shared in-memory state.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from contextlib import asynccontextmanager

from homeguard.core import VALID_ACTIONS, VALID_DEVICES
from homeguard.mcp_server import default_engine, default_mcp_server

# Mount the MCP server Streamable-HTTP ASGI app (sub-app path='/')
try:
    mcp_asgi = default_mcp_server.streamable_http_app(streamable_http_path="/")
except Exception as e:
    mcp_asgi = None
    print(f"Warning: Could not create streamable_http_app: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager that starts the MCP server session manager loop."""
    session_mgr = getattr(default_mcp_server._lowlevel_server, "_session_manager", None)
    if session_mgr:
        async with session_mgr.run():
            yield
    else:
        yield


app = FastAPI(
    title="HomeGuard: The Smart Home That Explains Itself",
    description="Dependency graph RCA, impact estimation, and voice-controlled safe remediation for smart homes (Simulated).",
    version="0.1.0",
    lifespan=lifespan,
)

# Enable CORS for local development and client integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if mcp_asgi is not None:
    app.mount("/mcp", mcp_asgi)


@app.get("/api/mcp-info")
def get_mcp_status() -> dict[str, Any]:
    """Return status and tool list when visited by a web browser."""
    return {
        "status": "online",
        "service": "HomeGuard MCP Server",
        "transport": "Streamable-HTTP",
        "endpoint": "/mcp",
        "tools": [
            "home_status",
            "diagnose_home",
            "propose_fix",
            "approve_fix",
            "verify_fix",
            "rollback_fix",
        ],
        "message": "Streamable-HTTP endpoint active for Alexa+ and MCP clients. For TV App, visit http://localhost:8082 or Dashboard at /",
    }

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
INDEX_FILE = STATIC_DIR / "index.html"
TV_DIR = Path(__file__).resolve().parent.parent / "tv-app" / "dist"

if TV_DIR.exists():
    app.mount("/tv", StaticFiles(directory=str(TV_DIR), html=True), name="tv")


@app.get("/tv")
def serve_tv():
    """Serve the TV app index.html directly."""
    tv_index = TV_DIR / "index.html"
    if tv_index.exists():
        return FileResponse(tv_index)
    return HTMLResponse("<h1>TV App: tv-app/dist/index.html not found</h1>", status_code=404)


class InjectFailureRequest(BaseModel):
    device_id: str = "wifi_extender"
    mode: str = "offline"
    fail_verification: bool = False


class ApproveFixRequest(BaseModel):
    incident_id: str
    user_confirmed: bool = True


class VerifyFixRequest(BaseModel):
    incident_id: str


class RollbackFixRequest(BaseModel):
    incident_id: str


class ProposeFixRequest(BaseModel):
    incident_id: str | None = None
    simulate_verification_failure: bool = False


class TVApproveBody(BaseModel):
    incident_id: str | None = None
    user_confirmed: bool = True


class TVRollbackBody(BaseModel):
    incident_id: str | None = None


@app.get("/api/status")
def get_system_status() -> dict[str, Any]:
    """Return device graph, root cause diagnosis, active incidents, and audit log."""
    devices = default_engine.get_devices()
    diagnosis = default_engine.diagnose_home()
    audit_log = default_engine.get_audit_log(limit=40)
    incidents = {k: v.to_dict() for k, v in default_engine.incidents.items()}
    dependency_graph = {
        dev_id: {
            "upstream": dev.get("upstream", []),
            "downstream": dev.get("downstream", []),
        }
        for dev_id, dev in devices.items()
    }

    return {
        "simulated": True,
        "devices": devices,
        "dependency_graph": dependency_graph,
        "diagnosis": diagnosis,
        "incidents": incidents,
        "audit_log": audit_log,
    }


@app.get("/api/diagnosis")
def get_diagnosis() -> dict[str, Any]:
    """Return root cause, victims, confidence, and plain-language summary."""
    diag = default_engine.diagnose_home()
    return {
        "simulated": True,
        "has_incident": diag.get("has_incident", False),
        "root_cause": diag.get("root_cause"),
        "root_cause_name": diag.get("root_cause_name"),
        "root_cause_status": diag.get("root_cause_status"),
        "victims": diag.get("victims", []),
        "victim_names": diag.get("victim_names", []),
        "confidence": diag.get("confidence", 1.0),
        "summary": diag.get("explanation", ""),
        "explanation": diag.get("explanation", ""),
        "spoken": diag.get("spoken", ""),
    }


@app.get("/api/proposal")
def get_proposal() -> dict[str, Any]:
    """Return proposed fix + impact (devices affected, duration, tier)."""
    # Check if there is already an active proposed incident
    proposed_incidents = [
        inc for inc in default_engine.incidents.values() if inc.state == "PROPOSED"
    ]
    diag = default_engine.diagnose_home()

    if proposed_incidents:
        inc = proposed_incidents[-1]
        impact = inc.impact
        return {
            "simulated": True,
            "has_proposal": True,
            "incident_id": inc.incident_id,
            "target_device": inc.target_device,
            "action": inc.action,
            "proposed_fix": f"{inc.action} {inc.target_device}",
            "state": inc.state,
            "impact": impact,
            "devices_affected": impact.get("affected_devices", []),
            "affected_device_names": impact.get("affected_device_names", []),
            "duration": impact.get("duration_seconds", 0),
            "duration_seconds": impact.get("duration_seconds", 0),
            "tier": impact.get("tier", "LOW"),
            "confirmation_required": True,
            "description": impact.get("description", ""),
        }

    # If an incident exists but hasn't been proposed yet, propose one
    if diag.get("has_incident") and diag.get("root_cause"):
        prop = default_engine.propose_fix(actor="system")
        impact = prop.get("impact", {})
        return {
            "simulated": True,
            "has_proposal": True,
            "incident_id": prop.get("incident_id"),
            "target_device": prop.get("target_device"),
            "action": prop.get("action"),
            "proposed_fix": f"{prop.get('action')} {prop.get('target_device')}",
            "state": "PROPOSED",
            "impact": impact,
            "devices_affected": impact.get("affected_devices", []),
            "affected_device_names": impact.get("affected_device_names", []),
            "duration": impact.get("duration_seconds", 0),
            "duration_seconds": impact.get("duration_seconds", 0),
            "tier": impact.get("tier", "LOW"),
            "confirmation_required": True,
            "description": impact.get("description", ""),
            "spoken": prop.get("spoken", ""),
        }

    return {
        "simulated": True,
        "has_proposal": False,
        "incident_id": None,
        "target_device": None,
        "action": None,
        "proposed_fix": None,
        "state": "NO_INCIDENT",
        "impact": None,
        "devices_affected": [],
        "affected_device_names": [],
        "duration": 0,
        "duration_seconds": 0,
        "tier": None,
        "confirmation_required": False,
        "message": "All devices online. No fix proposed.",
    }


@app.post("/api/approve")
def approve_fix_tv(req: TVApproveBody | None = None) -> dict[str, Any]:
    """Execute the fix ONLY if a proposal exists and user_confirmed=true."""
    user_confirmed = req.user_confirmed if req is not None else True
    inc_id = req.incident_id if req is not None else None

    diag = default_engine.diagnose_home()
    # If no incident_id supplied, locate the current PROPOSED incident
    if not inc_id:
        proposed_incidents = [
            inc for inc in default_engine.incidents.values() if inc.state == "PROPOSED"
        ]
        if not proposed_incidents or not diag.get("has_incident"):
            result = {
                "simulated": True,
                "incident_id": None,
                "executed": False,
                "error": "NO_PROPOSAL",
                "message": "Cannot approve fix: no proposed fix exists. Propose first.",
                "spoken": "I couldn't find a proposed fix to approve.",
            }
            default_engine._log_action(
                actor="user_tv", action="approve_fix_refused", target="none", result=result
            )
            return result
        inc_id = proposed_incidents[-1].incident_id

    # Call core approve_fix (enforces user_confirmed and state == PROPOSED)
    res = default_engine.approve_fix(
        incident_id=inc_id,
        user_confirmed=user_confirmed,
        actor="user_tv",
    )

    # If execution succeeded, also run stabilization verification
    if res.get("executed"):
        ver = default_engine.verify_fix(
            incident_id=inc_id,
            consecutive_ticks=3,
            actor="system",
        )
        res["verification"] = ver
        res["verified"] = ver.get("verified", False)
        res["auto_rollback"] = ver.get("auto_rollback", False)
        if ver.get("auto_rollback"):
            res["message"] = (
                "Simulated fix executed but verification failed. Auto-rolled back to previous state."
            )
        else:
            res["message"] = (
                "Simulated fix executed and verified successfully across 3 ticks."
            )

    return res


@app.post("/api/rollback")
def rollback_fix_tv(req: TVRollbackBody | None = None) -> dict[str, Any]:
    """Restore pre-fix snapshot."""
    inc_id = req.incident_id if req is not None else None

    if not inc_id:
        eligible = [
            inc for inc in default_engine.incidents.values() if inc.pre_fix_snapshot is not None
        ]
        if not eligible:
            result = {
                "simulated": True,
                "incident_id": None,
                "rolled_back": False,
                "error": "NO_SNAPSHOT",
                "message": "No executed fix found to rollback.",
                "spoken": "There is no previous state to restore.",
            }
            default_engine._log_action(
                actor="user_tv", action="rollback_refused", target="none", result=result
            )
            return result
        inc_id = eligible[-1].incident_id

    return default_engine.rollback_fix(incident_id=inc_id, actor="user_tv")


@app.get("/api/audit")
def get_audit_trail() -> dict[str, Any]:
    """Return the last 20 audit entries."""
    entries = default_engine.get_audit_log(limit=20)
    return {
        "simulated": True,
        "count": len(entries),
        "entries": entries,
        "audit_log": entries,
    }


@app.post("/api/inject_failure")
def inject_failure(req: InjectFailureRequest) -> dict[str, Any]:
    """Inject a failure into a simulated device to test root cause analysis."""
    if req.device_id not in VALID_DEVICES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown device '{req.device_id}'. Allowed: {sorted(list(VALID_DEVICES))}",
        )
    return default_engine.inject_failure(
        device_id=req.device_id,
        mode=req.mode,
        fail_verification=req.fail_verification,
        actor="system",
    )


@app.post("/api/clear_failures")
def clear_failures() -> dict[str, Any]:
    """Reset all simulated devices to healthy online state."""
    return default_engine.clear_failures(actor="system")


@app.post("/api/propose_fix")
def propose_fix(req: ProposeFixRequest | None = None) -> dict[str, Any]:
    """Propose a fix for the current root cause device."""
    sim_fail = req.simulate_verification_failure if req else False
    inc_id = req.incident_id if req else None
    return default_engine.propose_fix(
        incident_id=inc_id,
        simulate_verification_failure=sim_fail,
        actor="system",
    )


@app.post("/api/approve_fix")
def approve_fix(req: ApproveFixRequest) -> dict[str, Any]:
    """Approve or reject a proposed fix."""
    return default_engine.approve_fix(
        incident_id=req.incident_id,
        user_confirmed=req.user_confirmed,
        actor="system",
    )


@app.post("/api/verify_fix")
def verify_fix(req: VerifyFixRequest) -> dict[str, Any]:
    """Trigger stabilization check."""
    return default_engine.verify_fix(
        incident_id=req.incident_id,
        consecutive_ticks=3,
        actor="system",
    )


@app.post("/api/rollback_fix")
def rollback_fix(req: RollbackFixRequest) -> dict[str, Any]:
    """Restore pre-fix snapshot."""
    return default_engine.rollback_fix(
        incident_id=req.incident_id,
        actor="system",
    )


@app.get("/")
def serve_dashboard():
    """Serve the single-page dashboard HTML."""
    if INDEX_FILE.exists():
        return FileResponse(INDEX_FILE)
    return HTMLResponse("<h1>HomeGuard Dashboard: static/index.html not found</h1>")


def run() -> None:
    """Entrypoint to run dashboard and MCP server together."""
    host = os.getenv("HOMEGUARD_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", os.getenv("HOMEGUARD_PORT", "8000")))
    print(f"===========================================================")
    print(f"  HomeGuard Unified Server (FastAPI + MCP Server) Starting")
    print(f"  Dashboard UI:   http://127.0.0.1:{port}/")
    print(f"  LAN Access:     http://{host}:{port}/")
    print(f"  MCP Endpoint:   http://127.0.0.1:{port}/mcp")
    print(f"  State:          Shared In-Memory Singleton")
    print(f"  SIMULATED:      ALL smart home devices are simulated")
    print(f"===========================================================")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run()
