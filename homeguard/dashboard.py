"""HomeGuard Dashboard and Unified MCP Server Runner.

Exposes:
1. Production-oriented REST API for Dashboard, Digital Twin, Voice Assistant,
   Audit Ledger, Adapters, and Scenarios.
2. Mounts the MCP server Streamable-HTTP endpoint on the same shared in-memory state.
3. Serves the responsive 5-tab Pro Dashboard UI.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from homeguard.adapters import NetworkDiscoveryService
from homeguard.core import VALID_ACTIONS, VALID_DEVICES
from homeguard.mcp_server import default_engine, default_mcp_server
from homeguard.scenarios import BENCHMARK_SCENARIOS, run_benchmark_suite

# Mount the MCP server Streamable-HTTP ASGI app
try:
    try:
        from mcp.server.transport_security import TransportSecuritySettings
        sec = TransportSecuritySettings(enable_dns_rebinding_protection=False)
        mcp_asgi = default_mcp_server.streamable_http_app(streamable_http_path="/", transport_security=sec)
    except Exception:
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
    title="HomeGuard Pro: AI-Powered Home Network Reliability Platform",
    description="Digital Twin topology, deterministic RCA, predictive health, policy-controlled repairs, audit integrity.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if mcp_asgi is not None:
    app.mount("/mcp", mcp_asgi)


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


# Request Models
class InjectFailureRequest(BaseModel):
    device_id: str = "wifi_extender"
    mode: str = "offline"
    fail_verification: bool = False


class ApproveFixRequest(BaseModel):
    incident_id: str
    user_confirmed: bool = True
    idempotency_key: str | None = None


class VerifyFixRequest(BaseModel):
    incident_id: str
    consecutive_ticks: int = 3


class RollbackFixRequest(BaseModel):
    incident_id: str


class ProposeFixRequest(BaseModel):
    incident_id: str | None = None
    simulate_verification_failure: bool = False


class VoiceChatRequest(BaseModel):
    text: str
    language: str | None = None  # "en" | "hi" | None (auto-detect)


class TVApproveBody(BaseModel):
    incident_id: str | None = None
    user_confirmed: bool = True


class TVRollbackBody(BaseModel):
    incident_id: str | None = None


# Endpoints
@app.get("/health")
def health_check() -> dict[str, Any]:
    """Liveness/readiness endpoint for deployers and load balancers."""
    return {
        "status": "ok",
        "service": "homeguard-pro",
        "version": "2.0.0",
        "simulated": True,
        "device_count": len(default_engine.devices),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/mcp-info")
def get_mcp_status() -> dict[str, Any]:
    """Return MCP tools specification and transport details."""
    return {
        "status": "online",
        "service": "HomeGuard Pro MCP Server",
        "transport": "Streamable-HTTP",
        "endpoint": "/mcp",
        "tools": [
            "get_status",
            "diagnose",
            "propose_fix",
            "approve_fix",
            "verify_fix",
            "rollback_fix",
            "home_status",
            "diagnose_home",
        ],
        "schema_version": "2.0.0",
    }


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
    predictive = default_engine.predictive_monitor.calculate_network_risk(devices)

    return {
        "simulated": True,
        "devices": devices,
        "dependency_graph": dependency_graph,
        "diagnosis": diagnosis,
        "incidents": incidents,
        "audit_log": audit_log,
        "predictive": predictive,
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
        "confidence_label": diag.get("confidence_label", "high"),
        "evidence": diag.get("evidence", []),
        "observed_facts": diag.get("observed_facts", []),
        "inferred_hypotheses": diag.get("inferred_hypotheses", []),
        "candidates": diag.get("candidates", []),
        "summary": diag.get("explanation", ""),
        "explanation": diag.get("explanation", ""),
        "explanation_hindi": diag.get("explanation_hindi", ""),
        "spoken": diag.get("spoken", ""),
        "spoken_hindi": diag.get("spoken_hindi", ""),
        "clarifying_questions": diag.get("clarifying_questions", []),
        "clarifying_questions_hindi": diag.get("clarifying_questions_hindi", []),
    }


@app.get("/api/health-history")
def get_health_history(limit: int = 24) -> dict[str, Any]:
    """Return bounded telemetry snapshots for reliability trends."""
    return {
        "simulated": True,
        "snapshots": default_engine.get_health_history(limit),
    }


@app.get("/api/reliability")
def get_reliability() -> dict[str, Any]:
    """Summarize observed health signals and predictive risks."""
    devices = default_engine.get_devices()
    return default_engine.predictive_monitor.calculate_network_risk(devices)


@app.get("/api/incidents")
def get_incidents() -> dict[str, Any]:
    """Return incident lifecycle records ordered newest first."""
    incidents = [
        incident.to_dict()
        for incident in reversed(list(default_engine.incidents.values()))
    ]
    return {"simulated": True, "count": len(incidents), "incidents": incidents}


@app.get("/api/incidents/{incident_id}/report")
def get_incident_report(incident_id: str) -> JSONResponse:
    """Return a downloadable, audit-linked incident report."""
    try:
        report = default_engine.get_incident_report(incident_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JSONResponse(
        content=report,
        headers={"Content-Disposition": f'attachment; filename="{incident_id}-report.json"'},
    )


@app.get("/api/proposal")
def get_proposal() -> dict[str, Any]:
    """Return active proposed fix + impact (affected devices, duration, tier, alternatives)."""
    diag = default_engine.diagnose_home()
    current_root = diag.get("root_cause")
    current_fingerprint = default_engine._state_fingerprint()

    # Find valid proposal matching current root cause and state
    valid_proposals = [
        inc for inc in default_engine.incidents.values()
        if inc.state == "PROPOSED"
        and inc.target_device == current_root
        and (not inc.state_fingerprint or inc.state_fingerprint == current_fingerprint)
    ]

    if valid_proposals:
        inc = valid_proposals[-1]
        impact = inc.impact
        plan = default_engine.proposals.get(inc.proposal_id or "")
        return {
            "simulated": True,
            "has_proposal": True,
            "incident_id": inc.incident_id,
            "proposal_id": inc.proposal_id,
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
            "safer_alternatives": plan.safer_alternatives if plan else [],
            "expires_at": inc.expires_at,
            "spoken": plan.spoken if plan else "",
            "spoken_hindi": plan.spoken_hindi if plan else "",
        }

    # If an incident exists but no valid proposal exists for the current root cause, propose one
    if diag.get("has_incident") and current_root:
        # Invalidate obsolete proposals
        for inc in default_engine.incidents.values():
            if inc.state == "PROPOSED" and inc.target_device != current_root:
                inc.state = "REJECTED"
        prop = default_engine.propose_fix(actor="system")
        impact = prop.get("impact", {})
        return {
            "simulated": True,
            "has_proposal": True,
            "incident_id": prop.get("incident_id"),
            "proposal_id": prop.get("proposal_id"),
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
            "safer_alternatives": prop.get("safer_alternatives", []),
            "expires_at": prop.get("expires_at"),
            "spoken": prop.get("spoken", ""),
            "spoken_hindi": prop.get("spoken_hindi", ""),
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
    current_root = diag.get("root_cause")
    current_fingerprint = default_engine._state_fingerprint()

    if not inc_id:
        valid_proposals = [
            inc for inc in default_engine.incidents.values()
            if inc.state == "PROPOSED"
            and inc.target_device == current_root
            and (not inc.state_fingerprint or inc.state_fingerprint == current_fingerprint)
        ]
        if not valid_proposals:
            if diag.get("has_incident") and current_root:
                fresh_prop = default_engine.propose_fix(actor="user_tv")
                inc_id = fresh_prop.get("incident_id")
            else:
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
        else:
            inc_id = valid_proposals[-1].incident_id

    res = default_engine.approve_fix(
        incident_id=inc_id,
        user_confirmed=user_confirmed,
        actor="user_tv",
    )

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
def get_audit_trail(limit: int = 20) -> dict[str, Any]:
    """Return audit events."""
    entries = default_engine.get_audit_log(limit=limit)
    return {
        "simulated": True,
        "count": len(entries),
        "entries": entries,
        "audit_log": entries,
    }


@app.get("/api/audit/verify-integrity")
def verify_audit_integrity() -> dict[str, Any]:
    """Cryptographically verify the SHA-256 tamper-evident hash chain."""
    return default_engine.database.verify_audit_chain_integrity()


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
        idempotency_key=req.idempotency_key,
    )


@app.post("/api/verify_fix")
def verify_fix(req: VerifyFixRequest) -> dict[str, Any]:
    """Trigger stabilization check."""
    return default_engine.verify_fix(
        incident_id=req.incident_id,
        consecutive_ticks=req.consecutive_ticks,
        actor="system",
    )


@app.post("/api/rollback_fix")
def rollback_fix(req: RollbackFixRequest) -> dict[str, Any]:
    """Restore pre-fix snapshot."""
    return default_engine.rollback_fix(
        incident_id=req.incident_id,
        actor="system",
    )


@app.post("/api/voice/intent")
def process_voice_message(req: VoiceChatRequest) -> dict[str, Any]:
    """Process natural language voice transcript in English or Hindi."""
    diag = default_engine.diagnose_home()
    lang = req.language or default_engine.voice_assistant.detect_language(req.text)
    intent, display_text, spoken_text = default_engine.voice_assistant.get_contextual_response(
        user_text=req.text,
        diagnosis_data=diag,
        language=lang,  # type: ignore
    )

    action_result = None
    if intent == "APPROVE_FIX" and diag.get("has_incident"):
        prop = default_engine.propose_fix(actor="user_voice")
        if prop.get("incident_id"):
            action_result = default_engine.approve_fix(
                incident_id=prop["incident_id"],
                user_confirmed=True,
                actor="user_voice",
            )
            if action_result.get("executed"):
                ver = default_engine.verify_fix(
                    incident_id=prop["incident_id"],
                    consecutive_ticks=3,
                    actor="system",
                )
                action_result["verification"] = ver

    elif intent == "ROLLBACK_FIX":
        eligible = [
            inc for inc in default_engine.incidents.values() if inc.pre_fix_snapshot is not None
        ]
        if eligible:
            action_result = default_engine.rollback_fix(
                incident_id=eligible[-1].incident_id,
                actor="user_voice",
            )

    return {
        "user_query": req.text,
        "detected_language": lang,
        "intent": intent,
        "response_text": display_text,
        "spoken": spoken_text,
        "action_result": action_result,
        "has_incident": diag.get("has_incident", False),
    }


@app.get("/api/scenarios/benchmark")
def run_benchmark() -> dict[str, Any]:
    """Run all 8 automated reliability test scenarios and return accuracy score."""
    return run_benchmark_suite(default_engine)


@app.get("/api/discovery/scan")
def scan_network(subnet: str = "192.168.1.0/24") -> dict[str, Any]:
    """Simulate LAN subnet discovery of physical & virtual nodes."""
    nodes = NetworkDiscoveryService.scan_subnet(subnet)
    return {
        "subnet": subnet,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "discovered_devices": nodes,
    }


@app.get("/api/adapters/status")
def get_adapters_status() -> dict[str, Any]:
    """Return connection status of device integration adapters."""
    return {
        "adapters": [
            adapter.test_connection()
            for adapter in default_engine.adapters.values()
        ]
    }


@app.get("/")
def serve_dashboard():
    """Serve the Pro dashboard HTML."""
    if INDEX_FILE.exists():
        return FileResponse(INDEX_FILE)
    return HTMLResponse("<h1>HomeGuard Pro Dashboard: static/index.html not found</h1>")


def run() -> None:
    """Entrypoint to run dashboard and MCP server together."""
    host = os.getenv("HOMEGUARD_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", os.getenv("HOMEGUARD_PORT", "8000")))
    print("===========================================================")
    print("  HomeGuard Pro Unified Platform Starting")
    print(f"  Dashboard UI:   http://127.0.0.1:{port}/")
    print(f"  LAN Access:     http://{host}:{port}/")
    print(f"  MCP Endpoint:   http://127.0.0.1:{port}/mcp")
    print("  State:          Digital Twin Engine & Relational DB")
    print("  SIMULATED:      ALL smart home devices are simulated")
    print("===========================================================")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run()
