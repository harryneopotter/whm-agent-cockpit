"""Issue lifecycle — state machine for alerts and detected problems.

States:
NEW → ACKNOWLEDGED → AUTO_FIX_ELIGIBLE → PENDING_APPROVAL → FIX_RUNNING → POST_CHECK_RUNNING → RESOLVED / FAILED / ESCALATED_TO_WHM / SUPPRESSED
"""

from __future__ import annotations

import json
import logging
import time
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from cockpit.config import settings

logger = logging.getLogger(__name__)

VALID_STATES = frozenset({
    "NEW", "ACKNOWLEDGED", "AUTO_FIX_ELIGIBLE", "PENDING_APPROVAL",
    "FIX_RUNNING", "POST_CHECK_RUNNING", "RESOLVED", "FAILED",
    "ESCALATED_TO_WHM", "SUPPRESSED",
})


@dataclass
class Issue:
    """A single detected issue."""

    issue_id: str
    severity: str  # "critical" | "warning" | "info"
    state: str = "NEW"
    description: str = ""
    detected_at: str = ""
    acknowledged_at: str | None = None
    resolved_at: str | None = None
    consecutive_detections: int = 1
    target_type: str | None = None
    target_id: str | None = None

    def transition(self, new_state: str) -> None:
        if new_state not in VALID_STATES:
            raise ValueError(f"Invalid state: {new_state}")
        self.state = new_state


class IssueManager:
    """Manages issue lifecycle against SQLite."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or settings.db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.row_factory = sqlite3.Row
        return conn

    def detect_or_update(
        self,
        issue_id: str,
        severity: str,
        description: str,
        target_type: str | None = None,
        target_id: str | None = None,
    ) -> Issue:
        """Create a new issue or increment consecutive_detections on an existing NEW one."""
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        conn = self._conn()
        try:
            existing = conn.execute(
                "SELECT * FROM issues WHERE issue_id = ?", (issue_id,)
            ).fetchone()
            if existing and existing["state"] in ("NEW", "ACKNOWLEDGED", "AUTO_FIX_ELIGIBLE"):
                new_count = existing["consecutive_detections"] + 1
                conn.execute(
                    "UPDATE issues SET consecutive_detections = ?, detected_at = ? WHERE issue_id = ?",
                    (new_count, now, issue_id),
                )
                conn.commit()
                return Issue(
                    issue_id=issue_id, severity=severity, state=existing["state"],
                    description=description, detected_at=now,
                    consecutive_detections=new_count,
                    target_type=target_type, target_id=target_id,
                )
            else:
                conn.execute(
                    "INSERT OR REPLACE INTO issues "
                    "(issue_id, detected_at, severity, state, description, "
                    " consecutive_detections, target_type, target_id, ttl_seconds) "
                    "VALUES (?, ?, ?, 'NEW', ?, 1, ?, ?, 86400)",
                    (issue_id, now, severity, description, target_type, target_id),
                )
                conn.commit()
                return Issue(
                    issue_id=issue_id, severity=severity, state="NEW",
                    description=description, detected_at=now,
                    target_type=target_type, target_id=target_id,
                )
        finally:
            conn.close()

    def acknowledge(self, issue_id: str) -> None:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE issues SET state = 'ACKNOWLEDGED', acknowledged_at = ? WHERE issue_id = ?",
                (now, issue_id),
            )
            conn.commit()
        finally:
            conn.close()

    def resolve(self, issue_id: str) -> None:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE issues SET state = 'RESOLVED', resolved_at = ? WHERE issue_id = ?",
                (now, issue_id),
            )
            conn.commit()
        finally:
            conn.close()

    def get_active(self) -> list[dict[str, Any]]:
        """Return all non-resolved, non-suppressed issues."""
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM issues WHERE state NOT IN ('RESOLVED', 'SUPPRESSED') "
                "ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, "
                "detected_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
