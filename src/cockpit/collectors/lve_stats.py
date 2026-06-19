"""LVE/CloudLinux Stats Collector — resource offenders from /proc/lve and lveinfo."""

from __future__ import annotations

import subprocess
import re
from typing import Any

from cockpit.collectors.base import BaseCollector


class LVEStatsCollector(BaseCollector):
    """Collect CloudLinux LVE resource faults per account."""

    name = "lve_stats"

    async def poll(self) -> dict[str, list[dict[str, Any]]]:
        now = self.now_iso()
        rows = self._parse_lve_info(now)
        return {"lve_stats": rows}

    @staticmethod
    def _parse_lve_info(now: str) -> list[dict[str, Any]]:
        """Parse lveinfo output for recent faults."""
        rows: list[dict[str, Any]] = []
        try:
            result = subprocess.run(
                ["lveinfo", "--no-header", "--period", "last24hours"],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode != 0:
                return rows

            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) < 6:
                    continue
                # lveinfo format: EP ID USER  CPU  IO  MEM  EP  NPROC
                # Columns vary by version — try common patterns
                username = parts[2] if len(parts) > 2 else ""
                if not username or username in ("root", "nobody"):
                    continue
                rows.append({
                    "collected_at": now,
                    "username": username,
                    "cpu_faults": _safe_int(parts[3]) if len(parts) > 3 else None,
                    "io_faults": _safe_int(parts[4]) if len(parts) > 4 else None,
                    "entry_process_faults": None,
                    "memory_faults": _safe_int(parts[5]) if len(parts) > 5 else None,
                    "nproc_faults": _safe_int(parts[6]) if len(parts) > 6 else None,
                    "ttl_seconds": 300,
                })
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return rows


def _safe_int(val: str) -> int | None:
    try:
        return int(val)
    except (ValueError, TypeError):
        return None
