"""Server health collector — CPU, RAM, swap, disk, uptime."""

from __future__ import annotations

import os
import re
from typing import Any

from cockpit.collectors.base import BaseCollector


class ServerHealthCollector(BaseCollector):
    """Collects CPU load, RAM, swap, uptime from /proc and system info."""

    name = "server_health"

    async def poll(self) -> dict[str, list[dict[str, Any]]]:
        now = self.now_iso()
        load = self._load_avg()
        mem = self._mem_info()
        uptime = self._uptime()

        hostname = os.uname().nodename

        health_row = {
            "collected_at": now,
            "hostname": hostname,
            "load_avg_1m": load[0],
            "load_avg_5m": load[1],
            "load_avg_15m": load[2],
            "cpu_percent": None,  # computed by averaging idle across samples
            "ram_total_mb": mem.get("MemTotal"),
            "ram_used_mb": mem.get("MemTotal") - mem.get("MemAvailable", 0)
                if "MemTotal" in mem and "MemAvailable" in mem else None,
            "ram_used_percent": round(
                (1 - mem["MemAvailable"] / mem["MemTotal"]) * 100, 1
            ) if mem.get("MemTotal") and mem.get("MemAvailable") else None,
            "swap_total_mb": mem.get("SwapTotal"),
            "swap_used_mb": mem.get("SwapTotal") - mem.get("SwapFree", 0)
                if "SwapTotal" in mem and "SwapFree" in mem else None,
            "swap_used_percent": round(
                (1 - mem["SwapFree"] / mem["SwapTotal"]) * 100, 1
            ) if mem.get("SwapTotal") and mem.get("SwapFree") and mem["SwapTotal"] > 0
            else None,
            "uptime_seconds": uptime,
            "ttl_seconds": 60,
        }

        disk_rows = self._disk_usage(now)

        return {
            "server_health": [health_row],
            "disk_health": disk_rows,
        }

    @staticmethod
    def _load_avg() -> tuple[float, float, float]:
        try:
            with open("/proc/loadavg") as f:
                parts = f.read().split()[:3]
                return tuple(float(p) for p in parts)
        except FileNotFoundError:
            return (0.0, 0.0, 0.0)

    @staticmethod
    def _mem_info() -> dict[str, int]:
        result: dict[str, int] = {}
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    match = re.match(r"^(\w+):\s+(\d+)", line)
                    if match:
                        result[match.group(1)] = int(match.group(2)) // 1024  # kB→MB
        except FileNotFoundError:
            pass
        return result

    @staticmethod
    def _uptime() -> int | None:
        try:
            with open("/proc/uptime") as f:
                return int(float(f.read().split()[0]))
        except (FileNotFoundError, ValueError, IndexError):
            return None

    @staticmethod
    def _disk_usage(now: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        try:
            import subprocess
            result = subprocess.run(
                ["df", "-B1", "--output=target,size,used,avail,ipcent,pcent"],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.strip().split("\n")[1:]:  # skip header
                parts = line.split()
                if len(parts) >= 6:
                    mount = parts[0]
                    total = int(parts[1]) if parts[1].isdigit() else None
                    used = int(parts[2]) if parts[2].isdigit() else None
                    free = int(parts[3]) if parts[3].isdigit() else None
                    inode_str = parts[4].rstrip("%")
                    inode_pct = float(inode_str) if inode_str.replace(".", "", 1).isdigit() else None
                    pct = float(parts[5].rstrip("%")) if parts[5].rstrip("%").replace(".", "", 1).isdigit() else None
                    rows.append({
                        "collected_at": now,
                        "mount_point": mount,
                        "total_gb": round(total / (1024**3), 1) if total else None,
                        "used_gb": round(used / (1024**3), 1) if used else None,
                        "free_gb": round(free / (1024**3), 1) if free else None,
                        "used_percent": pct,
                        "inode_used_percent": inode_pct,
                        "ttl_seconds": 120,
                    })
        except Exception:
            pass
        return rows
