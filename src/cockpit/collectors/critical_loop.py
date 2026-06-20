"""Immediate Critical Loop — runs every 1-5 minutes checking for urgent issues.

Triggers alerts for: services down, disk critical, mail queue surge, etc.
"""

from __future__ import annotations

import sqlite3
import time
from typing import Any

from cockpit.collectors.base import BaseCollector
from cockpit.config import settings
from cockpit.issues import IssueManager

CRITICAL_SERVICES = ["litespeed", "exim", "dovecot", "mariadb", "named"]

# Mount points to monitor for disk/inode critical alerts
CRITICAL_MOUNTS = ["/", "/home", "/var", "/tmp"]

DISK_CRITICAL_PERCENT = 90
INODE_CRITICAL_PERCENT = 85
MAIL_QUEUE_SURGE_THRESHOLD = 2000


class CriticalLoopCollector(BaseCollector):
    """Monitors for urgent conditions on every cycle."""

    name = "critical_loop"

    def __init__(self, db_path: str | None = None) -> None:
        super().__init__(db_path)
        self._issues = IssueManager(db_path)

    async def poll(self) -> dict[str, list[dict[str, Any]]]:
        """Check critical conditions and create/update issues in SQLite."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            self._check_services(conn)
            self._check_disk(conn)
            self._check_mail_queue(conn)
        finally:
            conn.close()
        return {}  # data is written via IssueManager, not direct _store

    def _check_services(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            "SELECT DISTINCT service_name, status FROM service_status "
            "WHERE collected_at = (SELECT MAX(collected_at) FROM service_status)"
        ).fetchall()
        for row in rows:
            svc = row["service_name"]
            status = row["status"]
            if status == "stopped" and svc in CRITICAL_SERVICES:
                self._issues.detect_or_update(
                    issue_id=f"{svc}_stopped",
                    severity="critical",
                    description=f"{svc} service is not running",
                    target_type="service",
                    target_id=svc,
                )
            elif status == "running":
                self._issues.resolve(f"{svc}_stopped")

    def _check_disk(self, conn: sqlite3.Connection) -> None:
        for mount in CRITICAL_MOUNTS:
            row = conn.execute(
                "SELECT * FROM disk_health WHERE mount_point = ? "
                "ORDER BY collected_at DESC LIMIT 1",
                (mount,),
            ).fetchone()
            if not row:
                continue
            pct = row["used_percent"]
            inode_pct = row["inode_used_percent"]
            mount_label = mount.replace("/", "_")

            if pct and pct >= DISK_CRITICAL_PERCENT:
                self._issues.detect_or_update(
                    issue_id=f"disk_critical{mount_label}",
                    severity="critical",
                    description=f"{mount} disk at {pct}% (threshold: {DISK_CRITICAL_PERCENT}%)",
                    target_type="mount",
                    target_id=mount,
                )
            elif pct and pct < DISK_CRITICAL_PERCENT - 5:
                self._issues.resolve(f"disk_critical{mount_label}")

            if inode_pct and inode_pct >= INODE_CRITICAL_PERCENT:
                self._issues.detect_or_update(
                    issue_id=f"inode_critical{mount_label}",
                    severity="critical",
                    description=f"{mount} inode at {inode_pct}% (threshold: {INODE_CRITICAL_PERCENT}%)",
                    target_type="mount",
                    target_id=mount,
                )
            elif inode_pct and inode_pct < INODE_CRITICAL_PERCENT - 5:
                self._issues.resolve(f"inode_critical{mount_label}")

    def _check_mail_queue(self, conn: sqlite3.Connection) -> None:
        row = conn.execute(
            "SELECT * FROM mail_queue ORDER BY collected_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            return
        qsize = row["queue_size"]
        if qsize and qsize >= MAIL_QUEUE_SURGE_THRESHOLD:
            self._issues.detect_or_update(
                issue_id="mail_queue_surge",
                severity="warning",
                description=f"Mail queue at {qsize} (threshold: {MAIL_QUEUE_SURGE_THRESHOLD})",
                target_type="service",
                target_id="exim",
            )
        elif qsize and qsize < MAIL_QUEUE_SURGE_THRESHOLD * 0.5:
            self._issues.resolve("mail_queue_surge")
