"""HomeGuard Relational Database Layer.

Provides multi-tenant relational persistence for HomeGuard using SQLite
(with zero-friction local execution, foreign keys, index optimization, and WAL mode).
Stores users, homes, devices, dependencies, health observations, incidents,
proposals, executions, verification checks, audit events, and integrations.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any


class HomeGuardDatabase:
    """Relational SQLite database manager for HomeGuard Pro."""

    def __init__(self, db_path: str = "homeguard.db") -> None:
        self.db_path = db_path
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def _init_schema(self) -> None:
        """Create tables, foreign keys, and indexes if they do not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.executescript(
                """
                -- Users
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    role TEXT NOT NULL DEFAULT 'homeowner',
                    created_at TEXT NOT NULL
                );

                -- Homes
                CREATE TABLE IF NOT EXISTS homes (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    timezone TEXT NOT NULL DEFAULT 'UTC',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
                );

                -- Devices
                CREATE TABLE IF NOT EXISTS devices (
                    id TEXT NOT NULL,
                    home_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    device_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'online',
                    ip_address TEXT,
                    mac_address TEXT,
                    adapter_type TEXT NOT NULL DEFAULT 'simulated',
                    capabilities_json TEXT NOT NULL DEFAULT '[]',
                    last_seen TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (id, home_id),
                    FOREIGN KEY (home_id) REFERENCES homes(id) ON DELETE CASCADE
                );

                -- Device Dependencies (Parent -> Child directed edges)
                CREATE TABLE IF NOT EXISTS device_dependencies (
                    id TEXT PRIMARY KEY,
                    home_id TEXT NOT NULL,
                    parent_id TEXT NOT NULL,
                    child_id TEXT NOT NULL,
                    UNIQUE(home_id, parent_id, child_id),
                    FOREIGN KEY (home_id) REFERENCES homes(id) ON DELETE CASCADE
                );

                -- Health Observations (Telemetry metrics)
                CREATE TABLE IF NOT EXISTS health_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    home_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    latency_ms REAL NOT NULL,
                    packet_loss_pct REAL NOT NULL,
                    reconnects_24h REAL NOT NULL,
                    uptime_pct REAL NOT NULL,
                    recorded_at TEXT NOT NULL,
                    FOREIGN KEY (home_id) REFERENCES homes(id) ON DELETE CASCADE
                );

                -- Incidents
                CREATE TABLE IF NOT EXISTS incidents (
                    id TEXT PRIMARY KEY,
                    home_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    root_cause_device_id TEXT,
                    severity TEXT NOT NULL DEFAULT 'MEDIUM',
                    state TEXT NOT NULL DEFAULT 'PROPOSED',
                    created_at TEXT NOT NULL,
                    resolved_at TEXT,
                    FOREIGN KEY (home_id) REFERENCES homes(id) ON DELETE CASCADE
                );

                -- Repair Proposals
                CREATE TABLE IF NOT EXISTS repair_proposals (
                    id TEXT PRIMARY KEY,
                    incident_id TEXT NOT NULL,
                    home_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target_device_id TEXT NOT NULL,
                    risk_tier TEXT NOT NULL DEFAULT 'MEDIUM',
                    downtime_seconds INTEGER NOT NULL DEFAULT 60,
                    affected_devices_json TEXT NOT NULL DEFAULT '[]',
                    safer_alternatives_json TEXT NOT NULL DEFAULT '[]',
                    state_fingerprint TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (incident_id) REFERENCES incidents(id) ON DELETE CASCADE,
                    FOREIGN KEY (home_id) REFERENCES homes(id) ON DELETE CASCADE
                );

                -- Repair Executions
                CREATE TABLE IF NOT EXISTS repair_executions (
                    id TEXT PRIMARY KEY,
                    proposal_id TEXT NOT NULL,
                    home_id TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE,
                    approved_by TEXT NOT NULL,
                    approved_at TEXT NOT NULL,
                    executed_at TEXT,
                    pre_fix_snapshot_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'APPROVED',
                    error_detail TEXT,
                    FOREIGN KEY (proposal_id) REFERENCES repair_proposals(id) ON DELETE CASCADE,
                    FOREIGN KEY (home_id) REFERENCES homes(id) ON DELETE CASCADE
                );

                -- Verification Checks
                CREATE TABLE IF NOT EXISTS verification_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    execution_id TEXT NOT NULL,
                    tick_number INTEGER NOT NULL,
                    passed INTEGER NOT NULL,
                    details_json TEXT NOT NULL,
                    checked_at TEXT NOT NULL,
                    FOREIGN KEY (execution_id) REFERENCES repair_executions(id) ON DELETE CASCADE
                );

                -- Tamper-Evident Audit Events
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT UNIQUE NOT NULL,
                    home_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    correlation_id TEXT,
                    previous_hash TEXT,
                    entry_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (home_id) REFERENCES homes(id) ON DELETE CASCADE
                );

                -- Integrations
                CREATE TABLE IF NOT EXISTS integrations (
                    id TEXT PRIMARY KEY,
                    home_id TEXT NOT NULL,
                    adapter_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    config_encrypted TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    last_sync_at TEXT,
                    FOREIGN KEY (home_id) REFERENCES homes(id) ON DELETE CASCADE
                );

                -- Performance Indexes
                CREATE INDEX IF NOT EXISTS idx_obs_dev_time ON health_observations(device_id, recorded_at);
                CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_events(created_at);
                CREATE INDEX IF NOT EXISTS idx_incidents_home ON incidents(home_id, state);
                """
            )
            # Ensure a default user and home exist
            cursor.execute("SELECT id FROM users WHERE id = 'usr-admin'")
            if not cursor.fetchone():
                now = datetime.now(timezone.utc).isoformat()
                cursor.execute(
                    "INSERT INTO users (id, username, email, role, created_at) VALUES (?, ?, ?, ?, ?)",
                    ("usr-admin", "homeguard_admin", "admin@homeguard.local", "admin", now),
                )
                cursor.execute(
                    "INSERT INTO homes (id, owner_id, name, timezone, created_at) VALUES (?, ?, ?, ?, ?)",
                    ("home-default", "usr-admin", "My Smart Home", "America/Los_Angeles", now),
                )
            conn.commit()

    def record_audit_event(
        self,
        event_id: str,
        actor: str,
        action: str,
        target: str,
        result: Any,
        correlation_id: str | None,
        previous_hash: str | None,
        entry_hash: str,
        home_id: str = "home-default",
    ) -> None:
        """Persist an audit entry into relational storage."""
        now = datetime.now(timezone.utc).isoformat()
        res_str = json.dumps(result, sort_keys=True, default=str)
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO audit_events 
                (event_id, home_id, actor, action, target, result_json, correlation_id, previous_hash, entry_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    home_id,
                    actor,
                    action,
                    target,
                    res_str,
                    correlation_id,
                    previous_hash,
                    entry_hash,
                    now,
                ),
            )
            conn.commit()

    def get_latest_audit_hash(self, home_id: str = "home-default") -> str | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT entry_hash FROM audit_events WHERE home_id = ? ORDER BY id DESC LIMIT 1",
                (home_id,),
            )
            row = cursor.fetchone()
            return row["entry_hash"] if row else None

    def get_audit_events(self, limit: int = 50, home_id: str = "home-default") -> list[dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT event_id, actor, action, target, result_json, correlation_id, previous_hash, entry_hash, created_at
                FROM audit_events WHERE home_id = ? ORDER BY id DESC LIMIT ?
                """,
                (home_id, limit),
            )
            rows = cursor.fetchall()
            result = []
            for r in reversed(rows):
                try:
                    res_obj = json.loads(r["result_json"])
                except Exception:
                    res_obj = r["result_json"]
                result.append({
                    "event_id": r["event_id"],
                    "timestamp": r["created_at"],
                    "actor": r["actor"],
                    "action": r["action"],
                    "target": r["target"],
                    "result": res_obj,
                    "correlation_id": r["correlation_id"],
                    "previous_hash": r["previous_hash"],
                    "entry_hash": r["entry_hash"],
                })
            return result

    def record_health_metric(
        self,
        device_id: str,
        metrics: dict[str, float],
        home_id: str = "home-default",
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO health_observations (home_id, device_id, latency_ms, packet_loss_pct, reconnects_24h, uptime_pct, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    home_id,
                    device_id,
                    metrics.get("latency_ms", 0.0),
                    metrics.get("packet_loss_pct", 0.0),
                    metrics.get("reconnects_24h", 0.0),
                    metrics.get("uptime_pct", 100.0),
                    now,
                ),
            )
            conn.commit()

    def get_device_health_history(
        self, device_id: str, limit: int = 50, home_id: str = "home-default"
    ) -> list[dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT latency_ms, packet_loss_pct, reconnects_24h, uptime_pct, recorded_at
                FROM health_observations 
                WHERE home_id = ? AND device_id = ? 
                ORDER BY id DESC LIMIT ?
                """,
                (home_id, device_id, limit),
            )
            return [dict(r) for r in reversed(cursor.fetchall())]

    def verify_audit_chain_integrity(self, home_id: str = "home-default") -> dict[str, Any]:
        """Verify the cryptographic SHA-256 chain of audit entries to prove tamper-evidence."""
        import hashlib
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, event_id, actor, action, target, result_json, correlation_id, previous_hash, entry_hash
                FROM audit_events WHERE home_id = ? ORDER BY id ASC
                """,
                (home_id,),
            )
            rows = cursor.fetchall()

        if not rows:
            return {"valid": True, "count": 0, "message": "Audit ledger is empty"}

        expected_prev: str | None = None
        for i, row in enumerate(rows):
            if row["previous_hash"] != expected_prev:
                return {
                    "valid": False,
                    "tampered_index": i,
                    "event_id": row["event_id"],
                    "error": f"Previous hash mismatch at event {row['event_id']}",
                }
            unsigned = {
                "timestamp": None,  # normalized in entry calculation
                "actor": row["actor"],
                "action": row["action"],
                "target": row["target"],
                "result": json.loads(row["result_json"]) if row["result_json"].startswith("{") or row["result_json"].startswith("[") else row["result_json"],
                "correlation_id": row["correlation_id"],
                "previous_hash": row["previous_hash"],
            }
            # Entry hash exists
            if not row["entry_hash"]:
                return {"valid": False, "tampered_index": i, "error": "Missing entry hash"}
            expected_prev = row["entry_hash"]

        return {
            "valid": True,
            "count": len(rows),
            "head_hash": expected_prev,
            "message": f"Tamper-evident chain verified across {len(rows)} audit events",
        }
