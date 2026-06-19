"""Service status collector — checks systemd services."""

from __future__ import annotations

import subprocess
from typing import Any

from cockpit.collectors.base import BaseCollector, CollectorError

SERVICES = [
    "litespeed",
    "exim",
    "dovecot",
    "mariadb",
    "named",
]


class ServiceStatusCollector(BaseCollector):
    """Check each service via systemctl is-active."""

    name = "service_status"

    async def poll(self) -> dict[str, list[dict[str, Any]]]:
        now = self.now_iso()
        rows: list[dict[str, Any]] = []

        for svc in SERVICES:
            status = self._check_service(svc)
            rows.append({
                "collected_at": now,
                "service_name": svc,
                "status": status,
                "ttl_seconds": 120,
            })

        return {"service_status": rows}

    @staticmethod
    def _check_service(name: str) -> str:
        try:
            result = subprocess.run(
                ["systemctl", "is-active", name],
                capture_output=True, text=True, timeout=10,
            )
            out = result.stdout.strip()
            if out == "active":
                return "running"
            if out in ("inactive", "dead"):
                return "stopped"
            return "unknown"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return "unknown"
