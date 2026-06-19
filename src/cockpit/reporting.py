"""Operational report generation — 12-hour reports + critical alerts.

Generates the structured JSON report that gets sent to Codex for review (Phase 6).
"""

from __future__ import annotations

import json
import logging
import time
import sqlite3
from typing import Any

from cockpit.config import settings

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generates the Codex input report from SQLite telemetry."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or settings.db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.row_factory = sqlite3.Row
        return conn

    def generate_report(self, report_id: str | None = None) -> dict[str, Any]:
        """Generate a full operational report matching the Codex input schema (PRD §7.4)."""
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        report: dict[str, Any] = {
            "report_id": report_id or f"report-{now}",
            "generated_at": now,
        }

        conn = self._conn()
        try:
            report["server"] = self._server_health(conn)
            report["disk"] = self._disk_health(conn)
            report["services"] = self._service_status(conn)
            report["mail"] = self._mail_queue(conn)
            report["backups"] = self._backup_status(conn)
            report["ssl"] = self._ssl_expiry(conn)
            report["alerts"] = self._active_alerts(conn)
        finally:
            conn.close()

        return report

    @staticmethod
    def _server_health(conn: sqlite3.Connection) -> dict[str, Any]:
        row = conn.execute(
            "SELECT * FROM server_health ORDER BY collected_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            return {}
        return {
            "hostname": row["hostname"],
            "load_avg_1m": row["load_avg_1m"],
            "load_avg_5m": row["load_avg_5m"],
            "load_avg_15m": row["load_avg_15m"],
            "cpu_percent": row["cpu_percent"],
            "ram_used_percent": row["ram_used_percent"],
            "swap_used_percent": row["swap_used_percent"],
            "uptime_seconds": row["uptime_seconds"],
        }

    @staticmethod
    def _disk_health(conn: sqlite3.Connection) -> dict[str, Any]:
        row = conn.execute(
            "SELECT * FROM disk_health WHERE mount_point = '/' ORDER BY collected_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            return {}
        return {
            "used_percent": row["used_percent"],
            "inode_used_percent": row["inode_used_percent"],
            "free_gb": row["free_gb"],
        }

    @staticmethod
    def _service_status(conn: sqlite3.Connection) -> list[dict[str, str]]:
        rows = conn.execute(
            "SELECT DISTINCT service_name, status FROM service_status "
            "WHERE collected_at = (SELECT MAX(collected_at) FROM service_status)"
        ).fetchall()
        return [{"name": r["service_name"], "status": r["status"]} for r in rows]

    @staticmethod
    def _mail_queue(conn: sqlite3.Connection) -> dict[str, Any]:
        row = conn.execute(
            "SELECT * FROM mail_queue ORDER BY collected_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            return {}
        return {
            "queue_size": row["queue_size"],
            "frozen_count": row["frozen_count"],
            "exim_errors_last_hour": row["exim_errors_last_hour"],
        }

    @staticmethod
    def _backup_status(conn: sqlite3.Connection) -> dict[str, Any]:
        row = conn.execute(
            "SELECT * FROM jetbackup_status ORDER BY collected_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            return {}
        return {
            "destination_reachable": bool(row["destination_reachable"]),
            "last_run_at": row["last_run_at"],
            "failed_accounts": json.loads(row["failed_accounts"]) if row["failed_accounts"] else [],
            "accounts_missing_recent_backup": (
                json.loads(row["accounts_missing_recent_backup"])
                if row["accounts_missing_recent_backup"] else []
            ),
            "missing_backup_threshold_hours": 26,
        }

    @staticmethod
    def _ssl_expiry(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
        rows = conn.execute(
            "SELECT domain, days_remaining FROM ssl_certs "
            "WHERE days_remaining IS NOT NULL AND days_remaining <= 14 "
            "AND collected_at = (SELECT MAX(collected_at) FROM ssl_certs)"
        ).fetchall()
        return {
            "expiring_within_14_days": [
                {"domain": r["domain"], "days_remaining": r["days_remaining"]}
                for r in rows
            ]
        }

    @staticmethod
    def _active_alerts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
        rows = conn.execute(
            "SELECT * FROM issues WHERE state NOT IN ('RESOLVED', 'SUPPRESSED') "
            "ORDER BY detected_at DESC LIMIT 50"
        ).fetchall()
        return [{
            "issue_id": r["issue_id"],
            "severity": r["severity"],
            "state": r["state"],
            "detected_at": r["detected_at"],
            "consecutive_detections": r["consecutive_detections"],
            "description": r["description"],
        } for r in rows]
